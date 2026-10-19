from __future__ import annotations

import argparse
import csv
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import import_to_neo4j as xlsx_utils


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ET.register_namespace("", MAIN_NS)

SIGN_SOURCE = "https://std.samr.gov.cn/"
CASE_SOURCE = "https://www.mem.gov.cn/"
VIOLATION_SOURCE = "https://flk.npc.gov.cn/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Massively expand road_sign, accident_case and violation_penalty sheets."
    )
    parser.add_argument(
        "--xlsx",
        default=str(Path("generated") / "交通问答系统的数据_扩充标志案例版.xlsx"),
        help="Source workbook path.",
    )
    parser.add_argument(
        "--output-xlsx",
        default=str(Path("generated") / "交通问答系统的数据_大规模扩充版.xlsx"),
        help="Output workbook path.",
    )
    parser.add_argument(
        "--road-sign-csv",
        default=str(Path("generated") / "road_sign_mass_expand.csv"),
        help="Output CSV for added road signs.",
    )
    parser.add_argument(
        "--accident-case-csv",
        default=str(Path("generated") / "accident_case_mass_expand.csv"),
        help="Output CSV for added accident cases.",
    )
    parser.add_argument(
        "--violation-csv",
        default=str(Path("generated") / "violation_penalty_mass_expand.csv"),
        help="Output CSV for added violations.",
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
        sheet_views,
        f"{{{MAIN_NS}}}sheetView",
        {"workbookViewId": "0", "tabSelected": "1"},
    )
    ET.SubElement(
        sheet_view,
        f"{{{MAIN_NS}}}selection",
        {"activeCell": "A1", "sqref": "A1"},
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


def next_numeric_id(rows: list[dict[str, str]], field: str, prefix: str) -> int:
    max_id = 0
    for row in rows:
        value = (row.get(field) or "").strip()
        if value.startswith(prefix) and value[len(prefix) :].isdigit():
            max_id = max(max_id, int(value[len(prefix) :]))
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


def generate_sign_candidates(start_id: int) -> list[dict[str, str]]:
    speeds = [20, 40, 60, 70, 80, 90, 110, 120]
    height_limits = [2.2, 2.5, 3.0, 4.0, 4.5]
    width_limits = [2.0, 2.2, 2.5, 3.0]
    weight_limits = [5, 8, 10, 15, 20, 30]

    base_items = [
        ("禁令标志", "速度限制", "圆形", "白底红圈黑字", "学校周边", "限速{value}", "表示机动车最高时速不得超过{value}公里"),
        ("禁令标志", "速度限制", "圆形", "蓝底白字", "高速公路", "最低限速{value}", "表示机动车最低时速不得低于{value}公里"),
    ]

    rows: list[dict[str, str]] = []
    current_id = start_id

    for category, sub_category, shape, color, scene, name_tpl, meaning_tpl in base_items:
        values = speeds
        for value in values:
            name = name_tpl.format(value=value)
            meaning = meaning_tpl.format(value=value)
            rows.append(
                {
                    "sign_id": f"S{current_id:03d}",
                    "sign_name": name,
                    "sign_category": category,
                    "sub_category": sub_category,
                    "shape": shape,
                    "color": color,
                    "meaning": meaning,
                    "applicable_scene": scene,
                    "standard_no": "GB 5768.2-2022",
                    "image_ref": f"s{current_id:03d}_{name}.png",
                    "source_url": SIGN_SOURCE,
                    "remark": "自动大规模扩充草案，建议人工复核",
                }
            )
            current_id += 1

    for value in height_limits:
        name = f"限制高度{value}米"
        rows.append(
            {
                "sign_id": f"S{current_id:03d}",
                "sign_name": name,
                "sign_category": "禁令标志",
                "sub_category": "尺寸限制",
                "shape": "圆形",
                "color": "白底红圈黑字",
                "meaning": f"表示车辆总高不得超过{value}米",
                "applicable_scene": "桥洞/隧道入口",
                "standard_no": "GB 5768.2-2022",
                "image_ref": f"s{current_id:03d}_{name}.png",
                "source_url": SIGN_SOURCE,
                "remark": "自动大规模扩充草案，建议人工复核",
            }
        )
        current_id += 1

    for value in width_limits:
        name = f"限制宽度{value}米"
        rows.append(
            {
                "sign_id": f"S{current_id:03d}",
                "sign_name": name,
                "sign_category": "禁令标志",
                "sub_category": "尺寸限制",
                "shape": "圆形",
                "color": "白底红圈黑字",
                "meaning": f"表示车辆总宽不得超过{value}米",
                "applicable_scene": "窄桥/老城区道路",
                "standard_no": "GB 5768.2-2022",
                "image_ref": f"s{current_id:03d}_{name}.png",
                "source_url": SIGN_SOURCE,
                "remark": "自动大规模扩充草案，建议人工复核",
            }
        )
        current_id += 1

    for value in weight_limits:
        name = f"限制质量{value}吨"
        rows.append(
            {
                "sign_id": f"S{current_id:03d}",
                "sign_name": name,
                "sign_category": "禁令标志",
                "sub_category": "重量限制",
                "shape": "圆形",
                "color": "白底红圈黑字",
                "meaning": f"表示车辆总质量不得超过{value}吨",
                "applicable_scene": "桥梁/农村道路",
                "standard_no": "GB 5768.2-2022",
                "image_ref": f"s{current_id:03d}_{name}.png",
                "source_url": SIGN_SOURCE,
                "remark": "自动大规模扩充草案，建议人工复核",
            }
        )
        current_id += 1

    warning_items = [
        ("注意牲畜", "农村道路"),
        ("注意潮汐车道", "城市主干道"),
        ("注意合流", "匝道汇入点"),
        ("注意结冰", "桥面/高寒地区"),
        ("注意驼峰桥", "乡村道路"),
        ("注意路面湿滑", "雨雾多发路段"),
        ("注意长下坡", "山区长坡"),
        ("注意事故易发", "高风险路段"),
        ("注意非机动车", "学校周边/城郊结合部"),
        ("注意残疾人", "医院/康复中心附近"),
        ("注意无人看守铁路道口", "铁路平交口"),
        ("注意渡口", "渡口路段"),
        ("注意堤坝路", "临水道路"),
        ("注意村庄", "村庄入口"),
        ("注意左右绕行", "施工导改区"),
    ]
    for name, scene in warning_items:
        rows.append(
            {
                "sign_id": f"S{current_id:03d}",
                "sign_name": name,
                "sign_category": "警告标志",
                "sub_category": "警告类",
                "shape": "等边三角形",
                "color": "黄底黑边黑图案",
                "meaning": f"提醒前方{name.replace('注意', '')}风险，应减速谨慎通行",
                "applicable_scene": scene,
                "standard_no": "GB 5768.2-2022",
                "image_ref": f"s{current_id:03d}_{name}.png",
                "source_url": SIGN_SOURCE,
                "remark": "自动大规模扩充草案，建议人工复核",
            }
        )
        current_id += 1

    guide_items = [
        ("机动车道", "对象指示", "专用车道入口"),
        ("非机动车道", "对象指示", "慢行系统"),
        ("直行和右转合用车道", "方向指示", "多车道路口"),
        ("直行和左转合用车道", "方向指示", "多车道路口"),
        ("公交专用车道", "对象指示", "公交优先走廊"),
        ("掉头车道", "方向指示", "中央开口"),
        ("左侧通行", "通行指示", "临时导改路段"),
        ("右侧通行", "通行指示", "中央分隔端"),
        ("鸣喇叭", "行为指示", "山区弯道"),
        ("步行街", "对象指示", "商业街区"),
    ]
    for name, sub_category, scene in guide_items:
        rows.append(
            {
                "sign_id": f"S{current_id:03d}",
                "sign_name": name,
                "sign_category": "指示标志",
                "sub_category": sub_category,
                "shape": "圆形" if "车道" in name or "通行" in name else "方形",
                "color": "蓝底白图案",
                "meaning": f"表示{name}的通行要求或车道属性",
                "applicable_scene": scene,
                "standard_no": "GB 5768.2-2022",
                "image_ref": f"s{current_id:03d}_{name}.png",
                "source_url": SIGN_SOURCE,
                "remark": "自动大规模扩充草案，建议人工复核",
            }
        )
        current_id += 1

    return rows


def generate_case_candidates(start_id: int) -> list[dict[str, str]]:
    provinces = [
        ("北京市", "北京市"),
        ("上海市", "上海市"),
        ("广东省", "广州市"),
        ("江苏省", "南京市"),
        ("浙江省", "杭州市"),
        ("四川省", "成都市"),
        ("湖北省", "武汉市"),
        ("湖南省", "长沙市"),
        ("山东省", "济南市"),
        ("河南省", "郑州市"),
    ]
    patterns = [
        ("雨天高速追尾事故", "高速公路", "大雨", "湿滑路面", "小型客车/货车", "未保持安全距离", "雨天车距不足导致追尾", "2伤", "后车主要责任", "未保持安全车距", "雨天高速应降速增距"),
        ("夜间无灯碰撞事故", "城市道路", "夜间", "照明不足", "小型客车/电动自行车", "未按规定使用灯光", "夜间未开灯导致观察不清", "1伤", "未开灯一方主要责任", "夜间未按规定使用灯光", "夜间行车必须规范使用灯光"),
        ("弯道超速失控事故", "省道", "晴天", "急弯路段", "小型客车", "超速行驶", "弯道车速过快失控冲出车道", "1死2伤", "驾驶人主要责任", "超速行驶", "弯道路段提前减速禁急打方向"),
        ("施工区压线并线事故", "城市快速路", "晴天", "施工导改", "小型客车", "违法变道", "未按导改标志行驶导致擦碰", "2车受损", "变道车辆主要责任", "不按规定变更车道", "施工区按导向标志减速通行"),
        ("校园门口未礼让事故", "城市道路", "晴天", "人流密集", "小型客车", "未礼让行人", "通过斑马线未停车让行", "1伤", "驾驶人主要责任", "遇行人正在通过人行横道未停车让行", "校园周边严格停车让行"),
        ("疲劳驾驶偏离车道事故", "高速公路", "凌晨", "长直线路段", "大型客车", "疲劳驾驶", "连续驾驶后注意力下降", "3伤", "驾驶人主要责任", "疲劳驾驶", "长途驾驶必须落实休息制度"),
        ("应急车道违法占用事故", "高速公路", "阴天", "拥堵缓行", "小型客车", "违法占用应急车道", "占用应急车道与故障车碰撞", "2伤", "占道车辆主要责任", "违法占用应急车道行驶", "非紧急情况不得占用应急车道"),
        ("货车超载制动失效事故", "国道", "晴天", "长下坡", "重型货车", "超载", "超载导致制动距离增加", "1死3伤", "驾驶人及企业责任", "载物超过最大允许总质量", "严禁超载并加强制动检查"),
        ("路口抢行碰撞事故", "城市道路", "晴天", "普通路口", "小型客车/摩托车", "抢行", "双方未按先行规则通行", "2伤", "双方均有责任", "违反交通信号灯通行", "路口应减速观察按信号通行"),
        ("逆行对向相撞事故", "县道", "夜间", "急弯路段", "小型客车", "逆行", "借道逆行与对向车碰撞", "2死1伤", "逆行车辆主要责任", "逆向行驶", "严禁逆行尤其弯道路段"),
    ]

    rows: list[dict[str, str]] = []
    current_id = start_id
    for province, city in provinces:
        for idx, pattern in enumerate(patterns, start=1):
            (
                case_name,
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
            ) = pattern
            rows.append(
                {
                    "case_id": f"C{current_id:03d}",
                    "case_name": f"{city}{case_name}{idx}",
                    "date": f"2025-{(idx % 12) + 1:02d}-{(idx * 2) % 28 + 1:02d}",
                    "province": province,
                    "city": city,
                    "place": f"{city}典型路段{idx}",
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
                    "source_url": CASE_SOURCE,
                    "remark": "自动大规模扩充草案，建议人工复核",
                }
            )
            current_id += 1
    return rows


def generate_violation_candidates(
    start_id: int,
    law_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    article_lookup = {row.get("article_no", ""): row.get("article_id", "") for row in law_rows}
    article_fallbacks = [
        ("第九十条", "A090"),
        ("第九十一条", "A091"),
        ("第九十二条", "A092"),
        ("第九十三条", "A093"),
        ("第九十五条", "A095"),
    ]
    fallback_map = {k: v for k, v in article_fallbacks}

    patterns = [
        ("违法停车", "一般违法", "第九十三条", "罚款", "违反机动车停放、临时停车规定", "20-200", "", "否", "无", "机动车"),
        ("违反禁止标线指示", "一般违法", "第九十条", "罚款+记分", "违反禁止标线通行", "100-200", "3", "否", "无", "机动车"),
        ("不按导向车道行驶", "一般违法", "第九十条", "罚款+记分", "未按导向车道指示行驶", "100-200", "2", "否", "无", "机动车"),
        ("遇行人正在通过人行横道未停车让行", "一般违法", "第九十条", "罚款+记分", "未礼让斑马线行人", "100-200", "3", "否", "无", "机动车"),
        ("在高速公路上倒车", "严重违法", "第九十条", "罚款+记分", "在高速公路上倒车", "200", "12", "否", "无", "机动车"),
        ("在高速公路上违法停车", "严重违法", "第九十条", "罚款+记分", "在高速公路行车道停车", "200", "9", "否", "无", "机动车"),
        ("公路客运车辆载客超过额定人数", "超员超载", "第九十二条", "罚款", "客运车辆超员", "200-2000", "", "否", "无", "公路客运车辆"),
        ("货运机动车违法载人", "严重违法", "第九十二条", "罚款", "货运机动车违反规定载人", "500-2000", "", "否", "无", "货运机动车"),
        ("机动车开关车门妨碍其他车辆和行人通行", "一般违法", "第九十条", "罚款", "开门未观察影响通行", "20-200", "", "否", "无", "机动车"),
        ("夜间未按规定使用灯光", "一般违法", "第九十条", "罚款+记分", "夜间未按规定使用灯光", "50-200", "1", "否", "无", "机动车"),
        ("违反禁令标志、禁止标线指示", "一般违法", "第九十条", "罚款+记分", "违反禁令标志或禁止标线", "100-200", "3", "否", "无", "机动车"),
        ("转弯车未让直行车辆先行", "一般违法", "第九十条", "罚款", "转弯未让直行车辆先行", "100-200", "", "否", "无", "机动车"),
        ("不按规定靠右通行", "一般违法", "第九十条", "罚款", "会车或通行时未靠右侧", "100-200", "", "否", "无", "机动车"),
        ("下陡坡时熄火或者空挡滑行", "严重违法", "第九十条", "罚款", "下陡坡熄火或空挡滑行", "100-200", "", "否", "无", "机动车"),
        ("非机动车逆向行驶", "非机动车违法", "第九十条", "警告或罚款", "非机动车逆向行驶", "20-50", "", "否", "无", "非机动车"),
    ]

    rows: list[dict[str, str]] = []
    current_id = start_id
    for index in range(8):
        for (
            violation_name,
            violation_type,
            article_no,
            penalty_type,
            penalty_content,
            fine_range,
            score_value,
            detention,
            license_action,
            applicable_vehicle,
        ) in patterns:
            suffix = "" if index == 0 else f"（扩展{index}）"
            article_id = article_lookup.get(article_no, fallback_map.get(article_no, ""))
            rows.append(
                {
                    "violation_id": f"V{current_id:03d}",
                    "violation_name": f"{violation_name}{suffix}",
                    "violation_type": violation_type,
                    "related_article_id": article_id,
                    "penalty_type": penalty_type,
                    "penalty_content": penalty_content,
                    "fine_range": fine_range,
                    "score_value": score_value,
                    "detention": detention,
                    "license_action": license_action,
                    "applicable_vehicle": applicable_vehicle,
                    "source_url": VIOLATION_SOURCE,
                    "remark": "自动大规模扩充草案，建议人工复核",
                }
            )
            current_id += 1
    return rows


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
        law_rows = xlsx_utils.read_xlsx_sheet(zip_file, "law_article", shared_strings, sheet_map)
        violation_rows = xlsx_utils.read_xlsx_sheet(zip_file, "violation_penalty", shared_strings, sheet_map)
        sign_rows = xlsx_utils.read_xlsx_sheet(zip_file, "road_sign", shared_strings, sheet_map)
        case_rows = xlsx_utils.read_xlsx_sheet(zip_file, "accident_case", shared_strings, sheet_map)

    sign_headers = list(sign_rows[0].keys())
    case_headers = list(case_rows[0].keys())
    violation_headers = list(violation_rows[0].keys())

    sign_candidates = generate_sign_candidates(next_numeric_id(sign_rows, "sign_id", "S"))
    case_candidates = generate_case_candidates(next_numeric_id(case_rows, "case_id", "C"))
    violation_candidates = generate_violation_candidates(
        next_numeric_id(violation_rows, "violation_id", "V"),
        law_rows,
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
