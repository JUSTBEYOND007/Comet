"""LongMemEval 数据加载(HuggingFace `xiaowu0162/longmemeval`)。

⚠ 仓库特殊情况:作者在 HF 上把数据文件改名时去掉了 `.json` 后缀
(longmemeval_s.json → longmemeval_s),导致 `datasets.load_dataset` 的 auto-discovery 失败。
解决:用 `huggingface_hub.hf_hub_download` 直接下载文件,手动解析 JSON。

数据集结构(每条):
- question_id:        str
- question_type:      single-session-user | single-session-assistant | single-session-preference |
                      multi-session | temporal-reasoning | knowledge-update | (其他取决于版本)
- question:           str
- answer:             str (参考答案,短文本)
- haystack_sessions:  [[{"role":"user/assistant","content":"..."}, ...], ...] 多 session 长对话
- answer_session_ids: [str, ...] 答案出处的 session id(可选)

子集与体积:
- longmemeval_oracle:  15.4 MB(精简版,推荐先用)
- longmemeval_s:      278 MB
- longmemeval_m:     2.75 GB(太大,本项目用不上)
"""
from __future__ import annotations

import json
from typing import TypedDict

from eval.benchmarks._common import cache_path

_HF_REPO = "xiaowu0162/longmemeval"
# 仓库内的实际文件名(无扩展名,但内容是 JSON)
_FILE_BY_SUBSET = {
    "longmemeval_s": "longmemeval_s",
    "longmemeval_m": "longmemeval_m",
    "longmemeval_oracle": "longmemeval_oracle",
}


class LMEQuery(TypedDict):
    qid: str
    qtype: str
    question: str
    answer: str
    sessions: list[list[dict]]
    answer_session_ids: list


def load(subset: str = "longmemeval_s", limit: int | None = None) -> list[LMEQuery]:
    """加载 LongMemEval。

    Args:
        subset: longmemeval_s(短)/ longmemeval_m(中)/ longmemeval_oracle(精简) —— 默认 _s
        limit: 题数上限(快速验证用)
    """
    if subset not in _FILE_BY_SUBSET:
        raise ValueError(f"未知子集 {subset};可选:{list(_FILE_BY_SUBSET)}")

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as e:
        raise RuntimeError(
            "缺少 huggingface_hub 依赖(应随 datasets 一起装)。请在 api/ 下执行:uv sync"
        ) from e

    cache_dir = str(cache_path("hf_datasets").parent)
    filename = _FILE_BY_SUBSET[subset]
    print(f"  [longmemeval] 下载/读取 {filename}(首次会下,后续走缓存)…")
    path = hf_hub_download(
        repo_id=_HF_REPO,
        filename=filename,
        repo_type="dataset",
        cache_dir=cache_dir,
    )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    out: list[LMEQuery] = []
    for i, row in enumerate(data):
        if limit is not None and i >= limit:
            break
        out.append({
            "qid": str(row.get("question_id") or i),
            "qtype": str(row.get("question_type") or "unknown"),
            "question": (row.get("question") or "").strip(),
            "answer": (row.get("answer") or "").strip(),
            "sessions": row.get("haystack_sessions") or [],
            "answer_session_ids": row.get("answer_session_ids") or [],
        })
    return out
