from __future__ import annotations

import argparse
import csv
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import import_to_neo4j as xlsx_utils


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ET.register_namespace("", MAIN_NS)

SOURCE_URL_SIGN = "https://std.samr.gov.cn/"
SOURCE_URL_CASE = "https://www.gov.cn/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Expand road_sign and accident_case data and merge into workbook.")
    parser.add_argument(
        "--xlsx",
        default=str(Path("generated") / "交通问答系统的数据_合并法规版_二次合并.xlsx"),
    )
    parser.add_argument(
        "--road-sign-csv",
        default=str(Path("generated") / "road_sign_expand_draft.csv"),
    )
    parser.add_argument(
        "--accident-case-csv",
        default=str(Path("generated") / "accident_case_expand_draft.csv"),
    )
    parser.add_argument(
        "--output-xlsx",
        default=str(Path("generated") / "交通问答系统的数据_扩充标志案例版.xlsx"),
    )
    return parser.parse_args()


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
        sheet_views, f"{{{MAIN_NS}}}sheetView", {"workbookViewId": "0", "tabSelected": "1"}
    )
    ET.SubElement(sheet_view, f"{{{MAIN_NS}}}selection", {"activeCell": "A1", "sqref": "A1"})
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
        if value.startswith(prefix) and value[len(prefix) :].isdigit():
            max_id = max(max_id, int(value[len(prefix) :]))
    return max_id + 1


def draft_road_sign_rows(start_id: int) -> list[dict[str, str]]:
    items = [
        ("限速30", "禁令标志", "速度限制", "圆形", "白底红圈黑字", "表示机动车最高时速不得超过30公里", "学校周边/居民区"),
        ("限速50", "禁令标志", "速度限制", "圆形", "白底红圈黑字", "表示机动车最高时速不得超过50公里", "城市道路"),
        ("限速100", "禁令标志", "速度限制", "圆形", "白底红圈黑字", "表示机动车最高时速不得超过100公里", "高速公路"),
        ("解除限速40", "禁令标志", "速度限制", "圆形", "白底黑边黑斜杠", "表示限制速度40公里的路段结束", "限速路段末端"),
        ("禁止鸣喇叭", "禁令标志", "行为限制", "圆形", "白底红圈黑图案斜杠", "表示禁止机动车鸣喇叭", "医院/学校附近"),
        ("禁止左转", "禁令标志", "转向限制", "圆形", "白底红圈黑图案斜杠", "表示禁止车辆左转", "路口"),
        ("禁止右转", "禁令标志", "转向限制", "圆形", "白底红圈黑图案斜杠", "表示禁止车辆右转", "路口"),
        ("禁止超车", "禁令标志", "行为限制", "圆形", "白底红圈黑红车图案", "表示禁止机动车超车", "桥梁/隧道路段"),
        ("会车让行", "禁令标志", "让行类", "圆形", "白底红圈黑红箭头", "表示会车时应停车让对向车辆先行", "狭窄路段"),
        ("最低限速40", "禁令标志", "速度限制", "圆形", "蓝底白字", "表示机动车最低时速不得低于40公里", "快速路入口"),
        ("注意非机动车", "警告标志", "警告类", "等边三角形", "黄底黑边黑图案", "提醒前方有非机动车横穿或混行", "城郊接合部"),
        ("注意牲畜", "警告标志", "警告类", "等边三角形", "黄底黑边黑图案", "提醒前方可能有牲畜横穿", "农村道路"),
        ("注意路面结冰", "警告标志", "气象警告", "等边三角形", "黄底黑边黑图案", "提醒前方路段冬季易结冰", "桥面/山区道路"),
        ("注意积水", "警告标志", "气象警告", "等边三角形", "黄底黑边黑图案", "提醒前方路段可能积水", "低洼路段"),
        ("双向交通", "警告标志", "道路形态", "等边三角形", "黄底黑边黑图案", "提醒前方由单向变为双向交通", "施工导改路段"),
        ("注意潮汐车道", "警告标志", "道路形态", "等边三角形", "黄底黑边黑图案", "提醒前方有潮汐车道变化", "城市主干道"),
        ("注意合流", "警告标志", "道路形态", "等边三角形", "黄底黑边黑图案", "提醒前方有车流汇入", "匝道汇入点"),
        ("环岛行驶", "指示标志", "方向指示", "圆形", "蓝底白箭头", "表示前方按环岛方向行驶", "环岛路口"),
        ("靠右侧道路行驶", "指示标志", "通行指示", "圆形", "蓝底白箭头", "表示车辆应靠道路右侧通行", "道路分隔端"),
        ("步行", "指示标志", "专用通行", "圆形", "蓝底白图案", "表示该路段为步行通道", "景区/校园"),
    ]

    rows: list[dict[str, str]] = []
    for offset, item in enumerate(items, start=0):
        sign_id = f"S{start_id + offset:03d}"
        sign_name, category, sub_category, shape, color, meaning, scene = item
        rows.append(
            {
                "sign_id": sign_id,
                "sign_name": sign_name,
                "sign_category": category,
                "sub_category": sub_category,
                "shape": shape,
                "color": color,
                "meaning": meaning,
                "applicable_scene": scene,
                "standard_no": "GB 5768.2-2022",
                "image_ref": f"{sign_id.lower()}_{sign_name}.png".replace(" ", "_"),
                "source_url": SOURCE_URL_SIGN,
                "remark": "自动扩充草案，建议人工复核",
            }
        )
    return rows


