# ai-agent-rag

可溯源的 RAG 文档问答系统：混合检索（BM25 + 向量）+ 段落级评测（Recall@K / MRR）。

> **本项目基于 [kinoshita-fuyou/ai-learning-copilot](https://github.com/kinoshita-fuyou/ai-learning-copilot) 的 MIT 协议代码二次开发。**
> 检索策略、评测体系与语料由本人重构，改动记录见 `docs/changelog.md`。

## 当前状态

- [x] 工程基线：跑通上游全链路
- [ ] 接入真实 LLM Provider（DeepSeek）
- [ ] 语料替换：15–30 篇真实领域文档
- [ ] embedding 替换：特征哈希 → 真实向量模型
- [ ] 段落级评测集（30 条，含无答案题）
- [ ] 消融实验：纯向量 vs 混合检索

## 快速开始

（待补）

## 评测结果

（待补：填入真实数字）

## 已知局限

（待补：至少写 3 条。诚实的局限比吹嘘更加分）
liyitai06-30
