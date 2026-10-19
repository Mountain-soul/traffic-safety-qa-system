r"""
Import traffic safety knowledge graph data from CSV files into Neo4j.

Expected CSV files:
- law_article.csv
- violation_penalty.csv
- road_sign.csv
- accident_case.csv

Recommended usage:
    pip install neo4j
    python import_to_neo4j.py --uri bolt://localhost:7687 --user neo4j --password your_password --xlsx "C:\\path\\to\\data.xlsx"

You can also set these environment variables instead of passing arguments:
- NEO4J_URI
- NEO4J_USER
- NEO4J_PASSWORD
- NEO4J_DATABASE
"""

from __future__ import annotations

import argparse
import base64
import csv
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


WORKSPACE_DIR = Path(__file__).resolve().parent
LOCAL_ENV_FILES = [
    WORKSPACE_DIR / ".vscode" / "python.env",
    WORKSPACE_DIR / ".env",
]


def load_local_env_files() -> None:
    for env_path in LOCAL_ENV_FILES:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


load_local_env_files()


DEFAULT_FILES = {
    "law_article": "law_article.csv",
    "violation_penalty": "violation_penalty.csv",
    "road_sign": "road_sign.csv",
    "accident_case": "accident_case.csv",
}

DEFAULT_XLSX_CANDIDATES = [
    os.getenv("TRAFFIC_KG_XLSX", ""),
    str(Path("generated") / "交通问答系统的数据_清洗溯源版.xlsx"),
    str(Path("generated") / "交通问答系统的数据_第二轮大规模扩充版.xlsx"),
    str(Path("generated") / "交通问答系统的数据_大规模扩充版.xlsx"),
    str(Path("generated") / "交通问答系统的数据_扩充标志案例版.xlsx"),
    str(Path("generated") / "交通问答系统的数据_合并法规版_二次合并.xlsx"),
    str(
        Path.home()
        / "Desktop"
        / "\u5927\u521b"
        / "\u4ea4\u901a\u95ee\u7b54\u7cfb\u7edf\u7684\u6570\u636e.xlsx"
    ),
]

SUMMARY_LABELS = [
    "Law",
    "Article",
    "Violation",
    "Penalty",
    "RoadSign",
    "AccidentCase",
    "Behavior",
    "Weather",
    "RoadCondition",
    "VehicleType",
    "Suggestion",
    "SignCategory",
    "SignSubCategory",
    "SignShape",
    "SignColor",
    "Scene",
    "Standard",
    "ViolationType",
    "ApplicableVehicle",
    "PenaltyType",
    "LicenseAction",
    "Province",
    "City",
    "Road",
    "CasualtyResult",
    "ResponsibilityType",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import traffic safety CSV data into Neo4j."
    )
    parser.add_argument(
        "--uri",
        default=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        help="Neo4j URI, default: %(default)s",
    )
    parser.add_argument(
        "--user",
        default=os.getenv("NEO4J_USER", "neo4j"),
        help="Neo4j username, default: %(default)s",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("NEO4J_PASSWORD"),
        help="Neo4j password. If omitted, the script will prompt for it.",
    )
    parser.add_argument(
        "--database",
        default=os.getenv("NEO4J_DATABASE", "neo4j"),
        help="Neo4j database name, default: %(default)s",
    )
    parser.add_argument(
        "--data-dir",
        default=".",
        help="Directory containing the four CSV files, default: %(default)s",
    )
    parser.add_argument(
        "--xlsx",
        help="Optional xlsx workbook path. If provided, the script reads sheets named law_article, violation_penalty, road_sign, accident_case.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Rows imported per transaction, default: %(default)s",
    )
    parser.add_argument(
        "--http-uri",
        default=os.getenv("NEO4J_HTTP_URI", "http://localhost:7474"),
        help="Neo4j HTTP endpoint for the built-in fallback client, default: %(default)s",
    )
    return parser.parse_args()


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\ufeff", "").strip()
    text = re.sub(r"[ \t]+", " ", text)
    return text


def dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def split_multi_value(value: str) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    normalized = text
    for sep in ("\uFF0F", "|", ";", "\uFF1B", "\u3001"):
        normalized = normalized.replace(sep, "/")
    parts = [part.strip() for part in normalized.split("/") if part.strip()]
    return dedupe_keep_order(parts)


