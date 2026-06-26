"""公共评测基准（L2/L3/L4）—— 引入业界公认 benchmark 把指标对标到可比基线。

- L2 cmteb_t2:  C-MTEB T2Retrieval（中文检索基准）
- L3 hotpotqa:  HotpotQA distractor（多跳问答基准）
- L4 longmemeval: LongMemEval-S（长对话记忆基准）

每个子模块导出 `run_benchmark(...)` 异步函数，返回 (指标表 dict, 明细 list)，
与 `tasks/*` 的协议一致，便于 `reporters` 复用。

数据获取走 HuggingFace `datasets` 库，缓存到 `api/eval/cache/`（git ignore）。
"""
from pathlib import Path

# 公共缓存目录：HuggingFace datasets 下载 + 各 benchmark 中间产物
CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


BENCHMARKS = {
    "cmteb-t2": ("L2 中文检索 (C-MTEB T2Retrieval)", "cmteb_t2"),
    "hotpotqa": ("L3 多跳推理 (HotpotQA distractor)", "hotpotqa"),
    "longmemeval": ("L4 长对话记忆 (LongMemEval-S)", "longmemeval"),
}
