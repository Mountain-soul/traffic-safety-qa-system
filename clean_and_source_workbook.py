from __future__ import annotations

import argparse
import csv
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import import_to_neo4j as xlsx_utils
from import_to_neo4j import clean_text


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ET.register_namespace("", MAIN_NS)

SHEET_NAMES = ["law_article", "violation_penalty", "road_sign", "accident_case"]
SOURCE_COLUMNS = ["source_name", "source_type", "source_note", "quality_flag"]

DEDUP_KEYS = {
    "law_article": ["law_name", "article_no", "article_text"],
    "violation_penalty": [
        "violation_name",
        "violation_type",
        "penalty_type",
        "penalty_content",
        "fine_range",
        "score_value",
        "detention",
        "license_action",
        "applicable_vehicle",
    ],
    "road_sign": ["sign_name", "meaning", "applicable_scene", "standard_no"],
    "accident_case": ["case_name", "date", "province", "city", "place", "cause", "casualties"],
}

COMBINE_FIELDS = {"remark", "source_url", "source_name", "source_note", "suggestion"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean duplicated rows and add traceable source fields to the traffic KG workbook."
    )
    parser.add_argument(
        "--xlsx",
        default="",
        help="Source workbook. Defaults to import_to_neo4j.detect_default_xlsx().",
    )
    parser.add_argument(
        "--output-xlsx",
        default=str(Path("generated") / "交通问答系统的数据_清洗溯源版.xlsx"),
        help="Cleaned output workbook.",
    )
    parser.add_argument(
        "--report",
        default=str(Path("generated") / "data_quality_cleaning_report.csv"),
        help="CSV report path.",
    )
    return parser.parse_args()


def col_letter(index: int) -> str:
    result: list[str] = []
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
        sheet_views, f"{{{MAIN_NS}}}sheetView", {"workbookViewId": "0", "tabSelected": "1"}
    )
    ET.SubElement(sheet_view, f"{{{MAIN_NS}}}selection", {"activeCell": "A1", "sqref": "A1"})
    ET.SubElement(worksheet, f"{{{MAIN_NS}}}sheetFormatPr", {"defaultRowHeight": "15"})

    sheet_data = ET.SubElement(worksheet, f"{{{MAIN_NS}}}sheetData")
    header_row = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", {"r": "1"})
    for col_idx, header in enumerate(headers, start=1):
        header_row.append(make_inline_cell(f"{col_letter(col_idx)}1", header))

    for row_idx, row in enumerate(rows, start=2):
        row_node = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", {"r": str(row_idx)})
        for col_idx, header in enumerate(headers, start=1):
            value = row.get(header, "")
            if value:
                row_node.append(make_inline_cell(f"{col_letter(col_idx)}{row_idx}", value))

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


def excel_serial_to_date_text(value: str) -> str:
    text = clean_text(value)
    if not re.fullmatch(r"\d{5}(?:\.0)?", text):
        return text
    serial = int(float(text))
    if serial < 30000 or serial > 60000:
        return text
    base = datetime(1899, 12, 30)
    return (base + timedelta(days=serial)).strftime("%Y-%m-%d")


def normalize_key_value(value: str) -> str:
    text = clean_text(value)
    text = re.sub(r"\s+", "", text)
    text = text.replace("；", ";").replace("，", ",")
    return text.lower()


def append_unique(existing: str, incoming: str) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for raw in [existing, incoming]:
        for item in re.split(r"[;；|、]+", clean_text(raw)):
            cleaned = clean_text(item)
            key = normalize_key_value(cleaned)
            if not cleaned or key in seen:
                continue
            seen.add(key)
            values.append(cleaned)
    return "；".join(values)


def prefer_value(field: str, existing: str, incoming: str) -> str:
    old = clean_text(existing)
    new = clean_text(incoming)
    if not old:
        return new
    if not new or old == new:
        return old
    if field in COMBINE_FIELDS:
        return append_unique(old, new)
    if old in {"无", "否", "未注明", "待补充"} and new not in {"无", "否", "未注明", "待补充"}:
        return new
    if len(new) > len(old) * 1.6 and field.endswith(("text", "content", "cause")):
        return new
    return old


