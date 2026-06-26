"""L4 长对话记忆基准 —— LongMemEval(EMNLP 2024)。

公共数据集对照:专评长对话记忆 5 大能力(单事件回忆 / 多事件聚合 / 时间推理 / 知识更新 / 抽象理解),
与本项目记忆系统功能划分几乎一一对应。
"""
from eval.benchmarks.longmemeval.runner import run_benchmark

__all__ = ["run_benchmark"]
