# -*- coding: utf-8 -*-
r"""把 corpus/ 目录下的文档批量导入 EvidenceQA 的 SQLite 库，并自动生成语料清单。

支持的格式：.md / .mdx / .txt（.mdx 会自动清洗 import 语句和 JSX 标签）
子目录会被递归扫描，标题冲突时自动用「父目录/文件名」区分。

用法（在 evidenceqa 目录下，用 venv 的 python）：
    python import_corpus.py --corpus ..\corpus --reset

它做五件事：
    1. 可选：清空 documents / chunks（--reset）
    2. 读取并清洗文本（MDX 语法剥离、frontmatter 剥离、normalize_text）
    3. 按 chunking.py 的规则切块（CHUNK_SIZE=500, OVERLAP=80）
    4. 算 embedding 并写库
    5. 自动生成 corpus/MANIFEST.md（语料清单）

注意：导入逻辑复用 app/ 下的正式代码，和网页上传的行为完全一致。
"""

import argparse
import re
import time
from datetime import datetime
from pathlib import Path

SUPPORTED_SUFFIXES = {".md", ".mdx", ".txt"}

# 这些文件不作为语料导入（清单本身、说明文件、以下划线开头的临时文件）
SKIP_NAMES = {"manifest.md", "readme.md", "changelog.md"}

FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.S)
IMPORT_RE = re.compile(r"^\s*(import|export)\s+")
JSX_TAG_RE = re.compile(r"</?[A-Za-z][^<>]*>")
JSX_EXPR_RE = re.compile(r"\{[^{}\n]*\}")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)


def split_frontmatter(text: str) -> tuple[str, str]:
    """拆出 frontmatter（用于取 title），返回 (frontmatter, 正文)。"""
    match = FRONTMATTER_RE.match(text)
    if match:
        return match.group(1), text[match.end():]
    return "", text


def clean_mdx(body: str) -> str:
    """清洗 MDX 专有语法。代码块内部原样保留。"""
    output = []
    in_fence = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            output.append(line)
            continue
        if in_fence:
            output.append(line)
            continue
        if IMPORT_RE.match(line):
            continue
        line = JSX_TAG_RE.sub("", line)
        line = JSX_EXPR_RE.sub("", line)
        output.append(line)
    text = "\n".join(output)
    text = HTML_COMMENT_RE.sub("", text)
    return text


def pick_title(frontmatter: str, body: str, fallback: str) -> str:
    """优先 frontmatter 的 title，其次第一个 H1，最后用文件名。"""
    match = re.search(r"^\s*title\s*:\s*(.+?)\s*$", frontmatter, re.M)
    if match:
        title = match.group(1).strip().strip("\"'")
        if title:
            return title
    match = H1_RE.search(body)
    if match:
        return match.group(1).strip()
    return fallback


def unique_title(title: str, relative: Path, used: set[str]) -> str:
    """标题冲突时用「父目录/文件名」区分。"""
    if title not in used:
        used.add(title)
        return title
    candidate = f"{relative.parent.name}/{title}" if relative.parent.name else title
    index = 2
    base = candidate
    while candidate in used:
        candidate = f"{base} ({index})"
        index += 1
    used.add(candidate)
    return candidate