def build_penalty_key(row: dict[str, str]) -> str:
    pieces = [
        row.get("violation_name", ""),
        row.get("penalty_type", ""),
        row.get("penalty_content", ""),
        row.get("score_value", ""),
    ]
    return "||".join(clean_text(piece) for piece in pieces)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError(f"CSV file has no header row: {path}")

        rows: list[dict[str, str]] = []
        for raw_row in reader:
            row = {key: clean_text(value) for key, value in raw_row.items() if key}
            if any(row.values()):
                rows.append(row)
        return rows


def column_ref_to_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref.upper())
    if not match:
        return -1
    letters = match.group(1)
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def xlsx_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    cell_type = cell.attrib.get("t", "")

    if cell_type == "inlineStr":
        text_parts = [
            node.text or ""
            for node in cell.findall(f".//{namespace}t")
        ]
        return clean_text("".join(text_parts))

    value_node = cell.find(f"{namespace}v")
    if value_node is None or value_node.text is None:
        return ""

    raw_value = value_node.text
    if cell_type == "s":
        try:
            return clean_text(shared_strings[int(raw_value)])
        except (ValueError, IndexError):
            return ""
    return clean_text(raw_value)


def read_shared_strings(zip_file: zipfile.ZipFile) -> list[str]:
    shared_path = "xl/sharedStrings.xml"
    if shared_path not in zip_file.namelist():
        return []

    root = ET.fromstring(zip_file.read(shared_path))
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    values: list[str] = []
    for string_item in root.findall(f"{namespace}si"):
        text_parts = [node.text or "" for node in string_item.findall(f".//{namespace}t")]
        values.append("".join(text_parts))
    return values


def read_workbook_sheet_map(zip_file: zipfile.ZipFile) -> dict[str, str]:
    workbook_root = ET.fromstring(zip_file.read("xl/workbook.xml"))
    rels_root = ET.fromstring(zip_file.read("xl/_rels/workbook.xml.rels"))

    workbook_ns = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    rels_ns = {
        "pkg": "http://schemas.openxmlformats.org/package/2006/relationships"
    }

    rel_id_to_target: dict[str, str] = {}
    for relationship in rels_root.findall("pkg:Relationship", rels_ns):
        rel_id = relationship.attrib.get("Id", "")
        target = relationship.attrib.get("Target", "")
        if rel_id and target:
            normalized_target = target.replace("\\", "/").lstrip("/")
            if not normalized_target.startswith("xl/"):
                normalized_target = f"xl/{normalized_target}"
            rel_id_to_target[rel_id] = normalized_target

    sheet_map: dict[str, str] = {}
    for sheet in workbook_root.findall("main:sheets/main:sheet", workbook_ns):
        name = sheet.attrib.get("name", "")
        rel_id = sheet.attrib.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id",
            "",
        )
        target = rel_id_to_target.get(rel_id)
        if name and target:
            sheet_map[name] = target
    return sheet_map


