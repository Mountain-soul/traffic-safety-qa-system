from __future__ import annotations

import argparse
import csv
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
CHINESE_NUM = "零〇一二三四五六七八九十百千万两"
CHAPTER_RE = re.compile(rf"^第[{CHINESE_NUM}]+章")
SECTION_RE = re.compile(rf"^第[{CHINESE_NUM}]+节")
ARTICLE_RE = re.compile(rf"^(第[{CHINESE_NUM}0-9]+条)\s*(.*)$")

FIELDNAMES = [
    "law_id",
    "law_name",
    "law_level",
    "chapter",
    "section",
    "article_id",
    "article_no",
    "article_title",
    "article_text",
    "effective_date",
    "source_url",
    "remark",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract Chinese law articles from docx/txt files.")
    parser.add_argument("--input", required=True, help="A docx/txt file or a folder containing them.")
    parser.add_argument(
        "--output",
        default=str(Path("generated") / "extracted_law_articles.csv"),
        help="Output CSV path.",
    )
    parser.add_argument("--law-id", default="LNEW")
    parser.add_argument("--law-name", default="", help="If omitted, file stem is used.")
    parser.add_argument("--law-level", default="法规")
    parser.add_argument("--effective-date", default="")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--remark", default="从法规文档自动抽取，建议人工复核")
    return parser.parse_args()


def clean_line(text: str) -> str:
    text = text.replace("\u3000", " ").replace("\ufeff", "").strip()
    return re.sub(r"[ \t]+", " ", text)


def read_docx_paragraphs(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))

    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", WORD_NS):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", WORD_NS)]
        line = clean_line("".join(texts))
        if line:
            paragraphs.append(line)
    return paragraphs


def read_txt_paragraphs(path: Path) -> list[str]:
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return [clean_line(line) for line in path.read_text(encoding=encoding).splitlines() if clean_line(line)]
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"Cannot decode {path}")


def read_paragraphs(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return read_docx_paragraphs(path)
    if suffix == ".txt":
        return read_txt_paragraphs(path)
    raise ValueError(f"Unsupported file type: {path}")


def iter_input_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    files: list[Path] = []
    for pattern in ("*.docx", "*.txt"):
        files.extend(input_path.rglob(pattern))
    return sorted(files)


def looks_like_title_tail(text: str) -> bool:
    if not text or len(text) > 18:
        return False
    return not any(mark in text for mark in "，。；：！？、,.;:!?")


def build_rows_for_file(path: Path, args: argparse.Namespace, file_index: int) -> list[dict[str, str]]:
    paragraphs = read_paragraphs(path)
    law_name = args.law_name or path.stem
    law_id = args.law_id if args.law_id != "LNEW" else f"LNEW{file_index:02d}"

    rows: list[dict[str, str]] = []
    chapter = ""
    section = ""
    current_no = ""
    current_title = ""
    current_lines: list[str] = []
    article_index = 0

    def flush() -> None:
        nonlocal article_index, current_no, current_title, current_lines
        if not current_no:
            return
        article_index += 1
        rows.append(
            {
                "law_id": law_id,
                "law_name": law_name,
                "law_level": args.law_level,
                "chapter": chapter,
                "section": section,
                "article_id": f"{law_id}_A{article_index:03d}",
                "article_no": current_no,
                "article_title": current_title,
                "article_text": "\n".join(current_lines).strip(),
                "effective_date": args.effective_date,
                "source_url": args.source_url,
                "remark": args.remark,
            }
        )
        current_no = ""
        current_title = ""
        current_lines = []

    for paragraph in paragraphs:
        if paragraph in {law_name, "目录"}:
            continue

        if CHAPTER_RE.match(paragraph):
            flush()
            chapter = paragraph
            section = ""
            continue

        if SECTION_RE.match(paragraph):
            flush()
            section = paragraph
            continue

        article_match = ARTICLE_RE.match(paragraph)
        if article_match:
            flush()
            current_no = article_match.group(1)
            tail = article_match.group(2).strip()
            current_title = tail if looks_like_title_tail(tail) else ""
            current_lines = [] if current_title else ([tail] if tail else [])
            continue

        if current_no:
            current_lines.append(paragraph)

    flush()
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    all_rows: list[dict[str, str]] = []
    files = iter_input_files(input_path)
    for index, file_path in enumerate(files, start=1):
        rows = build_rows_for_file(file_path, args, index)
        all_rows.extend(rows)
        print(f"{file_path.name}: {len(rows)} articles")

    write_csv(output_path, all_rows)
    print(f"Total articles: {len(all_rows)}")
    print(f"Output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
