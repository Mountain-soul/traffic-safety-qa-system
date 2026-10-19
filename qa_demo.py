from __future__ import annotations

import argparse
import getpass
import os
import sys

from import_to_neo4j import create_driver
from traffic_qa_engine import ConversationContext, TrafficQAEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Traffic safety KG QA demo.")
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.getenv("NEO4J_PASSWORD"))
    parser.add_argument("--database", default=os.getenv("NEO4J_DATABASE", "neo4j"))
    parser.add_argument(
        "--http-uri",
        default=os.getenv("NEO4J_HTTP_URI", "http://localhost:7474"),
    )
    parser.add_argument("--question", help="Ask one question and exit.")
    return parser.parse_args()


def interactive_loop(engine: TrafficQAEngine) -> None:
    print("交通安全知识图谱问答已启动，输入 exit 或 quit 结束。")
    context = ConversationContext()
    while True:
        try:
            question = input("\n请输入问题：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            return

        if question.lower() in {"exit", "quit"}:
            print("已退出。")
            return

        payload, context = engine.answer(question, context)
        print("\n回答：")
        print(payload.to_text())


def main() -> int:
    args = parse_args()
    password = args.password or getpass.getpass("Neo4j password (input hidden): ")
    driver = create_driver(args, password)

    try:
        driver.verify_connectivity()
    except Exception as error:  # noqa: BLE001
        print(f"Failed to connect to Neo4j: {error}", file=sys.stderr)
        driver.close()
        return 1

    try:
        with driver.session(database=args.database) as session:
            engine = TrafficQAEngine(session)
            if args.question:
                payload, _ = engine.answer(args.question, ConversationContext())
                print(payload.to_text())
            else:
                interactive_loop(engine)
        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
