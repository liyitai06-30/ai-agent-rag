# -*- coding: utf-8 -*-
r"""评测运行器：读 eval/questions.txt，先校验再计算 Recall@K / MRR。

questions.txt 格式（每行一条，用 | 分隔；字段两端空格会被忽略）：

    id | 问题 | 期望文档标题 | 期望段落锚点 | 有无答案(1/0)

    以 # 开头的行是注释，空行忽略。
    无答案题：期望文档和锚点留空，最后一列填 0。

用法（在 evidenceqa 目录下）：
    python eval_run.py                  # 先校验，通过后跑评测（默认 hybrid）
    python eval_run.py --check-only     # 只校验，不跑
    python eval_run.py --mode vector    # 纯向量模式
    python eval_run.py -k 5

三个指标：
    Recall@K   期望文档是否出现在前 K 条里（衡量"找不找得到"）
    Hit@K      前 K 条里是否有【同一篇文档、且包含锚点】的块（衡量"定位准不准"）
    MRR        第一个命中块的排名的倒数取平均（衡量"排得靠不靠前"）
"""

import argparse
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path


def pack(text: str) -> str:
    """去掉所有空白，用于中文锚点匹配。"""
    return re.sub(r"\s+", "", text or "")


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "y", "yes", "true", "是", "有"}


def parse_questions(path: Path):
    items, errors = [], []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 5:
            errors.append(f"第 {lineno} 行：字段不足，需要 5 个用 | 分隔 → {line[:40]}")
            continue
        qid, question, expected, anchor, has_answer = parts[0], parts[1], parts[2], parts[3], parts[4]
        if not qid or not question:
            errors.append(f"第 {lineno} 行：id 或问题为空")
            continue
        items.append(
            {
                "id": qid,
                "question": question,
                "expected": expected,
                "anchor": anchor,
                "has_answer": parse_bool(has_answer),
                "second": parts[5] if len(parts) >= 6 else "",
                "line": lineno,
            }
        )
    return items, errors