def rows_from_sheet(zip_file: zipfile.ZipFile, sheet_path: str, shared_strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(zip_file.read(sheet_path))
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows: list[list[str]] = []

    for row in root.findall(".//main:sheetData/main:row", namespace):
        row_values: dict[int, str] = {}
        max_index = -1
        for cell in row.findall("main:c", namespace):
            cell_ref = cell.attrib.get("r", "")
            column_index = column_ref_to_index(cell_ref)
            if column_index < 0:
                column_index = max_index + 1
            row_values[column_index] = xlsx_cell_value(cell, shared_strings)
            max_index = max(max_index, column_index)
        if max_index >= 0:
            rows.append([row_values.get(i, "") for i in range(max_index + 1)])

    return rows


def sheet_rows_to_dicts(sheet_rows: list[list[str]], sheet_name: str) -> list[dict[str, str]]:
    if not sheet_rows:
        raise ValueError(f"Worksheet has no rows: {sheet_name}")

    header = [clean_text(value) for value in sheet_rows[0]]
    if not any(header):
        raise ValueError(f"Worksheet header row is empty: {sheet_name}")

    rows: list[dict[str, str]] = []
    for raw_row in sheet_rows[1:]:
        padded_row = raw_row + [""] * max(0, len(header) - len(raw_row))
        row = {
            header[i]: clean_text(padded_row[i])
            for i in range(len(header))
            if header[i]
        }
        if any(row.values()):
            rows.append(row)
    return rows


def read_xlsx_sheet(zip_file: zipfile.ZipFile, sheet_name: str, shared_strings: list[str], sheet_map: dict[str, str]) -> list[dict[str, str]]:
    if sheet_name not in sheet_map:
        raise ValueError(f"Worksheet not found in xlsx: {sheet_name}")
    sheet_rows = rows_from_sheet(zip_file, sheet_map[sheet_name], shared_strings)
    return sheet_rows_to_dicts(sheet_rows, sheet_name)


def chunked(rows: list[dict[str, object]], batch_size: int) -> Iterable[list[dict[str, object]]]:
    for start in range(0, len(rows), batch_size):
        yield rows[start : start + batch_size]


def detect_default_xlsx() -> Path | None:
    for candidate in DEFAULT_XLSX_CANDIDATES:
        candidate_text = clean_text(candidate)
        if not candidate_text:
            continue
        path = Path(candidate_text).expanduser()
        if path.exists():
            return path.resolve()
    return None


def prepare_case_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    prepared: list[dict[str, object]] = []
    for row in rows:
        prepared_row: dict[str, object] = dict(row)
        prepared_row["weather_list"] = split_multi_value(row.get("weather", ""))
        prepared_row["road_condition_list"] = split_multi_value(
            row.get("road_condition", "")
        )
        prepared_row["vehicle_type_list"] = split_multi_value(
            row.get("vehicle_type", "")
        )
        prepared_row["behavior_list"] = split_multi_value(row.get("behavior", ""))
        prepared_row["suggestion_list"] = split_multi_value(
            row.get("suggestion", "")
        ) or ([clean_text(row.get("suggestion", ""))] if clean_text(row.get("suggestion", "")) else [])
        prepared_row["violation_list"] = split_multi_value(
            row.get("violation_name", "")
        )
        prepared_row["province_list"] = (
            [clean_text(row.get("province", ""))]
            if clean_text(row.get("province", ""))
            else []
        )
        prepared_row["city_list"] = (
            [clean_text(row.get("city", ""))]
            if clean_text(row.get("city", ""))
            else []
        )
        prepared_row["road_list"] = (
            [clean_text(row.get("road_name", ""))]
            if clean_text(row.get("road_name", ""))
            else []
        )
        prepared_row["casualty_list"] = (
            [clean_text(row.get("casualties", ""))]
            if clean_text(row.get("casualties", ""))
            else []
        )
        prepared_row["responsibility_list"] = (
            [clean_text(row.get("responsibility", ""))]
            if clean_text(row.get("responsibility", ""))
            else []
        )
        prepared.append(prepared_row)
    return prepared


def prepare_violation_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    prepared: list[dict[str, object]] = []
    for row in rows:
        prepared_row: dict[str, object] = dict(row)
        prepared_row["penalty_key"] = build_penalty_key(row)
        prepared_row["violation_type_list"] = (
            [clean_text(row.get("violation_type", ""))]
            if clean_text(row.get("violation_type", ""))
            else []
        )
        prepared_row["applicable_vehicle_list"] = split_multi_value(
            row.get("applicable_vehicle", "")
        )
        prepared_row["penalty_type_list"] = (
            [clean_text(row.get("penalty_type", ""))]
            if clean_text(row.get("penalty_type", ""))
            else []
        )
        prepared_row["license_action_list"] = (
            [clean_text(row.get("license_action", ""))]
            if clean_text(row.get("license_action", ""))
            and clean_text(row.get("license_action", "")) not in {"无", "否"}
            else []
        )
        prepared.append(prepared_row)
    return prepared


def prepare_sign_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    prepared: list[dict[str, object]] = []
    for row in rows:
        prepared_row: dict[str, object] = dict(row)
        prepared_row["sign_category_list"] = (
            [clean_text(row.get("sign_category", ""))]
            if clean_text(row.get("sign_category", ""))
            else []
        )
        prepared_row["sub_category_list"] = (
            [clean_text(row.get("sub_category", ""))]
            if clean_text(row.get("sub_category", ""))
            else []
        )
        prepared_row["shape_list"] = (
            [clean_text(row.get("shape", ""))]
            if clean_text(row.get("shape", ""))
            else []
        )
        prepared_row["color_list"] = (
            [clean_text(row.get("color", ""))]
            if clean_text(row.get("color", ""))
            else []
        )
        prepared_row["scene_list"] = split_multi_value(row.get("applicable_scene", ""))
        prepared_row["standard_list"] = (
            [clean_text(row.get("standard_no", ""))]
            if clean_text(row.get("standard_no", ""))
            else []
        )
        prepared.append(prepared_row)
    return prepared


def create_constraints(tx) -> None:
    statements = [
        """
        CREATE CONSTRAINT law_id_unique IF NOT EXISTS
        FOR (n:Law) REQUIRE n.law_id IS UNIQUE
        """,
        """
        CREATE CONSTRAINT article_id_unique IF NOT EXISTS
        FOR (n:Article) REQUIRE n.article_id IS UNIQUE
        """,
        """
        CREATE CONSTRAINT violation_name_unique IF NOT EXISTS
        FOR (n:Violation) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT penalty_key_unique IF NOT EXISTS
        FOR (n:Penalty) REQUIRE n.penalty_key IS UNIQUE
        """,
        """
        CREATE CONSTRAINT sign_id_unique IF NOT EXISTS
        FOR (n:RoadSign) REQUIRE n.sign_id IS UNIQUE
        """,
        """
        CREATE CONSTRAINT case_id_unique IF NOT EXISTS
        FOR (n:AccidentCase) REQUIRE n.case_id IS UNIQUE
        """,
        """
        CREATE CONSTRAINT weather_name_unique IF NOT EXISTS
        FOR (n:Weather) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT road_condition_name_unique IF NOT EXISTS
        FOR (n:RoadCondition) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT vehicle_type_name_unique IF NOT EXISTS
        FOR (n:VehicleType) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT behavior_name_unique IF NOT EXISTS
        FOR (n:Behavior) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT suggestion_content_unique IF NOT EXISTS
        FOR (n:Suggestion) REQUIRE n.content IS UNIQUE
        """,
        """
        CREATE CONSTRAINT sign_category_name_unique IF NOT EXISTS
        FOR (n:SignCategory) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT sign_subcategory_name_unique IF NOT EXISTS
        FOR (n:SignSubCategory) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT sign_shape_name_unique IF NOT EXISTS
        FOR (n:SignShape) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT sign_color_name_unique IF NOT EXISTS
        FOR (n:SignColor) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT scene_name_unique IF NOT EXISTS
        FOR (n:Scene) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT standard_no_unique IF NOT EXISTS
        FOR (n:Standard) REQUIRE n.no IS UNIQUE
        """,
        """
        CREATE CONSTRAINT violation_type_name_unique IF NOT EXISTS
        FOR (n:ViolationType) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT applicable_vehicle_name_unique IF NOT EXISTS
        FOR (n:ApplicableVehicle) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT penalty_type_name_unique IF NOT EXISTS
        FOR (n:PenaltyType) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT license_action_name_unique IF NOT EXISTS
        FOR (n:LicenseAction) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT province_name_unique IF NOT EXISTS
        FOR (n:Province) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT city_name_unique IF NOT EXISTS
        FOR (n:City) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT road_name_unique IF NOT EXISTS
        FOR (n:Road) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT casualty_result_name_unique IF NOT EXISTS
        FOR (n:CasualtyResult) REQUIRE n.name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT responsibility_type_name_unique IF NOT EXISTS
        FOR (n:ResponsibilityType) REQUIRE n.name IS UNIQUE
        """,
    ]
    for statement in statements:
        tx.run(statement)


def import_law_articles(tx, rows: list[dict[str, object]]) -> None:
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (l:Law {law_id: row.law_id})
        SET l.name = row.law_name,
            l.level = row.law_level,
            l.effective_date = row.effective_date,
            l.source_url = row.source_url,
            l.source_name = row.source_name,
            l.source_type = row.source_type,
            l.source_note = row.source_note,
            l.quality_flag = row.quality_flag,
            l.remark = row.remark

        MERGE (a:Article {article_id: row.article_id})
        SET a.article_no = row.article_no,
            a.title = row.article_title,
            a.content = row.article_text,
            a.chapter = row.chapter,
            a.source_url = row.source_url,
            a.source_name = row.source_name,
            a.source_type = row.source_type,
            a.source_note = row.source_note,
            a.quality_flag = row.quality_flag

        MERGE (l)-[:HAS_ARTICLE]->(a)
        """,
        rows=rows,
    )


def import_violation_penalties(tx, rows: list[dict[str, object]]) -> None:
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (v:Violation {name: row.violation_name})
        SET v.violation_id = row.violation_id,
            v.type = row.violation_type,
            v.applicable_vehicle = row.applicable_vehicle,
            v.source_url = row.source_url,
            v.source_name = row.source_name,
            v.source_type = row.source_type,
            v.source_note = row.source_note,
            v.quality_flag = row.quality_flag,
            v.remark = row.remark

        MERGE (p:Penalty {penalty_key: row.penalty_key})
        SET p.penalty_type = row.penalty_type,
            p.content = row.penalty_content,
            p.fine_range = row.fine_range,
            p.score_value = row.score_value,
            p.detention = row.detention,
            p.license_action = row.license_action,
            p.source_url = row.source_url,
            p.source_name = row.source_name,
            p.source_type = row.source_type,
            p.source_note = row.source_note,
            p.quality_flag = row.quality_flag

        MERGE (v)-[:PENALIZED_AS]->(p)

        FOREACH (_ IN CASE WHEN row.related_article_id = '' THEN [] ELSE [1] END |
            MERGE (a:Article {article_id: row.related_article_id})
            MERGE (a)-[:REGULATES]->(v)
        )

        FOREACH (item IN row.violation_type_list |
            MERGE (vt:ViolationType {name: item})
            MERGE (v)-[:OF_TYPE]->(vt)
        )

        FOREACH (item IN row.applicable_vehicle_list |
            MERGE (av:ApplicableVehicle {name: item})
            MERGE (v)-[:APPLIES_TO]->(av)
        )

        FOREACH (item IN row.penalty_type_list |
            MERGE (pt:PenaltyType {name: item})
            MERGE (p)-[:HAS_PENALTY_TYPE]->(pt)
        )

        FOREACH (item IN row.license_action_list |
            MERGE (la:LicenseAction {name: item})
            MERGE (p)-[:HAS_LICENSE_ACTION]->(la)
        )
        """,
        rows=rows,
    )


