from __future__ import annotations

import argparse
import csv
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import import_to_neo4j as xlsx_utils


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ET.register_namespace("", MAIN_NS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Round 2 mass expansion based on the first expanded workbook."
    )
    parser.add_argument(
        "--xlsx",
        default=str(Path("generated") / "交通问答系统的数据_大规模扩充版.xlsx"),
        help="Source workbook path.",
    )
    parser.add_argument(
        "--output-xlsx",
        default=str(Path("generated") / "交通问答系统的数据_第二轮大规模扩充版.xlsx"),
        help="Output workbook path.",
    )
    parser.add_argument(
        "--road-sign-csv",
        default=str(Path("generated") / "road_sign_mass_expand_round2.csv"),
        help="Output CSV for round2 road signs.",
    )
    parser.add_argument(
        "--accident-case-csv",
        default=str(Path("generated") / "accident_case_mass_expand_round2.csv"),
        help="Output CSV for round2 accident cases.",
    )
    parser.add_argument(
        "--violation-csv",
        default=str(Path("generated") / "violation_penalty_mass_expand_round2.csv"),
        help="Output CSV for round2 violations.",
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
    ET.SubElement(
        sheet_view, f"{{{MAIN_NS}}}selection", {"activeCell": "A1", "sqref": "A1"}
    )
    ET.SubElement(worksheet, f"{{{MAIN_NS}}}sheetFormatPr", {"defaultRowHeight": "15"})

    sheet_data = ET.SubElement(worksheet, f"{{{MAIN_NS}}}sheetData")
    header_row = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", {"r": "1"})
    for i, header in enumerate(headers, start=1):
        header_row.append(make_inline_cell(f"{col_letter(i)}1", header))

    for row_idx, row in enumerate(rows, start=2):
        row_node = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", {"r": str(row_idx)})
        for col_idx, header in enumerate(headers, start=1):
            value = row.get(header, "")
            if value != "":
                row_node.append(make_inline_cell(f"{col_letter(col_idx)}{row_idx}", value))

    ET.SubElement(
        worksheet,
        f"{{{MAIN_NS}}}pageMargins",
        {"left": "0.7", "right": "0.7", "top": "0.75", "bottom": "0.75", "header": "0.3", "footer": "0.3"},
    )
    return ET.tostring(worksheet, encoding="utf-8", xml_declaration=True)


def next_numeric_id(rows: list[dict[str, str]], field: str, prefix: str) -> int:
    max_id = 0
    for row in rows:
        value = (row.get(field) or "").strip()
        if value.startswith(prefix) and value[len(prefix):].isdigit():
            max_id = max(max_id, int(value[len(prefix):]))
    return max_id + 1


def write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def merge_rows(
    existing: list[dict[str, str]],
    additions: list[dict[str, str]],
    headers: list[str],
    unique_field: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    existing_values = {(row.get(unique_field) or "").strip() for row in existing}
    new_rows: list[dict[str, str]] = []
    for row in additions:
        unique_value = (row.get(unique_field) or "").strip()
        if not unique_value or unique_value in existing_values:
            continue
        new_rows.append({header: row.get(header, "") for header in headers})
        existing_values.add(unique_value)

    merged = [{header: row.get(header, "") for header in headers} for row in existing]
    merged.extend(new_rows)
    return merged, new_rows


def clone_sign_rows(rows: list[dict[str, str]], start_id: int) -> list[dict[str, str]]:
    scene_suffixes = [
        "学校周边",
        "城市主干道",
        "高速公路入口",
        "山区弯道路段",
        "桥梁路段",
        "施工导改区",
        "医院周边",
        "城郊结合部",
    ]
    additions: list[dict[str, str]] = []
    current_id = start_id
    for index, row in enumerate(rows):
        for suffix in scene_suffixes:
            name = f"{row.get('sign_name', '')}扩展{index % 6 + 1}-{suffix}"
            additions.append(
                {
                    "sign_id": f"S{current_id:03d}",
                    "sign_name": name,
                    "sign_category": row.get("sign_category", ""),
                    "sub_category": row.get("sub_category", ""),
                    "shape": row.get("shape", ""),
                    "color": row.get("color", ""),
                    "meaning": f"{row.get('meaning', '')}，适用于{suffix}",
                    "applicable_scene": suffix,
                    "standard_no": row.get("standard_no", "GB 5768.2-2022"),
                    "image_ref": f"s{current_id:03d}_{name}.png",
                    "source_url": row.get("source_url", "https://std.samr.gov.cn/"),
                    "remark": "第二轮自动扩充草案，建议人工复核",
                }
            )
            current_id += 1
    return additions


def clone_case_rows(rows: list[dict[str, str]], start_id: int) -> list[dict[str, str]]:
    city_suffixes = ["东城区", "西城区", "新区", "开发区", "高新区"]
    additions: list[dict[str, str]] = []
    current_id = start_id
    for index, row in enumerate(rows):
        for offset, suffix in enumerate(city_suffixes, start=1):
            base_city = row.get("city", "") or "某市"
            case_name = f"{base_city}{suffix}{row.get('case_name', '')}扩展{offset}"
            additions.append(
                {
                    "case_id": f"C{current_id:03d}",
                    "case_name": case_name,
                    "date": row.get("date", ""),
                    "province": row.get("province", ""),
                    "city": base_city,
                    "place": f"{base_city}{suffix}{row.get('place', '')}",
                    "road_name": row.get("road_name", ""),
                    "weather": row.get("weather", ""),
                    "road_condition": row.get("road_condition", ""),
                    "vehicle_type": row.get("vehicle_type", ""),
                    "behavior": row.get("behavior", ""),
                    "cause": row.get("cause", ""),
                    "casualties": row.get("casualties", ""),
                    "responsibility": row.get("responsibility", ""),
                    "violation_name": row.get("violation_name", ""),
                    "suggestion": row.get("suggestion", ""),
                    "source_url": row.get("source_url", "https://www.mem.gov.cn/"),
                    "remark": "第二轮自动扩充草案，建议人工复核",
                }
            )
            current_id += 1
            if len(additions) >= 600:
                return additions
    return additions


def clone_violation_rows(
    rows: list[dict[str, str]],
    start_id: int,
) -> list[dict[str, str]]:
    vehicle_suffixes = ["机动车", "小型客车", "大型客车", "货车", "摩托车", "非机动车"]
    additions: list[dict[str, str]] = []
    current_id = start_id
    for index, row in enumerate(rows):
        for offset, vehicle in enumerate(vehicle_suffixes, start=1):
            violation_name = f"{row.get('violation_name', '')}扩展{offset}"
            additions.append(
                {
                    "violation_id": f"V{current_id:03d}",
                    "violation_name": violation_name,
                    "violation_type": row.get("violation_type", ""),
                    "related_article_id": row.get("related_article_id", ""),
                    "penalty_type": row.get("penalty_type", ""),
                    "penalty_content": row.get("penalty_content", ""),
                    "fine_range": row.get("fine_range", ""),
                    "score_value": row.get("score_value", ""),
                    "detention": row.get("detention", ""),
                    "license_action": row.get("license_action", ""),
                    "applicable_vehicle": vehicle,
                    "source_url": row.get("source_url", "https://flk.npc.gov.cn/"),
                    "remark": "第二轮自动扩充草案，建议人工复核",
                }
            )
            current_id += 1
            if len(additions) >= 700:
                return additions
    return additions


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


def main() -> int:
    args = parse_args()
    xlsx_path = Path(args.xlsx).resolve()
    output_xlsx = Path(args.output_xlsx).resolve()
    road_sign_csv = Path(args.road_sign_csv).resolve()
    accident_case_csv = Path(args.accident_case_csv).resolve()
    violation_csv = Path(args.violation_csv).resolve()

    with zipfile.ZipFile(xlsx_path) as zip_file:
        shared_strings = xlsx_utils.read_shared_strings(zip_file)
        sheet_map = xlsx_utils.read_workbook_sheet_map(zip_file)
        sign_rows = xlsx_utils.read_xlsx_sheet(zip_file, "road_sign", shared_strings, sheet_map)
        case_rows = xlsx_utils.read_xlsx_sheet(zip_file, "accident_case", shared_strings, sheet_map)
        violation_rows = xlsx_utils.read_xlsx_sheet(zip_file, "violation_penalty", shared_strings, sheet_map)

    sign_headers = list(sign_rows[0].keys())
    case_headers = list(case_rows[0].keys())
    violation_headers = list(violation_rows[0].keys())

    sign_candidates = clone_sign_rows(sign_rows, next_numeric_id(sign_rows, "sign_id", "S"))
    case_candidates = clone_case_rows(case_rows, next_numeric_id(case_rows, "case_id", "C"))
    violation_candidates = clone_violation_rows(
        violation_rows, next_numeric_id(violation_rows, "violation_id", "V")
    )

    merged_sign_rows, new_sign_rows = merge_rows(sign_rows, sign_candidates, sign_headers, "sign_name")
    merged_case_rows, new_case_rows = merge_rows(case_rows, case_candidates, case_headers, "case_name")
    merged_violation_rows, new_violation_rows = merge_rows(
        violation_rows, violation_candidates, violation_headers, "violation_name"
    )

    write_csv(road_sign_csv, sign_headers, new_sign_rows)
    write_csv(accident_case_csv, case_headers, new_case_rows)
    write_csv(violation_csv, violation_headers, new_violation_rows)

    write_workbook(
        xlsx_path,
        output_xlsx,
        {
            "road_sign": (sign_headers, merged_sign_rows),
            "accident_case": (case_headers, merged_case_rows),
            "violation_penalty": (violation_headers, merged_violation_rows),
        },
    )

    print(f"Added road_sign rows: {len(new_sign_rows)}")
    print(f"Added accident_case rows: {len(new_case_rows)}")
    print(f"Added violation_penalty rows: {len(new_violation_rows)}")
    print(f"Output workbook: {output_xlsx}")
    print(f"Updated road_sign total: {len(merged_sign_rows)}")
    print(f"Updated accident_case total: {len(merged_case_rows)}")
    print(f"Updated violation_penalty total: {len(merged_violation_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
