from __future__ import annotations

import argparse
import csv
from pathlib import Path

import import_to_neo4j as xlsx_utils


DEFAULT_SOURCE_URL = "https://jtgl.beijing.gov.cn/jgj/jgxx/flfg/fl/205308/index.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a draft violation_penalty CSV from the Road Traffic Safety Law workbook."
    )
    parser.add_argument(
        "--xlsx",
        required=True,
        help="Path to the merged workbook that contains the expanded law_article sheet.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the output CSV file.",
    )
    return parser.parse_args()


def build_article_lookup(law_rows: list[dict[str, str]]) -> dict[str, str]:
    return {row["article_no"]: row["article_id"] for row in law_rows if row.get("article_no")}


def draft_rows(article_lookup: dict[str, str]) -> list[dict[str, str]]:
    return [
        {
            "violation_id": "V007",
            "violation_name": "醉酒驾驶",
            "violation_type": "危险驾驶",
            "related_article_id": article_lookup.get("第九十一条", ""),
            "penalty_type": "吊销驾驶证+依法追究刑事责任",
            "penalty_content": "醉酒驾驶机动车的，约束至酒醒，吊销机动车驾驶证，依法追究刑事责任；五年内不得重新取得机动车驾驶证",
            "fine_range": "",
            "score_value": "",
            "detention": "否",
            "license_action": "吊销驾驶证",
            "applicable_vehicle": "机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十一条整理，记分需结合记分管理办法核验",
        },
        {
            "violation_id": "V008",
            "violation_name": "再次酒后驾驶",
            "violation_type": "危险驾驶",
            "related_article_id": article_lookup.get("第九十一条", ""),
            "penalty_type": "拘留+罚款+吊销驾驶证",
            "penalty_content": "因饮酒后驾驶机动车被处罚，再次饮酒后驾驶机动车的，处十日以下拘留，并处一千元以上二千元以下罚款，吊销机动车驾驶证",
            "fine_range": "1000-2000",
            "score_value": "",
            "detention": "是",
            "license_action": "吊销驾驶证",
            "applicable_vehicle": "机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十一条整理，拘留期限为十日以下",
        },
        {
            "violation_id": "V009",
            "violation_name": "饮酒后驾驶营运机动车",
            "violation_type": "危险驾驶",
            "related_article_id": article_lookup.get("第九十一条", ""),
            "penalty_type": "拘留+罚款+吊销驾驶证",
            "penalty_content": "饮酒后驾驶营运机动车的，处十五日拘留，并处五千元罚款，吊销机动车驾驶证，五年内不得重新取得机动车驾驶证",
            "fine_range": "5000",
            "score_value": "",
            "detention": "是",
            "license_action": "吊销驾驶证",
            "applicable_vehicle": "营运机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十一条整理，记分需结合记分管理办法核验",
        },
        {
            "violation_id": "V010",
            "violation_name": "醉酒驾驶营运机动车",
            "violation_type": "危险驾驶",
            "related_article_id": article_lookup.get("第九十一条", ""),
            "penalty_type": "吊销驾驶证+依法追究刑事责任",
            "penalty_content": "醉酒驾驶营运机动车的，约束至酒醒，吊销机动车驾驶证，依法追究刑事责任，十年内不得重新取得机动车驾驶证，重新取得后不得驾驶营运机动车",
            "fine_range": "",
            "score_value": "",
            "detention": "否",
            "license_action": "吊销驾驶证",
            "applicable_vehicle": "营运机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十一条整理",
        },
        {
            "violation_id": "V011",
            "violation_name": "酒醉驾发生重大交通事故",
            "violation_type": "危险驾驶",
            "related_article_id": article_lookup.get("第九十一条", ""),
            "penalty_type": "吊销驾驶证+依法追究刑事责任",
            "penalty_content": "饮酒后或者醉酒驾驶机动车发生重大交通事故，构成犯罪的，依法追究刑事责任，并吊销机动车驾驶证，终生不得重新取得机动车驾驶证",
            "fine_range": "",
            "score_value": "",
            "detention": "否",
            "license_action": "吊销驾驶证",
            "applicable_vehicle": "机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十一条整理",
        },
        {
            "violation_id": "V012",
            "violation_name": "公路客运车辆超员",
            "violation_type": "超员超载",
            "related_article_id": article_lookup.get("第九十二条", ""),
            "penalty_type": "罚款",
            "penalty_content": "公路客运车辆载客超过额定乘员的，处二百元以上五百元以下罚款；超过额定乘员百分之二十或者违反规定载货的，处五百元以上二千元以下罚款",
            "fine_range": "200-2000",
            "score_value": "",
            "detention": "否",
            "license_action": "无",
            "applicable_vehicle": "公路客运车辆",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十二条整理，具体罚款需按情形细分",
        },
        {
            "violation_id": "V013",
            "violation_name": "货运机动车超载",
            "violation_type": "超员超载",
            "related_article_id": article_lookup.get("第九十二条", ""),
            "penalty_type": "罚款",
            "penalty_content": "货运机动车超过核定载质量的，处二百元以上五百元以下罚款；超过核定载质量百分之三十或者违反规定载客的，处五百元以上二千元以下罚款",
            "fine_range": "200-2000",
            "score_value": "",
            "detention": "否",
            "license_action": "无",
            "applicable_vehicle": "货运机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十二条整理，具体罚款需按情形细分",
        },
        {
            "violation_id": "V014",
            "violation_name": "违法停车",
            "violation_type": "一般违法",
            "related_article_id": article_lookup.get("第九十三条", ""),
            "penalty_type": "警告或罚款",
            "penalty_content": "违反机动车停放、临时停车规定，驾驶人不在现场或者拒绝立即驶离、妨碍通行的，处二十元以上二百元以下罚款",
            "fine_range": "20-200",
            "score_value": "",
            "detention": "否",
            "license_action": "无",
            "applicable_vehicle": "机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十三条整理",
        },
        {
            "violation_id": "V015",
            "violation_name": "未悬挂机动车号牌",
            "violation_type": "牌证违法",
            "related_article_id": article_lookup.get("第九十五条", ""),
            "penalty_type": "扣留机动车+罚款",
            "penalty_content": "上道路行驶的机动车未悬挂机动车号牌的，应当扣留机动车，并可以依照第九十条规定予以处罚",
            "fine_range": "20-200",
            "score_value": "",
            "detention": "否",
            "license_action": "无",
            "applicable_vehicle": "机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十五条与第九十条整理，罚款依据为20-200元",
        },
        {
            "violation_id": "V016",
            "violation_name": "未放置检验合格标志或保险标志",
            "violation_type": "牌证违法",
            "related_article_id": article_lookup.get("第九十五条", ""),
            "penalty_type": "扣留机动车+罚款",
            "penalty_content": "上道路行驶的机动车未放置检验合格标志、保险标志的，应当扣留机动车，并可以依照第九十条规定予以处罚",
            "fine_range": "20-200",
            "score_value": "",
            "detention": "否",
            "license_action": "无",
            "applicable_vehicle": "机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十五条与第九十条整理，罚款依据为20-200元",
        },
        {
            "violation_id": "V017",
            "violation_name": "未随车携带行驶证或驾驶证",
            "violation_type": "牌证违法",
            "related_article_id": article_lookup.get("第九十五条", ""),
            "penalty_type": "扣留机动车+罚款",
            "penalty_content": "上道路行驶的机动车未随车携带行驶证、驾驶证的，应当扣留机动车，并可以依照第九十条规定予以处罚",
            "fine_range": "20-200",
            "score_value": "",
            "detention": "否",
            "license_action": "无",
            "applicable_vehicle": "机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十五条与第九十条整理，罚款依据为20-200元",
        },
        {
            "violation_id": "V018",
            "violation_name": "故意遮挡号牌",
            "violation_type": "牌证违法",
            "related_article_id": article_lookup.get("第九十五条", ""),
            "penalty_type": "罚款",
            "penalty_content": "故意遮挡机动车号牌的，依照第九十条规定予以处罚",
            "fine_range": "20-200",
            "score_value": "",
            "detention": "否",
            "license_action": "无",
            "applicable_vehicle": "机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十五条与第九十条整理，记分需结合记分管理办法核验",
        },
        {
            "violation_id": "V019",
            "violation_name": "污损号牌",
            "violation_type": "牌证违法",
            "related_article_id": article_lookup.get("第九十五条", ""),
            "penalty_type": "罚款",
            "penalty_content": "污损机动车号牌的，依照第九十条规定予以处罚",
            "fine_range": "20-200",
            "score_value": "",
            "detention": "否",
            "license_action": "无",
            "applicable_vehicle": "机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十五条与第九十条整理，记分需结合记分管理办法核验",
        },
        {
            "violation_id": "V020",
            "violation_name": "不按规定安装号牌",
            "violation_type": "牌证违法",
            "related_article_id": article_lookup.get("第九十五条", ""),
            "penalty_type": "罚款",
            "penalty_content": "不按规定安装机动车号牌的，依照第九十条规定予以处罚",
            "fine_range": "20-200",
            "score_value": "",
            "detention": "否",
            "license_action": "无",
            "applicable_vehicle": "机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十五条与第九十条整理，记分需结合记分管理办法核验",
        },
        {
            "violation_id": "V021",
            "violation_name": "无证驾驶",
            "violation_type": "严重违法",
            "related_article_id": article_lookup.get("第九十九条", ""),
            "penalty_type": "罚款+拘留",
            "penalty_content": "未取得机动车驾驶证、机动车驾驶证被吊销或者暂扣期间驾驶机动车的，处二百元以上二千元以下罚款，可以并处十五日以下拘留",
            "fine_range": "200-2000",
            "score_value": "",
            "detention": "是",
            "license_action": "无",
            "applicable_vehicle": "机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十九条整理",
        },
        {
            "violation_id": "V022",
            "violation_name": "将机动车交由无证人员驾驶",
            "violation_type": "严重违法",
            "related_article_id": article_lookup.get("第九十九条", ""),
            "penalty_type": "罚款+吊销驾驶证",
            "penalty_content": "将机动车交由未取得机动车驾驶证或者机动车驾驶证被吊销、暂扣的人驾驶的，处二百元以上二千元以下罚款，可以并处吊销机动车驾驶证",
            "fine_range": "200-2000",
            "score_value": "",
            "detention": "否",
            "license_action": "可并处吊销驾驶证",
            "applicable_vehicle": "机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十九条整理",
        },
        {
            "violation_id": "V023",
            "violation_name": "交通肇事后逃逸尚不构成犯罪",
            "violation_type": "严重违法",
            "related_article_id": article_lookup.get("第九十九条", ""),
            "penalty_type": "罚款+拘留",
            "penalty_content": "造成交通事故后逃逸，尚不构成犯罪的，处二百元以上二千元以下罚款，可以并处十五日以下拘留",
            "fine_range": "200-2000",
            "score_value": "",
            "detention": "是",
            "license_action": "无",
            "applicable_vehicle": "机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第九十九条整理",
        },
        {
            "violation_id": "V024",
            "violation_name": "强迫机动车驾驶人违反规定驾驶",
            "violation_type": "严重违法",
            "related_article_id": article_lookup.get("第九十九条", ""),
            "penalty_type": "罚款+拘留",
            "penalty_content": "强迫机动车驾驶人违反道路交通安全法律、法规和机动车安全驾驶要求驾驶机动车，造成交通事故，尚不构成犯罪的，处二百元以上二千元以下罚款，可以并处十五日以下拘留",
            "fine_range": "200-2000",
            "score_value": "",
            "detention": "是",
            "license_action": "无",
            "applicable_vehicle": "机动车",
            "source_url": DEFAULT_SOURCE_URL,
            "remark": "根据道路交通安全法第二十二条、第九十九条整理",
        },
    ]


def write_csv(output_path: Path, rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "violation_id",
        "violation_name",
        "violation_type",
        "related_article_id",
        "penalty_type",
        "penalty_content",
        "fine_range",
        "score_value",
        "detention",
        "license_action",
        "applicable_vehicle",
        "source_url",
        "remark",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    xlsx_path = Path(args.xlsx).resolve()
    output_path = Path(args.output).resolve()

    law_rows = xlsx_utils.load_all_xlsx(xlsx_path)[0]
    article_lookup = build_article_lookup(law_rows)
    rows = draft_rows(article_lookup)
    write_csv(output_path, rows)

    print(f"Generated draft rows: {len(rows)}")
    print(f"Output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