def import_road_signs(tx, rows: list[dict[str, object]]) -> None:
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (s:RoadSign {sign_id: row.sign_id})
        SET s.name = row.sign_name,
            s.category = row.sign_category,
            s.sub_category = row.sub_category,
            s.shape = row.shape,
            s.color = row.color,
            s.meaning = row.meaning,
            s.applicable_scene = row.applicable_scene,
            s.standard_no = row.standard_no,
            s.image_ref = row.image_ref,
            s.source_url = row.source_url,
            s.source_name = row.source_name,
            s.source_type = row.source_type,
            s.source_note = row.source_note,
            s.quality_flag = row.quality_flag,
            s.remark = row.remark

        FOREACH (item IN row.sign_category_list |
            MERGE (c:SignCategory {name: item})
            MERGE (s)-[:OF_CATEGORY]->(c)
        )

        FOREACH (item IN row.sub_category_list |
            MERGE (sc:SignSubCategory {name: item})
            MERGE (s)-[:OF_SUBCATEGORY]->(sc)
        )

        FOREACH (item IN row.shape_list |
            MERGE (sh:SignShape {name: item})
            MERGE (s)-[:HAS_SHAPE]->(sh)
        )

        FOREACH (item IN row.color_list |
            MERGE (co:SignColor {name: item})
            MERGE (s)-[:HAS_COLOR]->(co)
        )

        FOREACH (item IN row.scene_list |
            MERGE (scn:Scene {name: item})
            MERGE (s)-[:APPLIES_TO_SCENE]->(scn)
        )

        FOREACH (item IN row.standard_list |
            MERGE (st:Standard {no: item})
            MERGE (s)-[:FOLLOWS_STANDARD]->(st)
        )
        """,
        rows=rows,
    )


def import_accident_cases(tx, rows: list[dict[str, object]]) -> None:
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (c:AccidentCase {case_id: row.case_id})
        SET c.name = row.case_name,
            c.date = row.date,
            c.province = row.province,
            c.city = row.city,
            c.place = row.place,
            c.road_name = row.road_name,
            c.cause = row.cause,
            c.casualties = row.casualties,
            c.responsibility = row.responsibility,
            c.source_url = row.source_url,
            c.source_name = row.source_name,
            c.source_type = row.source_type,
            c.source_note = row.source_note,
            c.quality_flag = row.quality_flag,
            c.remark = row.remark

        FOREACH (item IN row.weather_list |
            MERGE (w:Weather {name: item})
            MERGE (c)-[:IN_WEATHER]->(w)
        )

        FOREACH (item IN row.road_condition_list |
            MERGE (r:RoadCondition {name: item})
            MERGE (c)-[:ON_CONDITION]->(r)
        )

        FOREACH (item IN row.vehicle_type_list |
            MERGE (vt:VehicleType {name: item})
            MERGE (c)-[:INVOLVES_VEHICLE]->(vt)
        )

        FOREACH (item IN row.behavior_list |
            MERGE (b:Behavior {name: item})
            MERGE (c)-[:HAS_BEHAVIOR]->(b)
        )

        FOREACH (item IN row.suggestion_list |
            MERGE (s:Suggestion {content: item})
            MERGE (c)-[:HAS_SUGGESTION]->(s)
        )

        FOREACH (item IN row.violation_list |
            MERGE (v:Violation {name: item})
            MERGE (c)-[:VIOLATES]->(v)
        )

        FOREACH (item IN row.province_list |
            MERGE (p:Province {name: item})
            MERGE (c)-[:IN_PROVINCE]->(p)
        )

        FOREACH (item IN row.city_list |
            MERGE (ci:City {name: item})
            MERGE (c)-[:IN_CITY]->(ci)
        )

        FOREACH (item IN row.road_list |
            MERGE (r:Road {name: item})
            MERGE (c)-[:ON_ROAD]->(r)
        )

        FOREACH (item IN row.casualty_list |
            MERGE (cr:CasualtyResult {name: item})
            MERGE (c)-[:HAS_CASUALTY]->(cr)
        )

        FOREACH (item IN row.responsibility_list |
            MERGE (rt:ResponsibilityType {name: item})
            MERGE (c)-[:HAS_RESPONSIBILITY]->(rt)
        )
        """,
        rows=rows,
    )