def infer_source(table_name: str, row: dict[str, str]) -> tuple[str, str, str]:
    if table_name == "law_article":
        law_name = clean_text(row.get("law_name"))
        if "实施条例" in law_name:
            return (
                "中华人民共和国道路交通安全法实施条例_20171007.docx",
                "法规文本",
                "由 data_sources 中法规文档抽取，并与公开法规资料核对。",
            )
        if "道路交通安全法" in law_name:
            return (
                "中华人民共和国道路交通安全法_20210429.docx",
                "法规文本",
                "由 data_sources 中法规文档抽取，并与公开法规资料核对。",
            )
        return (law_name or "公开法规资料", "法规文本", "由公开法规资料整理。")

    if table_name == "violation_penalty":
        return (
            "交通法规、记分规则与处罚规则整理",
            "法规规则整理",
            "由道路交通安全相关法规、记分规则和项目扩充模板整理，具体裁量标准建议后续人工复核。",
        )

    if table_name == "road_sign":
        return (
            "GB 5768.2-2022 道路交通标志和标线 第2部分：道路交通标志",
            "国家标准/标志资料整理",
            "依据道路交通标志国家标准及项目扩充规则整理。",
        )

    row_text = " ".join(clean_text(row.get(field)) for field in ["case_name", "province", "city", "place", "remark"])
    if "麻阳" in row_text or "3·20" in row_text or "3.20" in row_text:
        return (
            "麻阳县“3·20”较大道路交通事故调查报告.doc",
            "事故调查报告",
            "由 data_sources 中事故调查报告抽取。",
        )
    return (
        "data_sources 交通事故案例文档汇编",
        "事故案例文本/扩充整理",
        "由 data_sources 内事故案例文档、PDF 和项目扩充规则整理，建议后续继续补充官方链接。",
    )


def infer_quality_flag(row: dict[str, str]) -> str:
    marker_text = " ".join(clean_text(row.get(field)) for field in ["remark", "source_url", "source_note"])
    if "待复核" in marker_text or "扩充" in marker_text or "自动" in marker_text:
        return "自动扩充待人工复核"
    if "local:" in marker_text or "data_sources" in marker_text:
        return "本地文档来源待补官方链接"
    return "来源已补全"


def normalize_row(table_name: str, headers: list[str], row: dict[str, str]) -> dict[str, str]:
    normalized = {header: clean_text(row.get(header, "")) for header in headers}
    if table_name == "accident_case":
        normalized["date"] = excel_serial_to_date_text(normalized.get("date", ""))

    source_name, source_type, source_note = infer_source(table_name, normalized)
    if not normalized.get("source_name"):
        normalized["source_name"] = source_name
    if not normalized.get("source_type"):
        normalized["source_type"] = source_type
    if not normalized.get("source_note"):
        normalized["source_note"] = source_note

    if not normalized.get("source_url") and table_name == "accident_case":
        normalized["source_url"] = "local:data_sources/交通事故案例文档汇编"
    elif not normalized.get("source_url") and table_name == "road_sign":
        normalized["source_url"] = "https://std.samr.gov.cn/"
    elif not normalized.get("source_url") and table_name in {"law_article", "violation_penalty"}:
        normalized["source_url"] = "local:data_sources/法规资料整理"

    normalized["quality_flag"] = infer_quality_flag(normalized)
    return normalized


def row_key(table_name: str, row: dict[str, str]) -> tuple[str, ...]:
    fields = DEDUP_KEYS[table_name]
    key = tuple(normalize_key_value(row.get(field, "")) for field in fields)
    if any(key):
        return key
    id_fields = {
        "law_article": "article_id",
        "violation_penalty": "violation_id",
        "road_sign": "sign_id",
        "accident_case": "case_id",
    }
    return (normalize_key_value(row.get(id_fields[table_name], "")),)


