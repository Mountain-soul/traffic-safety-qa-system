from __future__ import annotations

import argparse
import csv
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

CHAPTER_RE = re.compile(r"^第[一二三四五六七八九十百零]+章")
SECTION_RE = re.compile(r"^第[一二三四五六七八九十百零]+节")
ARTICLE_RE = re.compile(r"^(第[一二三四五六七八九十百零]+条)[\u3000 ]*(.*)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract law articles from a .docx file into CSV."
    )
    parser.add_argument("--docx", required=True, help="Path to the source docx file.")
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the output CSV file.",
    )
    parser.add_argument(
        "--law-id",
        default="L001",
        help="Law ID prefix written into the output, default: %(default)s",
    )
    parser.add_argument(
        "--law-name",
        default="中华人民共和国道路交通安全法",
        help="Law name written into the output.",
    )
    parser.add_argument(
        "--law-level",
        default="法律",
        help="Law level written into the output, default: %(default)s",
    )
    parser.add_argument(
        "--effective-date",
        default="2021-04-29",
        help="Effective date written into the output, default: %(default)s",
    )
    parser.add_argument(
        "--source-url",
        default="",
        help="Optional source url written into the output.",
    )
    parser.add_argument(
        "--remark",
        default="从法规原文docx自动抽取",
        help="Optional remark written into the output.",
    )
    return parser.parse_args()


def extract_paragraphs(docx_path: Path) -> list[str]:
    with zipfile.ZipFile(docx_path) as zf:
        document_xml = ET.fromstring(zf.read("word/document.xml"))

    paragraphs: list[str] = []
    for paragraph in document_xml.findall(".//w:p", NS):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", NS)]
        text = "".join(texts).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def normalize_title(title: str) -> str:
    cleaned = title.replace("\u3000", " ").strip()
    return cleaned or ""


def infer_article_title(raw_tail: str) -> str:
    candidate = normalize_title(raw_tail)
    if not candidate:
        return ""
    # Most Chinese law articles do not have standalone titles after the article number.
    # If the tail already looks like a full sentence, keep the title empty.
    if any(mark in candidate for mark in "，。；：！？"):
        return ""
    if len(candidate) > 20:
        return ""
    return candidate


def extract_article_body(raw_tail: str, article_title: str) -> str:
    tail = normalize_title(raw_tail)
    if not tail:
        return ""
    if article_title and tail.startswith(article_title):
        tail = tail[len(article_title) :].strip()
    return tail


def build_rows(paragraphs: list[str], args: argparse.Namespace) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    chapter = ""
    section = ""
    current_article_no = ""
    current_article_title = ""
    current_article_lines: list[str] = []
    current_first_line_body = ""
    article_index = 0

    def flush_article() -> None:
        nonlocal article_index, current_article_no, current_article_title, current_article_lines, current_first_line_body
        if not current_article_no:
            return
        article_index += 1
        article_id = f"A{article_index:03d}"
        article_body_lines: list[str] = []
        if current_first_line_body:
            article_body_lines.append(current_first_line_body)
        article_body_lines.extend(line for line in current_article_lines if line)
        article_text = "\n".join(article_body_lines).strip()
        rows.append(
            {
                "law_id": args.law_id,
                "law_name": args.law_name,
                "law_level": args.law_level,
                "chapter": chapter,
                "section": section,
                "article_id": article_id,
                "article_no": current_article_no,
                "article_title": current_article_title,
                "article_text": article_text,
                "effective_date": args.effective_date,
                "source_url": args.source_url,
                "remark": args.remark,
            }
        )
        current_article_no = ""
        current_article_title = ""
        current_article_lines = []
        current_first_line_body = ""

    for paragraph in paragraphs:
        if paragraph == "目　　录" or paragraph.startswith("（") or paragraph == args.law_name:
            continue

        if CHAPTER_RE.match(paragraph):
            flush_article()
            chapter = paragraph
            section = ""
            continue

        if SECTION_RE.match(paragraph):
            flush_article()
            section = paragraph
            continue

        article_match = ARTICLE_RE.match(paragraph)
        if article_match:
            flush_article()
            current_article_no = article_match.group(1).strip()
            raw_tail = article_match.group(2)
            current_article_title = infer_article_title(raw_tail)
            current_first_line_body = extract_article_body(raw_tail, current_article_title)
            current_article_lines = []
            continue

        if current_article_no:
            current_article_lines.append(paragraph)

    flush_article()
    return rows


def write_csv(output_path: Path, rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
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
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    docx_path = Path(args.docx).resolve()
    output_path = Path(args.output).resolve()

    if not docx_path.exists():
        raise FileNotFoundError(f"Docx file not found: {docx_path}")

    paragraphs = extract_paragraphs(docx_path)
    rows = build_rows(paragraphs, args)
    write_csv(output_path, rows)

    print(f"Extracted {len(rows)} articles.")
    print(f"Output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