def print_summary(session) -> None:
    print("\nImport summary:")
    for label in SUMMARY_LABELS:
        result = session.run(f"MATCH (n:{label}) RETURN count(n) AS count")
        count = result.single()["count"]
        print(f"- {label}: {count}")


def infer_http_uri(uri: str) -> str:
    parsed = urllib.parse.urlparse(uri)
    hostname = parsed.hostname or "localhost"
    port = parsed.port or 7687
    if port == 7687:
        http_port = 7474
    else:
        http_port = port
    return f"http://{hostname}:{http_port}"


class HttpNeo4jResult:
    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records

    def single(self) -> dict[str, object]:
        if not self.records:
            return {}
        return self.records[0]


class HttpNeo4jSession:
    def __init__(self, http_uri: str, user: str, password: str, database: str) -> None:
        self.http_uri = http_uri.rstrip("/")
        self.user = user
        self.password = password
        self.database = database

    def __enter__(self) -> "HttpNeo4jSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def _request(self, statement: str, parameters: dict[str, object] | None = None) -> HttpNeo4jResult:
        endpoint = f"{self.http_uri}/db/{urllib.parse.quote(self.database)}/tx/commit"
        payload = {
            "statements": [
                {
                    "statement": statement,
                    "parameters": parameters or {},
                    "resultDataContents": ["row"],
                }
            ]
        }
        auth_text = f"{self.user}:{self.password}".encode("utf-8")
        headers = {
            "Authorization": "Basic " + base64.b64encode(auth_text).decode("ascii"),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                response_body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Neo4j HTTP request failed: {details}") from error

        errors = response_body.get("errors", [])
        if errors:
            joined = "; ".join(error.get("message", "Unknown error") for error in errors)
            raise RuntimeError(joined)

        results = response_body.get("results", [])
        if not results:
            return HttpNeo4jResult([])

        columns = results[0].get("columns", [])
        rows = results[0].get("data", [])
        records = [dict(zip(columns, item.get("row", []))) for item in rows]
        return HttpNeo4jResult(records)

    def run(self, statement: str, **parameters) -> HttpNeo4jResult:
        return self._request(statement, parameters)

    def execute_write(self, func, *args):
        return func(self, *args)


class HttpNeo4jDriver:
    def __init__(self, http_uri: str, user: str, password: str, database: str) -> None:
        self.http_uri = http_uri
        self.user = user
        self.password = password
        self.database = database

    def verify_connectivity(self) -> None:
        with self.session(database=self.database) as session:
            result = session.run("RETURN 1 AS ok")
            if result.single().get("ok") != 1:
                raise RuntimeError("Neo4j connectivity check failed.")

    def session(self, database: str | None = None) -> HttpNeo4jSession:
        return HttpNeo4jSession(
            self.http_uri,
            self.user,
            self.password,
            database or self.database,
        )

    def close(self) -> None:
        return None


def create_driver(args: argparse.Namespace, password: str):
    try:
        from neo4j import GraphDatabase
    except ImportError:
        http_uri = args.http_uri or infer_http_uri(args.uri)
        print(
            f"neo4j Python package not found, using HTTP fallback: {http_uri}"
        )
        return HttpNeo4jDriver(http_uri, args.user, password, args.database)

    return GraphDatabase.driver(args.uri, auth=(args.user, password))


def load_all_csvs(data_dir: Path) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    return (
        read_csv(data_dir / DEFAULT_FILES["law_article"]),
        read_csv(data_dir / DEFAULT_FILES["violation_penalty"]),
        read_csv(data_dir / DEFAULT_FILES["road_sign"]),
        read_csv(data_dir / DEFAULT_FILES["accident_case"]),
    )


def load_all_xlsx(xlsx_path: Path) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    if not xlsx_path.exists():
        raise FileNotFoundError(f"XLSX file not found: {xlsx_path}")

    with zipfile.ZipFile(xlsx_path) as zip_file:
        shared_strings = read_shared_strings(zip_file)
        sheet_map = read_workbook_sheet_map(zip_file)
        return (
            read_xlsx_sheet(zip_file, "law_article", shared_strings, sheet_map),
            read_xlsx_sheet(zip_file, "violation_penalty", shared_strings, sheet_map),
            read_xlsx_sheet(zip_file, "road_sign", shared_strings, sheet_map),
            read_xlsx_sheet(zip_file, "accident_case", shared_strings, sheet_map),
        )


def main() -> int:
    args = parse_args()

    try:
        if args.xlsx:
            xlsx_path = Path(args.xlsx).resolve()
            law_rows, violation_rows, sign_rows, case_rows = load_all_xlsx(xlsx_path)
        else:
            data_dir = Path(args.data_dir).resolve()
            if not data_dir.exists():
                print(f"Data directory does not exist: {data_dir}", file=sys.stderr)
                return 1
            try:
                law_rows, violation_rows, sign_rows, case_rows = load_all_csvs(data_dir)
            except FileNotFoundError as error:
                default_xlsx = detect_default_xlsx()
                if default_xlsx is not None:
                    print(f"CSV files not found, using default workbook: {default_xlsx}")
                    law_rows, violation_rows, sign_rows, case_rows = load_all_xlsx(default_xlsx)
                else:
                    print(error, file=sys.stderr)
                    print(
                        "Hint: if your data is in an Excel workbook, run with --xlsx \"full_path_to_file.xlsx\"",
                        file=sys.stderr,
                    )
                    return 1
    except (FileNotFoundError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1

    prepared_violation_rows = prepare_violation_rows(violation_rows)
    prepared_sign_rows = prepare_sign_rows(sign_rows)
    prepared_case_rows = prepare_case_rows(case_rows)

    print("Loaded CSV files:")
    print(f"- law_article.csv: {len(law_rows)} rows")
    print(f"- violation_penalty.csv: {len(violation_rows)} rows")
    print(f"- road_sign.csv: {len(sign_rows)} rows")
    print(f"- accident_case.csv: {len(case_rows)} rows")

    password = args.password or getpass.getpass("Neo4j password (input hidden): ")
    driver = create_driver(args, password)

    try:
        driver.verify_connectivity()
    except Exception as error:  # pragma: no cover - depends on runtime environment
        print(f"Failed to connect to Neo4j: {error}", file=sys.stderr)
        driver.close()
        return 1

    try:
        with driver.session(database=args.database) as session:
            session.execute_write(create_constraints)

            for batch in chunked(law_rows, args.batch_size):
                session.execute_write(import_law_articles, batch)

            for batch in chunked(prepared_violation_rows, args.batch_size):
                session.execute_write(import_violation_penalties, batch)

            for batch in chunked(prepared_sign_rows, args.batch_size):
                session.execute_write(import_road_signs, batch)

            for batch in chunked(prepared_case_rows, args.batch_size):
                session.execute_write(import_accident_cases, batch)

            print_summary(session)

        print("\nImport finished successfully.")
        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