def draft_accident_case_rows(start_id: int) -> list[dict[str, str]]:
    items = [
        ("高速分心驾驶追尾事故", "2024-01-18", "江苏省", "南京市", "G42沪蓉高速某路段", "高速公路", "阴天", "车流密集", "小型客车", "分心驾驶/未保持安全距离", "驾驶人使用手机导致追尾", "2伤", "驾驶人主要责任", "未保持安全车距", "严禁行车看手机并保持安全距离"),
        ("雨夜弯道超速侧滑事故", "2024-03-05", "湖南省", "株洲市", "某省道弯道路段", "省道", "雨天", "湿滑弯道", "小型客车", "超速行驶", "雨夜弯道车速过快失控", "1死2伤", "驾驶人主要责任", "超速行驶", "雨天弯道路段提前减速"),
        ("隧道出口急变道剐蹭事故", "2024-03-29", "浙江省", "杭州市", "某隧道出口", "城市快速路", "晴天", "明暗变化", "小型客车", "违法变道", "未观察后方来车强行并线", "3车受损", "变道车辆主要责任", "不按规定变更车道", "隧道出口保持车道稳定"),
        ("大雾天多车追尾事故", "2024-11-12", "河北省", "保定市", "京港澳高速某段", "高速公路", "大雾", "能见度低", "小型客车/货车", "未保持安全距离", "低能见度下跟车过近", "4伤", "多方责任", "未保持安全车距", "雾天开启雾灯并降低车速"),
        ("凌晨疲劳驾驶撞护栏事故", "2024-05-21", "江西省", "九江市", "某国道长直线路段", "国道", "夜间", "长直线路段", "重型货车", "疲劳驾驶", "连续驾驶超过4小时", "1死", "驾驶人主要责任", "疲劳驾驶", "严格执行休息制度"),
        ("施工路段未减速碰撞事故", "2024-06-03", "安徽省", "合肥市", "某快速路施工区", "城市快速路", "晴天", "施工导改", "小型客车", "未按标志减速", "忽视施工警示标志", "2伤", "驾驶人主要责任", "不按规定车道行驶", "施工区提前减速并按导向通行"),
        ("货车超载制动失效事故", "2024-07-14", "四川省", "雅安市", "山区长下坡路段", "省道", "晴天", "长下坡", "重型货车", "超载/操作不当", "超载导致制动距离过长", "1死3伤", "驾驶人及企业责任", "载物超过最大允许总质量", "严禁超载并定检制动系统"),
        ("校车未避让行人事故", "2024-09-09", "河南省", "新乡市", "学校门前路口", "城市道路", "晴天", "人流密集", "校车", "未避让行人", "通过斑马线未停车让行", "2伤", "驾驶人主要责任", "不按规定避让行人", "校车通过斑马线必须停车观察"),
        ("应急车道违法占用事故", "2024-10-02", "广东省", "广州市", "环城高速某段", "高速公路", "小雨", "拥堵路段", "小型客车", "违法占用应急车道", "拥堵时占用应急车道与故障车碰撞", "3伤", "占道车辆主要责任", "违法占用应急车道行驶", "拥堵时禁止占用应急车道"),
        ("高速应急车道碰撞事故", "2025-04-22", "湖北省", "武汉市", "绕城高速某段", "高速公路", "阴天", "拥堵缓行", "小型客车", "违法占用应急车道", "占用应急车道与故障检修车辆发生碰撞", "2伤", "占道车辆主要责任", "违法占用应急车道行驶", "非紧急情况不得占用应急车道"),
        ("逆行引发对向碰撞事故", "2024-12-18", "贵州省", "遵义市", "县道急弯路段", "县道", "夜间", "急弯路段", "小型客车", "逆行", "弯道借道逆行与对向车相撞", "2死1伤", "逆行车辆主要责任", "逆行", "弯道路段严禁越线行驶"),
        ("未系安全带二次伤害事故", "2025-01-11", "福建省", "福州市", "城市高架", "城市快速路", "晴天", "高架路段", "小型客车", "未系安全带", "碰撞后乘员二次撞击致重伤", "1重伤", "驾驶人及乘员共同责任", "未按规定系安全带", "全员全程系好安全带"),
        ("无证摩托车夜间事故", "2025-02-08", "云南省", "昆明市", "城郊道路", "城市道路", "夜间", "照明不足", "摩托车", "无证驾驶/不戴头盔", "超速且未佩戴头盔摔倒", "1死", "驾驶人主要责任", "摩托车不戴安全头盔", "骑乘摩托车必须戴头盔并守法"),
        ("公交专用道违规并线事故", "2025-03-16", "北京市", "北京市", "主干道公交专用道入口", "城市道路", "晴天", "早高峰", "小型客车", "违法并线", "强行并线与公交车剐蹭", "2车受损", "并线车辆主要责任", "不按规定变更车道", "高峰期谨慎并线礼让公交"),
        ("冰雪路面刹车失控事故", "2025-01-27", "黑龙江省", "哈尔滨市", "环线高架匝道", "城市快速路", "雪天", "结冰路面", "小型客车", "超速/跟车过近", "冰雪路面制动距离不足", "4车追尾", "多方责任", "超速行驶", "冰雪天气降低车速并拉大车距"),
        ("危险品车辆违规通行事故", "2025-04-10", "山东省", "淄博市", "危化品禁行路段", "国道", "晴天", "普通路段", "危险品运输车辆", "违反禁令标志", "未按规定路线行驶引发碰撞", "1死2伤", "驾驶人及企业责任", "违反禁令标志、禁止标线指示", "危化品运输严格按审批路线行驶"),
    ]

    rows: list[dict[str, str]] = []
    for offset, item in enumerate(items, start=0):
        case_id = f"C{start_id + offset:03d}"
        (
            case_name,
            date,
            province,
            city,
            place,
            road_name,
            weather,
            road_condition,
            vehicle_type,
            behavior,
            cause,
            casualties,
            responsibility,
            violation_name,
            suggestion,
        ) = item
        rows.append(
            {
                "case_id": case_id,
                "case_name": case_name,
                "date": date,
                "province": province,
                "city": city,
                "place": place,
                "road_name": road_name,
                "weather": weather,
                "road_condition": road_condition,
                "vehicle_type": vehicle_type,
                "behavior": behavior,
                "cause": cause,
                "casualties": casualties,
                "responsibility": responsibility,
                "violation_name": violation_name,
                "suggestion": suggestion,
                "source_url": SOURCE_URL_CASE,
                "remark": "自动扩充草案，建议人工复核",
            }
        )
    return rows


