from __future__ import annotations

import argparse
import csv
from pathlib import Path

from import_to_neo4j import (
    clean_text,
    detect_default_xlsx,
    load_all_xlsx,
    split_multi_value,
)


DEFAULT_OUTPUT = Path("generated") / "qa_test_questions.csv"


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = clean_text(value)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def first_values(rows: list[dict[str, str]], field: str, limit: int) -> list[str]:
    values = [clean_text(row.get(field, "")) for row in rows]
    return dedupe_keep_order(values)[:limit]


def split_values(rows: list[dict[str, str]], field: str, limit: int) -> list[str]:
    values: list[str] = []
    for row in rows:
        values.extend(split_multi_value(row.get(field, "")))
    return dedupe_keep_order(values)[:limit]


def write_questions(output_path: Path, rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["type", "question"])
        writer.writeheader()
        writer.writerows(rows)


def build_questions(xlsx_path: Path) -> list[dict[str, str]]:
    law_rows, violation_rows, sign_rows, case_rows = load_all_xlsx(xlsx_path)
    questions: list[dict[str, str]] = []

    def add(question_type: str, question: str) -> None:
        questions.append({"type": question_type, "question": question})

    add("overview", "当前图谱数据量是多少？")
    add("overview", "有哪些相关法规？")
    add("overview", "有哪些违法行为？")
    add("overview", "有哪些道路标志？")
    add("overview", "有哪些事故案例？")
    add("overview", "有哪些天气因素？")
    add("overview", "有哪些道路条件？")

    for name in first_values(violation_rows, "violation_name", 35):
        add("penalty", f"{name}怎么处罚？")
        add("penalty", f"{name}扣几分？")
        add("law", f"{name}相关法条有哪些？")
        add("accident", f"{name}会导致什么事故风险？")

    for article_no in first_values(law_rows, "article_no", 25):
        add("law", f"道路交通安全法{article_no}是什么？")

    for keyword in ["安全驾驶", "交通信号", "机动车限速", "驾驶证", "道路通行", "交通事故", "现场处理"]:
        add("law", f"{keyword}有什么规定？")

    for name in first_values(sign_rows, "sign_name", 35):
        add("sign", f"{name}是什么意思？")
        add("sign", f"{name}适用于什么场景？")

    for category in split_values(sign_rows, "sign_category", 8):
        add("overview", f"{category}标志有哪些？")

    for weather in split_values(case_rows, "weather", 12):
        add("accident", f"{weather}有什么事故风险？")
        add("overview", f"{weather}有哪些事故案例？")

    for behavior in split_values(case_rows, "behavior", 18):
        add("accident", f"{behavior}会导致什么事故？")
        add("overview", f"{behavior}有哪些事故案例？")

    for condition in split_values(case_rows, "road_condition", 15):
        add("accident", f"{condition}路段有什么风险？")
        add("overview", f"{condition}有哪些事故案例？")

    reasoning_questions = [
        "雨天高速遇到施工限速该如何操作？",
        "夜间高速遇到前方施工应该怎么办？",
        "大雾天气看到限速标志应该怎么通行？",
        "路面湿滑又遇到急弯应该如何处理？",
        "高速公路施工路段如何安全通行？",
        "雨天路面湿滑还要变道该怎么做？",
        "长下坡遇到限速标志应该怎么操作？",
        "雪天高速遇到能见度低应该怎么办？",
    ]
    for question in reasoning_questions:
        add("reasoning", question)

    deduped: list[dict[str, str]] = []
    seen_questions: set[str] = set()
    for row in questions:
        question = clean_text(row["question"])
        if not question or question in seen_questions:
            continue
        seen_questions.add(question)
        deduped.append({"type": row["type"], "question": question})
    return deduped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate QA test questions from the traffic KG workbook.")
    parser.add_argument("--xlsx", help="Workbook path. Defaults to the detected traffic KG workbook.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    xlsx_path = Path(args.xlsx).resolve() if args.xlsx else detect_default_xlsx()
    if xlsx_path is None:
        raise FileNotFoundError("No default workbook found. Please pass --xlsx.")
    questions = build_questions(xlsx_path)
    output_path = Path(args.output)
    write_questions(output_path, questions)
    print(f"Workbook: {xlsx_path}")
    print(f"Questions: {len(questions)}")
    print(f"Output: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
