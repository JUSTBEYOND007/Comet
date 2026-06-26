"""LongMemEval-S runner:多 session 对话注入记忆系统 → 用 query 集测召回 + 答题 → 按 qtype 算准确率。

设计要点:
- 每题独立 user_id(uuid5(qid)):多 session 萃取进图 → 测试 → 清理
- 萃取走真实链路 `run_extraction`,把每个 session 拼成一段文本喂给萃取(模拟"日常对话沉淀")
- 检索走 `search_memory`,把 top-k 记忆拼上下文 → 让 chat 答题
- 评估:LLM-as-judge(用 chat 模型判 pred 与 gold 是否语义等价,返回 1/0)
- 按 qtype 聚合输出五大能力维度准确率(若数据集中存在更多类型,自动按 type 分组)
"""
from __future__ import annotations

import asyncio
import string
import uuid
from collections import defaultdict
from typing import Any

from app.core.memory.extraction.orchestrator import run_extraction
from app.core.memory.graph_schema import ensure_graph_schema
from app.core.memory.retrieval.searcher import format_memory_context, search_memory
from app.repositories.neo4j.memory_graph_repository import MemoryGraphRepository

from eval import metrics as M
from eval.benchmarks._common import write_benchmark_details, write_benchmark_report
from eval.benchmarks.longmemeval.loader import load

_NS_LME = uuid.UUID("eee40000-0000-0000-0000-0000000000c4")
TOP_K = 8

# qtype 的中文展示名(找不到则用原 type)
_QTYPE_CN = {
    "single-session-user": "单事件回忆 (user)",
    "single-session-assistant": "单事件回忆 (assistant)",
    "single-session-preference": "偏好回忆",
    "multi-session": "多事件聚合",
    "temporal-reasoning": "时间推理",
    "knowledge-update": "知识更新",
}


def _qid_to_uid(qid: str) -> str:
    return str(uuid.uuid5(_NS_LME, qid))


def _session_to_text(session: list[dict]) -> str:
    """把一个 session 拼成可萃取的对话文本。"""
    lines = []
    for msg in session:
        role = msg.get("role", "")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        prefix = "用户" if role == "user" else "助手" if role == "assistant" else role
        lines.append(f"{prefix}:{content}")
    return "\n".join(lines)


# ── LLM-as-judge:判 pred 是否回答对了 gold ──

_JUDGE_PROMPT = """你是评测员,判断"模型回答"是否与"参考答案"在事实上一致。

问题:{question}
参考答案:{gold}
模型回答:{pred}

判断规则:
- 关注事实是否一致,语言形式、详略可以不同。
- 模型回答如果包含参考答案的核心信息(人名/事件/时间/数字)即视为正确。
- 完全无关或事实错误判为不正确。

只输出一个字符:1(一致)/ 0(不一致),不要任何解释。
"""


async def _llm_judge(chat_client, question: str, gold: str, pred: str) -> int:
    """LLM-as-judge 判断 pred 是否与 gold 一致,返回 1/0。"""
    prompt = _JUDGE_PROMPT.format(question=question, gold=gold, pred=pred)
    try:
        text = await chat_client.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=4, temperature=0.0,
        )
    except Exception:
        return 0
    text = (text or "").strip().strip(string.punctuation + " ")
    # 取首字符为判定
    if text.startswith("1"):
        return 1
    return 0


# ── chat 答题(基于记忆上下文) ──

_ANSWER_PROMPT = """你是基于"长期记忆"回答用户问题的助手。

下面是从该用户的多次过往对话中,与本问题相关的记忆片段:

{memory_context}

请用一句简洁的话回答用户问题。不知道就说"无法从记忆中确定"。

问题:{question}
回答:"""


async def _answer(chat_client, question: str, memory_context: str) -> str:
    prompt = _ANSWER_PROMPT.format(memory_context=memory_context or "(无相关记忆)", question=question)
    try:
        text = await chat_client.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=128, temperature=0.0,
        )
    except Exception:
        return ""
    text = (text or "").strip()
    # 去常见前缀
    for marker in ("回答:", "答:"):
        if text.startswith(marker):
            text = text[len(marker):].strip()
    return text


# ── 灌入 / 清理 ──

_INGEST_CONCURRENCY = 3  # 多 session 并发萃取(可经 LME_INGEST_CONCURRENCY 环境变量调)


