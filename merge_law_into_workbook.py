from __future__ import annotations

import argparse
import csv
import re
import zipfile
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import import_to_neo4j as xlsx_utils


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ET.register_namespace("", MAIN_NS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge extracted law CSV rows into the law_article sheet of an existing xlsx workbook."
    )
    parser.add_argument("--xlsx", required=True, help="Path to the source xlsx workbook.")
    parser.add_argument("--csv", required=True, help="Path to the extracted law CSV.")
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the merged xlsx workbook to create.",
    )
    return parser.parse_args()


def excel_serial_to_date_text(value: str) -> str:
    text = (value or "").strip()
    if not re.fullmatch(r"\d{5}", text):
        return text
    serial = int(text)
    if serial < 30000 or serial > 60000:
        return text
    base = datetime(1899, 12, 30)
    return (base + timedelta(days=serial)).strftime("%Y-%m-%d")


def load_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader)


def next_article_index(existing_rows: list[dict[str, str]]) -> int:
    max_index = 0
    for row in existing_rows:
        article_id = (row.get("article_id") or "").strip()
        if article_id.startswith("A") and article_id[1:].isdigit():
            max_index = max(max_index, int(article_id[1:]))
    return max_index + 1


def merge_rows(
    existing_rows: list[dict[str, str]],
    extracted_rows: list[dict[str, str]],
    target_headers: list[str],
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    existing_keys: set[tuple[str, str]] = set()

    for row in existing_rows:
        normalized = {header: row.get(header, "") for header in target_headers}
        normalized["effective_date"] = excel_serial_to_date_text(
            normalized.get("effective_date", "")
        )
        merged.append(normalized)
        existing_keys.add(
            (
                normalized.get("law_name", "").strip(),
                normalized.get("article_no", "").strip(),
            )
        )

    article_index = next_article_index(existing_rows)

    for row in extracted_rows:
        key = (
            (row.get("law_name") or "").strip(),
            (row.get("article_no") or "").strip(),
        )
        if key in existing_keys:
            continue

        normalized = {header: "" for header in target_headers}
        for header in target_headers:
            if header == "article_id":
                continue
            normalized[header] = row.get(header, "")

        normalized["article_id"] = f"A{article_index:03d}"
        article_index += 1

        if not normalized.get("source_url"):
            normalized["source_url"] = (
                "https://jtgl.beijing.gov.cn/jgj/jgxx/flfg/fl/205308/index.html"
            )
        if not normalized.get("remark"):
            normalized["remark"] = "从法规原文docx自动抽取"

        merged.append(normalized)
        existing_keys.add(key)

    return merged


def col_letter(index: int) -> str:
    result = []
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result.append(chr(ord("A") + remainder))
    return "".join(reversed(result))


def make_inline_cell(cell_ref: str, value: str) -> ET.Element:
    cell = ET.Element(f"{{{MAIN_NS}}}c", {"r": cell_ref, "t": "inlineStr"})
    is_node = ET.SubElement(cell, f"{{{MAIN_NS}}}is")
    text_node = ET.SubElement(is_node, f"{{{MAIN_NS}}}t")
    if value.startswith(" ") or value.endswith(" ") or "\n" in value:
        text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text_node.text = value
    return cell


def build_sheet_xml(headers: list[str], rows: list[dict[str, str]]) -> bytes:
    worksheet = ET.Element(f"{{{MAIN_NS}}}worksheet")

    last_cell = f"{col_letter(len(headers))}{len(rows) + 1}"
    ET.SubElement(worksheet, f"{{{MAIN_NS}}}dimension", {"ref": f"A1:{last_cell}"})

    sheet_views = ET.SubElement(worksheet, f"{{{MAIN_NS}}}sheetViews")
    sheet_view = ET.SubElement(
        sheet_views,
        f"{{{MAIN_NS}}}sheetView",
        {"workbookViewId": "0", "tabSelected": "1"},
    )
    ET.SubElement(
        sheet_view,
        f"{{{MAIN_NS}}}selection",
        {"activeCell": "A1", "sqref": "A1"},
    )

    ET.SubElement(
        worksheet,
        f"{{{MAIN_NS}}}sheetFormatPr",
        {"defaultRowHeight": "15"},
    )

    sheet_data = ET.SubElement(worksheet, f"{{{MAIN_NS}}}sheetData")

    header_row = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", {"r": "1"})
    for index, header in enumerate(headers, start=1):
        header_row.append(make_inline_cell(f"{col_letter(index)}1", header))

    for row_index, row in enumerate(rows, start=2):
        row_node = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", {"r": str(row_index)})
        for col_index, header in enumerate(headers, start=1):
            value = row.get(header, "")
            if value == "":
                continue
            row_node.append(make_inline_cell(f"{col_letter(col_index)}{row_index}", value))

    ET.SubElement(
        worksheet,
        f"{{{MAIN_NS}}}pageMargins",
        {
            "left": "0.7",
            "right": "0.7",
            "top": "0.75",
            "bottom": "0.75",
            "header": "0.3",
            "footer": "0.3",
        },
    )

    return ET.tostring(worksheet, encoding="utf-8", xml_declaration=True)


def main() -> int:
    args = parse_args()
    xlsx_path = Path(args.xlsx).resolve()
    csv_path = Path(args.csv).resolve()
    output_path = Path(args.output).resolve()

    if not xlsx_path.exists():
        raise FileNotFoundError(f"Xlsx file not found: {xlsx_path}")
    if not csv_path.exists():
        raise FileNotFoundError(f"Csv file not found: {csv_path}")

    law_rows, _, _, _ = xlsx_utils.load_all_xlsx(xlsx_path)
    if not law_rows:
        raise ValueError("The law_article sheet is empty.")

    headers = list(law_rows[0].keys())
    extracted_rows = load_csv_rows(csv_path)
    merged_rows = merge_rows(law_rows, extracted_rows, headers)

    with zipfile.ZipFile(xlsx_path, "r") as src_zip:
        sheet_map = xlsx_utils.read_workbook_sheet_map(src_zip)
        law_sheet_path = sheet_map["law_article"]
        new_sheet_xml = build_sheet_xml(headers, merged_rows)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as dst_zip:
            for item in src_zip.infolist():
                data = src_zip.read(item.filename)
                if item.filename == law_sheet_path:
                    data = new_sheet_xml
                dst_zip.writestr(item, data)

    print(f"Original law_article rows: {len(law_rows)}")
    print(f"Extracted law rows: {len(extracted_rows)}")
    print(f"Merged law_article rows: {len(merged_rows)}")
    print(f"Output workbook: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
