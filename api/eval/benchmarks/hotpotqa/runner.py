"""HotpotQA distractor runner：检索 top-k 段落 → 多跳 chat 答 → EM/F1 + 检索 Recall。

设计要点：
- 每题独立 user_id（uuid5(qid)），灌入 → 查 → 清理；不互相干扰、可重入。
- 段落级粒度（source_id = title），便于按 `gold_titles` 算检索 Recall。
- 三组对照：无 Verifier(A) / 同模型 self-critique(B) / 跨模型 Verifier(C) —— ② Verifier Loop 完成后才接入。
  当前先支持 baseline（无 Verifier），保留接口供 ② 接入后扩展。
- 答案评估走 HotpotQA 官方 `exact_match_score` / `f1_score` 口径（normalize + token 级 P/R/F1）。
"""
from __future__ import annotations

import asyncio
import re
import string
import uuid
from collections import Counter
from typing import Any

from app.core.rag.es_index import CHUNK_TYPE_CHILD, CHUNKS_INDEX, ensure_index
from app.core.rag.es_store import build_chunk_doc, bulk_index
from app.db.elastic import get_es

from eval import clients
from eval import metrics as M
from eval.benchmarks._common import write_benchmark_details, write_benchmark_report
from eval.benchmarks.hotpotqa.loader import load

K_RETRIEVE = 4  # 每题检索 top-4 段落给 chat 答（distractor 共 10 段，2 段是 gold）

# 命名空间根：每题 user_id = uuid5(NS_HOTPOT, qid)
_NS_HOTPOT = uuid.UUID("eee30000-0000-0000-0000-0000000000c3")


def _qid_to_uid(qid: str) -> str:
    return str(uuid.uuid5(_NS_HOTPOT, qid))


# ── HotpotQA 官方 EM/F1 评测口径（normalize + token） ──

def _normalize_answer(s: str) -> str:
    """官方口径：删除冠词、标点、多余空白、转小写。"""
    s = s.lower()
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _em(pred: str, gold: str) -> float:
    return float(_normalize_answer(pred) == _normalize_answer(gold))


def _f1(pred: str, gold: str) -> float:
    pt = _normalize_answer(pred).split()
    gt = _normalize_answer(gold).split()
    if not pt or not gt:
        return float(pt == gt)
    common = Counter(pt) & Counter(gt)
    num_same = sum(common.values())
    if num_same == 0:
        return 0.0
    p = num_same / len(pt)
    r = num_same / len(gt)
    return 2 * p * r / (p + r)


# ── 灌入与检索 ──

async def _ingest_one(embed_client, qid: str, paragraphs: list[dict]) -> None:
    """把单题的 10 段灌进 ES（child 粒度即可，段落本身就短）。"""
    uid = _qid_to_uid(qid)
    es_docs: list[dict] = []
    # 批量算向量
    texts = []
    titles = []
    for p in paragraphs:
        content = " ".join(p["sentences"])
        texts.append(content)
        titles.append(p["title"])
    vectors = await embed_client.embed(texts) if texts else []
    for title, content, vec in zip(titles, texts, vectors):
        es_docs.append(build_chunk_doc(
            user_id=uid, source_type="document", source_id=title,
            doc_name=title, chunk_type=CHUNK_TYPE_CHILD,
            content=content, vector=vec,
        ))
    if es_docs:
        await bulk_index(es_docs)


async def _clear_one(qid: str) -> None:
    es = get_es()
    try:
        await es.delete_by_query(
            index=CHUNKS_INDEX,
            body={"query": {"term": {"user_id": _qid_to_uid(qid)}}},
            refresh=True,
            conflicts="proceed",
        )
    except Exception:  # noqa: BLE001
        pass


# ── chat 回答 ──

_ANSWER_PROMPT = """You are answering a multi-hop question by ONLY using the provided paragraphs.

Question: {question}

Paragraphs:
{paragraphs}

Rules:
- Reason step by step internally, then output ONLY the final answer as a short phrase or "yes"/"no".
- Do NOT include explanations, punctuation, or quotation marks in the final answer line.
- If the answer is a person/place name, output exactly as it appears in the paragraphs.

Final Answer:"""


async def _answer(chat_client, question: str, paragraphs: list[tuple[str, str]]) -> str:
    """让 chat 模型基于检索到的 paragraphs 答 HotpotQA。返回最终答案文本。"""
    p_text = "\n\n".join(f"[{title}]\n{content}" for title, content in paragraphs)
    prompt = _ANSWER_PROMPT.format(question=question, paragraphs=p_text)
    text = await chat_client.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=128, temperature=0.0,
    )
    # 仅取「Final Answer:」后的最后一行作为最终答案
    text = (text or "").strip()
    # 去掉模型偶尔重复输出的「Final Answer:」前缀
    for marker in ("Final Answer:", "final answer:", "答案:", "Answer:"):
        if marker in text:
            text = text.split(marker, 1)[1]
    # 取首行非空
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line.strip(string.punctuation + " \"'")
    return text


# ── 主流程 ──