def clean_table(
    table_name: str,
    rows: list[dict[str, str]],
) -> tuple[list[str], list[dict[str, str]], dict[str, int]]:
    if not rows:
        return SOURCE_COLUMNS[:], [], {
            "before_rows": 0,
            "after_rows": 0,
            "removed_duplicates": 0,
            "blank_source_url_before": 0,
            "blank_source_url_after": 0,
            "blank_source_name_after": 0,
        }

    headers = list(rows[0].keys())
    for column in SOURCE_COLUMNS:
        if column not in headers:
            headers.append(column)

    blank_source_before = sum(1 for row in rows if not clean_text(row.get("source_url")))
    merged_by_key: dict[tuple[str, ...], dict[str, str]] = {}
    order: list[tuple[str, ...]] = []

    for raw_row in rows:
        row = normalize_row(table_name, headers, raw_row)
        key = row_key(table_name, row)
        if key not in merged_by_key:
            merged_by_key[key] = row
            order.append(key)
            continue
        current = merged_by_key[key]
        for header in headers:
            current[header] = prefer_value(header, current.get(header, ""), row.get(header, ""))
        current["quality_flag"] = infer_quality_flag(current)

    cleaned_rows = [merged_by_key[key] for key in order]
    stats = {
        "before_rows": len(rows),
        "after_rows": len(cleaned_rows),
        "removed_duplicates": len(rows) - len(cleaned_rows),
        "blank_source_url_before": blank_source_before,
        "blank_source_url_after": sum(1 for row in cleaned_rows if not clean_text(row.get("source_url"))),
        "blank_source_name_after": sum(1 for row in cleaned_rows if not clean_text(row.get("source_name"))),
    }
    return headers, cleaned_rows, stats


def write_workbook(
    source_xlsx: Path,
    output_xlsx: Path,
    sheet_payloads: dict[str, tuple[list[str], list[dict[str, str]]]],
) -> None:
    with zipfile.ZipFile(source_xlsx, "r") as src_zip:
        sheet_map = xlsx_utils.read_workbook_sheet_map(src_zip)
        xml_payloads = {
            sheet_map[sheet_name]: build_sheet_xml(headers, rows)
            for sheet_name, (headers, rows) in sheet_payloads.items()
        }

        output_xlsx.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_xlsx, "w", compression=zipfile.ZIP_DEFLATED) as dst_zip:
            for item in src_zip.infolist():
                data = src_zip.read(item.filename)
                if item.filename in xml_payloads:
                    data = xml_payloads[item.filename]
                dst_zip.writestr(item, data)


def write_report(report_path: Path, stats_by_sheet: dict[str, dict[str, int]]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sheet",
        "before_rows",
        "after_rows",
        "removed_duplicates",
        "blank_source_url_before",
        "blank_source_url_after",
        "blank_source_name_after",
    ]
    with report_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for sheet_name in SHEET_NAMES:
            row = {"sheet": sheet_name}
            row.update(stats_by_sheet[sheet_name])
            writer.writerow(row)


def main() -> int:
    args = parse_args()
    source_xlsx = Path(args.xlsx).resolve() if args.xlsx else xlsx_utils.detect_default_xlsx()
    if source_xlsx is None:
        raise FileNotFoundError("No default workbook found. Pass --xlsx explicitly.")

    output_xlsx = Path(args.output_xlsx).resolve()
    report_path = Path(args.report).resolve()

    with zipfile.ZipFile(source_xlsx) as zip_file:
        shared_strings = xlsx_utils.read_shared_strings(zip_file)
        sheet_map = xlsx_utils.read_workbook_sheet_map(zip_file)
        raw_tables = {
            sheet_name: xlsx_utils.read_xlsx_sheet(zip_file, sheet_name, shared_strings, sheet_map)
            for sheet_name in SHEET_NAMES
        }

    sheet_payloads: dict[str, tuple[list[str], list[dict[str, str]]]] = {}
    stats_by_sheet: dict[str, dict[str, int]] = {}
    for sheet_name, rows in raw_tables.items():
        headers, cleaned_rows, stats = clean_table(sheet_name, rows)
        sheet_payloads[sheet_name] = (headers, cleaned_rows)
        stats_by_sheet[sheet_name] = stats

    write_workbook(source_xlsx, output_xlsx, sheet_payloads)
    write_report(report_path, stats_by_sheet)

    print(f"Source workbook: {source_xlsx}")
    print(f"Cleaned workbook: {output_xlsx}")
    print(f"Report: {report_path}")
    for sheet_name in SHEET_NAMES:
        stats = stats_by_sheet[sheet_name]
        print(
            f"{sheet_name}: {stats['before_rows']} -> {stats['after_rows']}, "
            f"removed_duplicates={stats['removed_duplicates']}, "
            f"blank_source_url={stats['blank_source_url_before']} -> {stats['blank_source_url_after']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
