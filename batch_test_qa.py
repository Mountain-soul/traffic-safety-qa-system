from __future__ import annotations

import argparse
import csv
import getpass
import os
import sys
from pathlib import Path

from import_to_neo4j import create_driver, detect_default_xlsx
from generate_qa_test_questions import build_questions, write_questions
from traffic_qa_engine import ConversationContext, TrafficQAEngine


DEFAULT_QUESTIONS = Path("generated") / "qa_test_questions.csv"
DEFAULT_OUTPUT = Path("generated") / "qa_test_results.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch test traffic KG QA questions.")
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--http-uri", default=os.getenv("NEO4J_HTTP_URI", "http://localhost:7474"))
    parser.add_argument("--user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.getenv("NEO4J_PASSWORD"))
    parser.add_argument("--database", default=os.getenv("NEO4J_DATABASE", "neo4j"))
    return parser.parse_args()


def read_questions(path: Path) -> list[dict[str, str]]:
    encodings = ("utf-8-sig", "utf-8", "gbk")
    last_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        try:
            with path.open("r", encoding=encoding, newline="") as file:
                rows = list(csv.DictReader(file))
            return [row for row in rows if row.get("question")]
        except UnicodeDecodeError as error:
            last_error = error
    if last_error is not None:
        raise last_error
    return []


def is_useful_answer(answer: str) -> bool:
    bad_markers = [
        "我暂时没理解",
        "我还没识别到",
        "暂时没有查到",
        "暂时没有",
        "问题不能为空",
    ]
    return not any(marker in answer for marker in bad_markers)


def main() -> int:
    args = parse_args()
    questions_path = Path(args.questions)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not questions_path.exists():
        xlsx_path = detect_default_xlsx()
        if xlsx_path is None:
            print(f"Question file not found: {questions_path}", file=sys.stderr)
            return 1
        generated_rows = build_questions(xlsx_path)
        write_questions(questions_path, generated_rows)
        print(f"Question file not found, generated {len(generated_rows)} questions: {questions_path.resolve()}")

    rows = read_questions(questions_path)
    password = args.password or getpass.getpass("Neo4j password (input hidden): ")
    driver = create_driver(args, password)

    try:
        driver.verify_connectivity()
        with driver.session(database=args.database) as session:
            engine = TrafficQAEngine(session)
            results: list[dict[str, str]] = []
            for index, row in enumerate(rows, start=1):
                question = row["question"].strip()
                payload, _ = engine.answer(question, ConversationContext())
                answer = payload.to_text()
                useful = is_useful_answer(answer)
                results.append(
                    {
                        "index": str(index),
                        "question": question,
                        "type": row.get("type", ""),
                        "intent": payload.intent_label,
                        "status": "PASS" if useful else "CHECK",
                        "answer": answer.replace("\r\n", "\n").replace("\r", "\n"),
                    }
                )

        with output_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["index", "question", "type", "intent", "status", "answer"],
            )
            writer.writeheader()
            writer.writerows(results)

        total = len(results)
        passed = sum(1 for row in results if row["status"] == "PASS")
        print(f"Questions: {total}")
        print(f"PASS: {passed}")
        print(f"CHECK: {total - passed}")
        print(f"Useful-answer rate: {passed / total:.2%}" if total else "No questions.")
        print(f"Output: {output_path.resolve()}")
        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