def write_manifest(corpus: Path, rows: list[dict], embedder_name: str) -> Path:
    total_chars = sum(row["chars"] for row in rows)
    total_chunks = sum(row["chunks"] for row in rows)
    lines = [
        "# 语料清单",
        "",
        "> 本文件由 `import_corpus.py` 自动生成，不需要手工维护。",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- 文件数量：{len(rows)} 篇",
        f"- 总字数：{total_chars:,}",
        f"- 总切块：{total_chunks}",
        f"- Embedding：{embedder_name}",
        "",
        "## 明细",
        "",
        "| # | 文件 | 标题（进入评测的 ground truth） | 字数 | 块数 | 主要小节 |",
        "|---|---|---|---|---|---|",
    ]
    for index, row in enumerate(rows, 1):
        sections = row["sections"] or "—"
        lines.append(
            f"| {index} | {row['file']} | {row['title']} | {row['chars']:,} | "
            f"{row['chunks']} | {sections} |"
        )
    lines.append("")
    lines.append("## 待补充（人工判断，不必现在写）")
    lines.append("")
    lines.append("文档之间的「交叉点」——哪些篇目讲了同一件事的不同侧面。")
    lines.append("Day 4 写多跳评测题时会用到：只有存在交叉，才问得出「需要综合两篇」的问题。")
    lines.append("")
    path = corpus / "MANIFEST.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default="../corpus", help="语料目录，默认 ../corpus")
    parser.add_argument("--reset", action="store_true", help="导入前清空 documents 与 chunks")
    parser.add_argument("--limit", type=int, default=0, help="只导入前 N 个文件，0 表示全部")
    parser.add_argument("--no-manifest", action="store_true", help="不生成 MANIFEST.md")
    args = parser.parse_args()

    corpus = Path(args.corpus).resolve()
    if not corpus.exists():
        print(f"[错误] 语料目录不存在：{corpus}")
        return 2

    files = sorted(
        path
        for path in corpus.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_SUFFIXES
        and path.name.lower() not in SKIP_NAMES
        and not path.name.startswith("_")
    )
    if args.limit > 0:
        files = files[: args.limit]
    if not files:
        print(f"[错误] {corpus} 里没有找到 {'/'.join(sorted(SUPPORTED_SUFFIXES))} 文件")
        return 2

    from app.chunking import chunk_text, normalize_text
    from app.database import DB_PATH, get_connection, init_db
    from app.embeddings import get_embedder
    from app.repository import create_document, replace_document_chunks

    print("=" * 68)
    print(f"语料目录：{corpus}")
    print(f"文件数量：{len(files)}")
    print(f"数据库　：{DB_PATH}")
    init_db(DB_PATH)

    try:
        embedder = get_embedder()
    except Exception as error:
        print(f"[错误] 初始化 embedding 失败：{error}")
        print("提示：若 EMBEDDING_PROVIDER=api，请检查 .env 里的 BASE_URL / API_KEY")
        return 3

    if hasattr(embedder, "model"):
        embedder_name = f"{type(embedder).__name__}({getattr(embedder, 'model', '-')})"
    else:
        embedder_name = f"{type(embedder).__name__}(dim={getattr(embedder, 'dimensions', '-')})"
    print(f"Embedding：{embedder_name}")
    print("=" * 68)

    if args.reset:
        with get_connection(DB_PATH) as connection:
            connection.execute("DELETE FROM chunks")
            connection.execute("DELETE FROM documents")
        print("已清空原有文档与切块。\n")

    used_titles: set[str] = set()
    rows: list[dict] = []
    failed: list[tuple[str, str]] = []
    started = time.perf_counter()

    for index, path in enumerate(files, 1):
        relative = path.relative_to(corpus)
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception as error:
            failed.append((str(relative), f"读取失败：{error}"))
            continue

        frontmatter, body = split_frontmatter(raw)
        if path.suffix.lower() == ".mdx":
            body = clean_mdx(body)

        content = normalize_text(body)
        if not content:
            failed.append((str(relative), "清洗后内容为空"))
            continue

        title = pick_title(frontmatter, body, path.stem)
        title = unique_title(title, relative, used_titles)

        try:
            chunks = chunk_text(content)
            if hasattr(embedder, "embed_many"):
                embedder.embed_many([chunk.content for chunk in chunks])

            document = create_document(
                title=title,
                source_name=str(relative).replace("\\", "/"),
                content_type="text/markdown",
                content=content,
                db_path=DB_PATH,
            )
            replace_document_chunks(
                document_id=document["id"],
                chunks=chunks,
                embedder=embedder,
                db_path=DB_PATH,
            )
        except Exception as error:
            failed.append((str(relative), f"导入失败：{error}"))
            continue

        sections = [s.strip() for s in H2_RE.findall(body)][:2]
        rows.append(
            {
                "file": str(relative).replace("\\", "/"),
                "title": title,
                "chars": len(content),
                "chunks": len(chunks),
                "sections": "、".join(sections) if sections else "",
            }
        )
        print(
            f"[{index:2d}/{len(files)}] {title[:30]:<30} "
            f"{len(content):>6} 字 {len(chunks):>3} 块  ({path.name})"
        )

    elapsed = time.perf_counter() - started
    print("=" * 68)
    print(f"成功 {len(rows)} 篇 / 失败 {len(failed)} 篇")
    print(f"总字数 {sum(r['chars'] for r in rows):,}    总切块 {sum(r['chunks'] for r in rows)}")
    print(f"耗时 {elapsed:.1f} 秒")

    if failed:
        print("\n失败清单：")
        for name, reason in failed:
            print(f"  - {name}: {reason}")

    with get_connection(DB_PATH) as connection:
        doc_count = connection.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]
        chunk_count = connection.execute("SELECT COUNT(*) AS c FROM chunks").fetchone()["c"]
    print(f"\n库内现状：documents={doc_count}   chunks={chunk_count}")

    if rows and not args.no_manifest:
        manifest = write_manifest(corpus, rows, embedder_name)
        print(f"语料清单已生成：{manifest}")

    if doc_count < 10:
        print("\n[提醒] 文档少于 10 篇，评测仍然不够有说服力，建议补到 15 篇以上。")

    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
