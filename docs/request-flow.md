# 请求链路

## 1. 上传文档：POST /documents/upload
main.py 的 xxx() 
  → (做了什么) 
  → (调了哪个模块)
  → 落在哪张表

## 2. 提问：POST /ask
main.py 的 xxx()
  → repository 取出候选
  → retrieval.search_chunks() 或 hybrid_search_chunks()
  → answering.answer()
  → 返回 { 字段1, 字段2 }

## 3. 评测：POST /eval/retrieval
main.py 的 xxx()
  → 加载 data/eval_set.json
  → 对每条问题跑检索
  → 算 Recall@K / MRR / 平均延迟

## 4. 关键发现（一句话）
哪一步最慢？哪一步最容易出错？