def merge_rows(existing: list[dict[str, str]], additions: list[dict[str, str]], key_field: str) -> list[dict[str, str]]:
    headers = list(existing[0].keys())
    merged: list[dict[str, str]] = [{h: row.get(h, "") for h in headers} for row in existing]
    existing_keys = {(row.get(key_field) or "").strip() for row in existing}
    for row in additions:
        key = (row.get(key_field) or "").strip()
        if key and key in existing_keys:
            continue
        merged.append({h: row.get(h, "") for h in headers})
        existing_keys.add(key)
    return merged


def write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def write_workbook_with_updated_sheets(
    xlsx_path: Path,
    output_path: Path,
    road_headers: list[str],
    road_rows: list[dict[str, str]],
    case_headers: list[str],
    case_rows: list[dict[str, str]],
) -> None:
    with zipfile.ZipFile(xlsx_path, "r") as src_zip:
        sheet_map = xlsx_utils.read_workbook_sheet_map(src_zip)
        road_sheet_path = sheet_map["road_sign"]
        case_sheet_path = sheet_map["accident_case"]
        road_xml = build_sheet_xml(road_headers, road_rows)
        case_xml = build_sheet_xml(case_headers, case_rows)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as dst_zip:
            for item in src_zip.infolist():
                data = src_zip.read(item.filename)
                if item.filename == road_sheet_path:
                    data = road_xml
                elif item.filename == case_sheet_path:
                    data = case_xml
                dst_zip.writestr(item, data)