def resolve_title(expected: str, titles: list[str]) -> str | None:
    """精确匹配优先，否则允许唯一前缀匹配（少打字）。"""
    if expected in titles:
        return expected
    candidates = [t for t in titles if t.startswith(expected)]
    if len(candidates) == 1:
        return candidates[0]
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", default="../eval/questions.txt")
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--mode", choices=["hybrid", "vector"], default="hybrid")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    questions_path = Path(args.questions).resolve()
    if not questions_path.is_file():
        print(f"[错误] 找不到题目文件：{questions_path}")
        return 2

    items, errors = parse_questions(questions_path)
    if errors:
        print("[格式错误]")
        for e in errors:
            print("  " + e)
        return 2
    if not items:
        print("[错误] 题目文件里没有有效条目")
        return 2

    from app.database import DB_PATH, get_connection
    from app.embeddings import get_embedder
    from app.retrieval import hybrid_search_chunks, search_chunks

    with get_connection(DB_PATH) as connection:
        titles = [r["title"] for r in connection.execute("SELECT title FROM documents")]
        chunk_rows = connection.execute(
            "SELECT document_id, chunk_index, content FROM chunks"
        ).fetchall()
        doc_titles = {
            r["id"]: r["title"]
            for r in connection.execute("SELECT id, title FROM documents")
        }

    embedder = get_embedder()
    embedder_name = (
        f"{type(embedder).__name__}({getattr(embedder, 'model', '-')})"
        if hasattr(embedder, "model")
        else f"{type(embedder).__name__}(dim={getattr(embedder, 'dimensions', '-')})"
    )

    print("=" * 78)
    print(f"题目文件：{questions_path}")
    print(f"题目数量：{len(items)}")
    print(f"数据库　：{DB_PATH}   （{len(titles)} 篇文档 / {len(chunk_rows)} 个切块）")
    print(f"Embedding：{embedder_name}")
    print("=" * 78)

    # ---------------- 校验 ----------------
    problems = []
    ids = set()
    for item in items:
        if item["id"] in ids:
            problems.append(f"{item['id']}：id 重复")
        ids.add(item["id"])

        if item["has_answer"]:
            title = resolve_title(item["expected"], titles)
            if title is None:
                problems.append(
                    f"{item['id']}：找不到文档「{item['expected'][:30]}」（请从 eval_catalog.md 里复制标题）"
                )
                continue
            item["expected"] = title
            if not item["anchor"]:
                problems.append(f"{item['id']}：正样本必须填锚点")
                continue
            if item.get("second"):
                second = resolve_title(item["second"], titles)
                if second is None:
                    problems.append(
                        f"{item['id']}：第二文档「{item['second'][:30]}」在库里找不到"
                    )
                else:
                    item["second"] = second
            needle = pack(item["anchor"])
            doc_id = next((i for i, t in doc_titles.items() if t == title), None)
            texts = [pack(r["content"]) for r in chunk_rows if r["document_id"] == doc_id]
            if not any(needle in text for text in texts):
                problems.append(
                    f"{item['id']}：锚点「{item['anchor'][:20]}」在该文档的切块里找不到（检查是否有错字或多余空格）"
                )
        else:
            if item["expected"] or item["anchor"]:
                problems.append(f"{item['id']}：无答案题不应填文档和锚点")

    positives = sum(1 for i in items if i["has_answer"])
    negatives = len(items) - positives
    print(f"正样本 {positives} 条 / 无答案 {negatives} 条")

    if problems:
        print(f"\n[校验未通过] 发现 {len(problems)} 个问题：")
        for p in problems:
            print("  - " + p)
        print("\n按提示改完 questions.txt 再跑一次。")
        return 3

    print("校验通过。")
    if args.check_only:
        return 0

    # ---------------- 跑评测 ----------------
    search = hybrid_search_chunks if args.mode == "hybrid" else search_chunks
    print(f"\n开始评测（mode={args.mode}, k={args.k}）…\n")
    print(f"{'id':<6}{'Recall':<8}{'Hit':<7}{'RR':<8}{'ms':<8}问题")
    print("-" * 78)

    recall_list, hit_list, rr_list, latency_list = [], [], [], []
    failures = []
    negative_scores = []

    for item in items:
        started = time.perf_counter()
        hits = search(
            query=item["question"], embedder=embedder, top_k=args.k, db_path=DB_PATH
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        latency_list.append(elapsed_ms)

        hit_titles = [h["title"] for h in hits]

        if not item["has_answer"]:
            # 无答案题：记录原始向量相似度最高分，用来定拒答阈值
            raw = search_chunks(
                query=item["question"], embedder=embedder, top_k=1, db_path=DB_PATH
            )
            top_score = raw[0]["score"] if raw else 0.0
            negative_scores.append((item["id"], top_score))
            print(f"{item['id']:<6}{'—':<8}{'—':<7}{'—':<8}{elapsed_ms:<8.0f}[无答案] {item['question'][:26]}  最高分={top_score:.3f}")
            continue

        needle = pack(item["anchor"])
        # 多跳题：两个文档都要进 Top-K 才算召回
        doc_recalled = item["expected"] in hit_titles
        if item.get("second"):
            doc_recalled = doc_recalled and (item["second"] in hit_titles)
        rr = 0.0
        anchor_rank = None
        for rank, hit in enumerate(hits, 1):
            if hit["title"] == item["expected"] and needle in pack(hit["content"]):
                anchor_rank = rank
                rr = 1.0 / rank
                break

        recall_list.append(1.0 if doc_recalled else 0.0)
        hit_list.append(1.0 if anchor_rank else 0.0)
        rr_list.append(rr)

        flag = "✓" if anchor_rank == 1 else ("~" if anchor_rank else "✗")
        print(
            f"{item['id']:<6}{'✓' if doc_recalled else '✗':<8}"
            f"{'✓' if anchor_rank else '✗':<7}{rr:<8.2f}{elapsed_ms:<8.0f}"
            f"{flag} {item['question'][:24]}"
        )
        if not anchor_rank:
            failures.append(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "expected": item["expected"],
                    "anchor": item["anchor"],
                    "got": hit_titles[:3],
                }
            )

    # ---------------- 汇总 ----------------
    print("-" * 78)
    if recall_list:
        print(f"Recall@{args.k}（文档级）  : {statistics.mean(recall_list):.4f}")
        print(f"Hit@{args.k}（锚点级）     : {statistics.mean(hit_list):.4f}")
        print(f"MRR（锚点级）             : {statistics.mean(rr_list):.4f}")
    print(f"平均检索延迟              : {statistics.mean(latency_list):.0f} ms")
    if negative_scores:
        scores = [s for _, s in negative_scores]
        print(
            f"无答案题 top1 相似度       : 均值 {statistics.mean(scores):.3f}  "
            f"最高 {max(scores):.3f}"
        )
        print("  → 这个分布用来定拒答阈值：正样本的最低分应该明显高于它")

    if failures:
        print(f"\n失败清单（{len(failures)} 条，直接拿去做 badcase 卡）：")
        for f in failures:
            print(f"  [{f['id']}] {f['question']}")
            print(f"        期望：{f['expected']} / 锚点：{f['anchor'][:20]}")
            print(f"        实际：{f['got']}")

    # ---------------- 落盘 ----------------
    out_dir = questions_path.parent
    report = out_dir / f"results_{args.mode}_{datetime.now().strftime('%m%d_%H%M')}.md"
    lines = [
        f"# 评测结果（{args.mode}）",
        "",
        f"- 时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- 题目：{len(items)} 条（正样本 {positives} / 无答案 {negatives}）",
        f"- Embedding：{embedder_name}",
        f"- 文档数 / 切块数：{len(titles)} / {len(chunk_rows)}",
        f"- K = {args.k}",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| Recall@{args.k}（文档级） | {statistics.mean(recall_list):.4f} |" if recall_list else "",
        f"| Hit@{args.k}（锚点级） | {statistics.mean(hit_list):.4f} |" if hit_list else "",
        f"| MRR（锚点级） | {statistics.mean(rr_list):.4f} |" if rr_list else "",
        f"| 平均检索延迟 | {statistics.mean(latency_list):.0f} ms |",
        "",
    ]
    if failures:
        lines.append("## 失败清单\n")
        for f in failures:
            lines.append(f"- **{f['id']}** {f['question']}")
            lines.append(f"  - 期望：{f['expected']} / 锚点：`{f['anchor']}`")
            lines.append(f"  - 实际 Top3：{f['got']}")
    report.write_text("\n".join(x for x in lines if x), encoding="utf-8")
    print(f"\n报告已保存：{report}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