async def run_benchmark(
    embed_client, chat_client, rerank_client=None, *,
    sample: int = 500,
    verifier: str = "none",
    seed: int = 42,
) -> tuple[dict, list]:
    """跑 HotpotQA distractor。

    Args:
        embed_client / chat_client / rerank_client: 由 run_eval 注入
        sample: 采样数（按 bridge/comparison 分层）
        verifier: none | same | cross —— ② Verifier 接入后启用；当前 'none' 是 baseline
        seed: 采样种子
    """
    if verifier != "none":
        print(f"[hotpotqa] verifier={verifier} 暂未接入（等待 ② Verifier Loop 完成），按 'none' 跑")
    print(f"[hotpotqa] 加载数据集（采样 {sample} 条）…")
    queries = load(n=sample, seed=seed)
    print(f"  实际采样: {len(queries)} 条（bridge/comparison 按比例）")

    await ensure_index()

    # 累积指标
    em_list: list[float] = []
    f1_list: list[float] = []
    retr_recall_list: list[float] = []  # 检索 top-k 段落对 gold_titles 的覆盖
    details: list[dict] = []

    total = len(queries)
    for i, q in enumerate(queries, 1):
        qid = q["qid"]
        uid = _qid_to_uid(qid)
        print(f"  [hotpotqa] {i}/{total}  qid={qid}  type={q['qtype']}")
        print(f"    Q: {q['question'][:80]}")
        # 1. 灌入本题 10 段
        await _ingest_one(embed_client, qid, q["paragraphs"])
        await asyncio.sleep(0.05)  # 给 ES 一点索引时间
        try:
            # 2. 检索 top-k
            rh = await clients.retrieve_hybrid(embed_client, uid, q["question"], 10)
            if rerank_client is not None and len(rh) > K_RETRIEVE:
                rh = await clients.rerank_sources(rerank_client, uid, q["question"], rh, K_RETRIEVE)
            else:
                rh = rh[:K_RETRIEVE]
            # 3. 收集检索到的段落（按 source_id == title 对回 paragraphs）
            title_to_content = {p["title"]: " ".join(p["sentences"]) for p in q["paragraphs"]}
            retrieved = [(t, title_to_content.get(t, "")) for t in rh if t in title_to_content]
            # 4. 评检索 Recall: top-k 中命中 gold_titles 的数量 / 总 gold
            gold = q["gold_titles"]
            hits_in_topk = [t for t in rh if t in gold]
            retr_recall = len(hits_in_topk) / max(1, len(gold))
            retr_recall_list.append(retr_recall)
            print(f"    ✓ 检索 top-{K_RETRIEVE}: {rh} | 命中 gold={hits_in_topk} (Recall={retr_recall:.2f})")
            # 5. 让 chat 答
            pred = await _answer(chat_client, q["question"], retrieved)
            em = _em(pred, q["answer"])
            f1 = _f1(pred, q["answer"])
            em_list.append(em)
            f1_list.append(f1)
            mark = "✓" if em else ("~" if f1 > 0 else "✗")
            print(f"    {mark} pred='{pred[:60]}' | gold='{q['answer'][:60]}' | EM={em:.0f} F1={f1:.2f}")
            details.append({
                "qid": qid,
                "question": q["question"],
                "type": q["qtype"],
                "gold_answer": q["answer"],
                "gold_titles": gold,
                "retrieved_topk_titles": rh,
                "retrieval_recall": round(retr_recall, 4),
                "pred": pred,
                "em": em,
                "f1": round(f1, 4),
            })
        finally:
            await _clear_one(qid)

    table: dict[str, dict[str, Any]] = {
        f"baseline (verifier={verifier})": {
            "EM": M.avg(em_list),
            "F1": M.avg(f1_list),
            f"Retr Recall@{K_RETRIEVE}": M.avg(retr_recall_list),
            "样本数": len(em_list),
        }
    }

    meta = {
        "数据集": "hotpot_qa / distractor",
        "切分": "validation",
        "采样数": sample,
        "类型分布": _type_distribution(queries),
        "embedding 模型": embed_client.model_name,
        "chat 模型": chat_client.model_name,
        "rerank 模型": rerank_client.model_name if rerank_client else "（未配置）",
        "verifier 配置": verifier,
    }
    notes = [
        "HotpotQA distractor 评测：每题给 10 段（2 gold + 8 distractor），系统先检索 top-k 再多跳答。",
        "**污染声明**：dev 集发布于 2018 年，目前主流 LLM 训练集大概率覆盖；本评测仅用于系统设计对比（检索/Verifier 配置间），不作绝对水平断言。",
        "EM/F1 走 HotpotQA 官方口径（normalize + token 级 P/R/F1）。",
        "verifier 字段说明：none = 无 Verifier baseline；same/cross 待 ② Verifier Loop 接入后启用。",
    ]
    report = write_benchmark_report(
        "hotpotqa", "HotpotQA distractor (L3)",
        table, meta=meta, extra_notes=notes,
    )
    detail_path = write_benchmark_details("hotpotqa", details)
    print(f"  报告: {report}\n  明细: {detail_path}")
    return table, details


def _type_distribution(queries: list[dict]) -> str:
    c = Counter(q["qtype"] for q in queries)
    return ", ".join(f"{k}={v}" for k, v in c.most_common())
