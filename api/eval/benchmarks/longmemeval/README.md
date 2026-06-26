# L4 · LongMemEval-S

长对话记忆评测基准(EMNLP 2024),专评 5 大记忆能力,与本项目记忆系统功能划分几乎一一对应。

## 数据来源

- **HuggingFace 数据集**:[`xiaowu0162/longmemeval`](https://huggingface.co/datasets/xiaowu0162/longmemeval)
- **License**:MIT(见数据集 README)
- **子集与体积**:
  - `longmemeval_oracle`(**15.4 MB,推荐先用**):精简版,只含答案出处的相关 session,题数与 _s 接近
  - `longmemeval_s`(默认,278 MB):短版本,~500 题,对应 ICLR 2025 论文报告值
  - `longmemeval_m`(2.75 GB):中版本,本项目过大,不建议
- **⚠ 仓库特殊情况**:作者在 HF 上把数据文件改名时去掉了 `.json` 后缀(`longmemeval_s.json → longmemeval_s`),导致 `datasets.load_dataset` 的 auto-discovery 失败。本项目改用 `huggingface_hub.hf_hub_download` 直接下载文件、手动解析 JSON。
- 首次下载会缓存到 `api/eval/cache/hf_datasets/`

## 评测协议

- **指标**:按 `question_type` 聚合 + 综合 Accuracy
  - 单事件回忆 / 偏好回忆 / 多事件聚合 / 时间推理 / 知识更新 / …(取决于子集中存在的类型)
- **流程**:每题独立 user_id → 萃取多 session 对话进 Neo4j → 用问题做 `search_memory` 召回 top-k 记忆 → chat 模型基于记忆答 → LLM-as-judge 判 pred 与 gold 事实一致(1/0)
- **top-k 记忆召回**:默认 8
- **Judge 模型**:与 answerer 共用同一 chat 模型(存在自评偏置;**待 ② Verifier Loop 完成后可改用跨模型 judge 降低偏置**)

## 命名空间隔离

- 每题独立 `user_id = uuid5(NS_LME, qid)`,萃取 → 评估 → 立刻清理
- 题间互不污染;跑完不留残留

## 跑法

```bash
# 推荐先用 oracle 子集(15 MB),先把流程跑通
uv run python -m eval.run_eval --benchmark longmemeval --lme-subset longmemeval_oracle --lme-limit 20

# 默认 longmemeval_s(278 MB,~500 题,论文报告值同款),本项目默认只取 20 题
uv run python -m eval.run_eval --benchmark longmemeval

# 想跑更多
uv run python -m eval.run_eval --benchmark longmemeval --lme-limit 100
```

## 输出

- `report-longmemeval-{ts}.md`:各 qtype 准确率表 + 综合 + 评测元信息
- `details-longmemeval-{ts}.json`:逐题明细(召回的记忆名 / pred / correct)

## 注意

- 单题处理较重(多 session 萃取入图 + 检索 + 答 + judge),全集约 500 题可能需要较长时间和较多 token。开跑前建议:
  1. `--lme-limit 20` 验证链路通
  2. 估算单题平均耗时与 token,再决定是否全跑
- LongMemEval 论文报告了主流商业模型(GPT-4o / Claude 等)的基线,可作横向对照(但本项目的检索/萃取链路与论文实现不同,不可直接比绝对水平)

## 简历话术(待填真实数字)

> 在 LongMemEval-S 上,综合记忆准确率 X%;
> 时间推理 = Y%,知识更新 = Z%,多事件聚合 = W%(各维度对照主流商业模型基线)。

## 引用

```bibtex
@article{wu2024longmemeval,
  title={LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory},
  author={Wu, Di and Wang, Hongwei and Yu, Wenhao and Zhang, Yuwei and Chang, Kai-Wei and Yu, Dong},
  journal={EMNLP},
  year={2024}
}
```