async def _ingest_sessions(chat_client, embed_client, qid: str, sessions: list[list[dict]]) -> int:
    """把单题的多 session 并发萃取进 Neo4j(本题独立 user_id)。返回成功萃取的 session 数。

    并发数由 _INGEST_CONCURRENCY 控制,默认 3 路。
    并发的好处:LongMemEval 单题多 session 串行萃取太慢(每 session 30~60s);
    多 session 之间没有顺序依赖,asyncio 并发可显著缩短单题耗时,只要不被 LLM 厂商速率限制 429。
    """
    import os
    concurrency = max(1, int(os.getenv("LME_INGEST_CONCURRENCY", str(_INGEST_CONCURRENCY))))
    uid = _qid_to_uid(qid)
    total = len(sessions)
    sem = asyncio.Semaphore(concurrency)
    ok = [0]
    done = [0]

    async def _one(si: int, sess: list[dict]):
        text = _session_to_text(sess)
        if not text:
            done[0] += 1
            print(f"    [session {si}/{total}] 空 session,跳过 (done={done[0]}/{total})")
            return
        msg_count = len(sess)
        print(f"    [session {si}/{total}] ▶ 开始萃取 ({msg_count} 条消息, {len(text)} 字)…")
        async with sem:
            try:
                await run_extraction(
                    chat_client=chat_client, embed_client=embed_client,
                    user_id=uid, text=text, source="manual",
                )
                ok[0] += 1
                done[0] += 1
                print(f"    [session {si}/{total}] ✓ 萃取完成 (done={done[0]}/{total})")
            except Exception as e:  # noqa: BLE001
                done[0] += 1
                print(f"    [session {si}/{total}] ✗ 萃取失败 (done={done[0]}/{total}): {e}")

    await asyncio.gather(*(_one(i, s) for i, s in enumerate(sessions, 1)))
    return ok[0]


async def _clear_one(qid: str) -> None:
    try:
        await MemoryGraphRepository().delete_user_graph(_qid_to_uid(qid))
    except Exception:  # noqa: BLE001
        pass


# ── 主流程 ──

async def run_benchmark(
    embed_client, chat_client, *,
    subset: str = "longmemeval_s",
    limit: int | None = None,
) -> tuple[dict, list]:
    print(f"[longmemeval] 加载数据集 {subset}…")
    queries = load(subset=subset, limit=limit)
    print(f"  题数: {len(queries)}")

    await ensure_graph_schema()

    correct_by_type: dict[str, list[int]] = defaultdict(list)
    details: list[dict] = []
    total = len(queries)

    for i, q in enumerate(queries, 1):
        qid = q["qid"]
        n_sessions = len(q["sessions"])
        print(f"\n  [longmemeval] {i}/{total}  qid={qid}  qtype={q['qtype']}  sessions={n_sessions}")
        print(f"    Q: {q['question'][:60]}")
        try:
            # 1. 灌入 sessions
            n_ok = await _ingest_sessions(chat_client, embed_client, qid, q["sessions"])
            print(f"    ✓ 萃取完成: {n_ok}/{n_sessions} 成功")
            await asyncio.sleep(0.1)
            # 2. 检索记忆
            uid = _qid_to_uid(qid)
            hits = await search_memory(
                embed_client=embed_client, user_id=uuid.UUID(uid),
                query=q["question"], top_k=TOP_K,
            )
            top_names = [h.get("name") for h in hits][:TOP_K]
            print(f"    ✓ 检索 top-{TOP_K}: {top_names}")
            mem_ctx = format_memory_context(hits)
            # 3. 让 chat 基于记忆答
            pred = await _answer(chat_client, q["question"], mem_ctx)
            print(f"    ✓ pred: {pred[:80]}")
            print(f"      gold: {q['answer'][:80]}")
            # 4. LLM-as-judge
            correct = await _llm_judge(chat_client, q["question"], q["answer"], pred)
            mark = "✓ 正确" if correct else "✗ 错误"
            print(f"    {mark} (judge={correct})")
            correct_by_type[q["qtype"]].append(correct)
            details.append({
                "qid": qid,
                "qtype": q["qtype"],
                "question": q["question"],
                "gold_answer": q["answer"],
                "n_sessions": len(q["sessions"]),
                "n_sessions_ingested": n_ok,
                "retrieved_top_names": top_names,
                "pred": pred,
                "correct": correct,
            })
        finally:
            await _clear_one(qid)

    # 按 qtype 聚合
    table: dict[str, dict[str, Any]] = {}
    all_correct: list[int] = []
    for qtype, lst in sorted(correct_by_type.items()):
        all_correct.extend(lst)
        table[_QTYPE_CN.get(qtype, qtype)] = {
            "Accuracy": M.avg(lst),
            "样本数": len(lst),
        }
    table["综合"] = {
        "Accuracy": M.avg(all_correct),
        "样本数": len(all_correct),
    }

    meta = {
        "数据集": f"xiaowu0162/longmemeval ({subset})",
        "题数": len(queries),
        "embedding 模型": embed_client.model_name,
        "chat 模型(answer + judge)": chat_client.model_name,
        "top_k 记忆召回": TOP_K,
    }
    notes = [
        "LongMemEval 评测:把多 session 长对话注入记忆系统(萃取入 Neo4j),"
        "用问题测召回 → chat 答 → LLM-as-judge 判事实一致(1/0)。",
        "按 question_type 聚合五大能力维度准确率(子集中存在的类型)。",
        "每题独立 user_id(uuid5),萃取→评估→清理,题间不互相干扰。",
        "Judge 与 answerer 用同一 chat 模型:存在自评偏置风险,可考虑跨模型 judge 减少偏差(待 ② 完成后接入)。",
    ]
    report = write_benchmark_report(
        "longmemeval", "LongMemEval-S (L4)",
        table, meta=meta, extra_notes=notes,
    )
    detail_path = write_benchmark_details("longmemeval", details)
    print(f"  报告: {report}\n  明细: {detail_path}")
    return table, details