def main() -> int:
    args = parse_args()
    xlsx_path = Path(args.xlsx).resolve()
    road_csv_path = Path(args.road_sign_csv).resolve()
    case_csv_path = Path(args.accident_case_csv).resolve()
    output_xlsx_path = Path(args.output_xlsx).resolve()

    if not xlsx_path.exists():
        raise FileNotFoundError(f"Workbook not found: {xlsx_path}")

    _, _, road_rows, case_rows = xlsx_utils.load_all_xlsx(xlsx_path)
    if not road_rows or not case_rows:
        raise ValueError("road_sign or accident_case sheet is empty.")

    road_headers = list(road_rows[0].keys())
    case_headers = list(case_rows[0].keys())

    road_additions = draft_road_sign_rows(next_numeric_id(road_rows, "sign_id", "S"))
    case_additions = draft_accident_case_rows(next_numeric_id(case_rows, "case_id", "C"))

    merged_road_rows = merge_rows(road_rows, road_additions, "sign_id")
    merged_case_rows = merge_rows(case_rows, case_additions, "case_id")

    write_csv(road_csv_path, road_headers, road_additions)
    write_csv(case_csv_path, case_headers, case_additions)
    write_workbook_with_updated_sheets(
        xlsx_path,
        output_xlsx_path,
        road_headers,
        merged_road_rows,
        case_headers,
        merged_case_rows,
    )

    print(f"Original road_sign rows: {len(road_rows)}")
    print(f"Added road_sign rows: {len(road_additions)}")
    print(f"Merged road_sign rows: {len(merged_road_rows)}")
    print(f"Original accident_case rows: {len(case_rows)}")
    print(f"Added accident_case rows: {len(case_additions)}")
    print(f"Merged accident_case rows: {len(merged_case_rows)}")
    print(f"Road sign draft CSV: {road_csv_path}")
    print(f"Accident case draft CSV: {case_csv_path}")
    print(f"Output workbook: {output_xlsx_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
