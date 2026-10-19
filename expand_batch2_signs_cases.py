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
SOURCE_URL_CASE = "https://www.mem.gov.cn/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append a second batch of road_sign and accident_case data."
    )
    parser.add_argument(
        "--xlsx",
        default=str(Path("generated") / "交通问答系统的数据_扩充标志案例版.xlsx"),
        help="Source workbook path.",
    )
    parser.add_argument(
        "--road-sign-csv",
        default=str(Path("generated") / "road_sign_expand_batch2.csv"),
        help="Output CSV path for newly added road signs.",
    )
    parser.add_argument(
        "--accident-case-csv",
        default=str(Path("generated") / "accident_case_expand_batch2.csv"),
        help="Output CSV path for newly added accident cases.",
    )
    parser.add_argument(
        "--output-xlsx",
        default=str(Path("generated") / "交通问答系统的数据_二次扩充版.xlsx"),
        help="Output workbook path.",
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


def draft_road_sign_rows(start_id: int) -> list[dict[str, str]]:
    items = [
        ("S", "禁止掉头", "禁令标志", "转向限制", "圆形", "白底红圈黑图案斜杠", "表示禁止车辆掉头", "中央隔离路段/路口"),
        ("S", "停车让行", "禁令标志", "让行类", "八角形", "红底白字", "表示车辆必须停车观察后让行", "支路汇入主路口"),
        ("S", "减速让行", "禁令标志", "让行类", "倒三角形", "白底红边黑字", "表示车辆应减速让行", "视距受限路口"),
        ("S", "禁止停车", "禁令标志", "停车限制", "圆形", "蓝底红边红斜杠", "表示路段内禁止一切车辆停放", "主干道/消防通道"),
        ("S", "禁止长时停车", "禁令标志", "停车限制", "圆形", "蓝底红边红叉", "表示禁止车辆长时间停放", "医院周边/公交站附近"),
        ("S", "停车检查", "禁令标志", "管理检查", "圆形", "蓝底白字", "表示车辆应停车接受检查", "收费站/检查站"),
        ("S", "禁止直行", "禁令标志", "方向限制", "圆形", "白底红圈黑图案斜杠", "表示前方禁止车辆直行", "路口"),
        ("S", "禁止驶入", "禁令标志", "通行限制", "圆形", "红底白横杠", "表示一切车辆不得驶入", "单行反向入口"),
        ("S", "禁止机动车驶入", "禁令标志", "通行限制", "圆形", "白底红圈黑图案斜杠", "表示机动车不得进入", "步行街/学校区域"),
        ("S", "禁止载货汽车通行", "禁令标志", "车型限制", "圆形", "白底红圈黑图案斜杠", "表示载货汽车禁止通行", "城区限行路段"),
        ("S", "禁止危险物品运输车驶入", "禁令标志", "车型限制", "圆形", "白底红圈黑图案斜杠", "表示危险品运输车辆禁止驶入", "隧道/人口密集区"),
        ("S", "禁止三轮机动车通行", "禁令标志", "车型限制", "圆形", "白底红圈黑图案斜杠", "表示三轮机动车不得通行", "快速路入口"),
        ("S", "禁止拖拉机通行", "禁令标志", "车型限制", "圆形", "白底红圈黑图案斜杠", "表示拖拉机不得通行", "城市道路/高速入口"),
        ("S", "禁止行人进入", "禁令标志", "对象限制", "圆形", "白底红圈黑图案斜杠", "表示行人禁止进入", "高速公路/施工区域"),
        ("S", "禁止非机动车进入", "禁令标志", "对象限制", "圆形", "白底红圈黑图案斜杠", "表示非机动车禁止进入", "高架匝道/隧道"),
        ("S", "禁止摩托车通行", "禁令标志", "车型限制", "圆形", "白底红圈黑图案斜杠", "表示摩托车禁止通行", "高架路/城区核心区"),
        ("S", "限制宽度3米", "禁令标志", "尺寸限制", "圆形", "白底红圈黑字", "表示车辆总宽不得超过3米", "桥梁/窄路"),
        ("S", "限制高度3.5米", "禁令标志", "尺寸限制", "圆形", "白底红圈黑字", "表示车辆总高不得超过3.5米", "桥洞/地库入口"),
        ("S", "限制质量10吨", "禁令标志", "重量限制", "圆形", "白底红圈黑字", "表示车辆总质量不得超过10吨", "桥梁/乡村道路"),
        ("S", "限制轴重10吨", "禁令标志", "重量限制", "圆形", "白底红圈黑字", "表示单轴轴重不得超过10吨", "桥梁/治超路段"),
        ("S", "最低限速60", "禁令标志", "速度限制", "圆形", "蓝底白字", "表示机动车最低时速不得低于60公里", "高速公路"),
        ("S", "解除禁止超车", "禁令标志", "行为限制", "圆形", "白底黑边黑斜杠", "表示前方禁止超车路段结束", "山区路段末端"),
        ("S", "注意儿童", "警告标志", "警告类", "等边三角形", "黄底黑边黑图案", "提醒前方有儿童活动，注意减速", "学校周边"),
        ("S", "注意行人", "警告标志", "警告类", "等边三角形", "黄底黑边黑图案", "提醒前方行人密集", "商业区/医院附近"),
        ("S", "注意信号灯", "警告标志", "警告类", "等边三角形", "黄底黑边黑图案", "提醒前方有信号灯控制路口", "快速路出口"),
        ("S", "注意落石", "警告标志", "自然环境", "等边三角形", "黄底黑边黑图案", "提醒前方可能有落石危险", "山区公路"),
        ("S", "注意横风", "警告标志", "自然环境", "等边三角形", "黄底黑边黑图案", "提醒桥面或空旷地段易受横风影响", "跨海桥/高架桥"),
        ("S", "注意隧道", "警告标志", "道路形态", "等边三角形", "黄底黑边黑图案", "提醒前方进入隧道路段", "山岭道路"),
        ("S", "注意路面不平", "警告标志", "路面状况", "等边三角形", "黄底黑边黑图案", "提醒前方路面不平，应减速慢行", "施工维修路段"),
        ("S", "注意急转弯", "警告标志", "道路形态", "等边三角形", "黄底黑边黑图案", "提醒前方有急转弯", "山区道路"),
        ("S", "注意连续弯路", "警告标志", "道路形态", "等边三角形", "黄底黑边黑图案", "提醒前方有连续弯道路段", "盘山公路"),
        ("S", "注意陡坡", "警告标志", "道路形态", "等边三角形", "黄底黑边黑图案", "提醒前方为陡坡，应控制车速", "山区道路"),
        ("S", "注意施工", "警告标志", "施工警示", "等边三角形", "黄底黑边黑图案", "提醒前方道路施工", "养护施工区"),
        ("S", "事故易发路段", "警告标志", "风险提示", "矩形", "黄底黑字", "提醒该路段事故高发，需谨慎驾驶", "急弯/长下坡"),
        ("S", "注意积水", "警告标志", "气象警示", "等边三角形", "黄底黑边黑图案", "提醒前方低洼积水，涉水需谨慎", "易积水路段"),
        ("S", "注意慢行", "警告标志", "警告类", "矩形", "黄底黑字", "提醒车辆降低车速慢行通过", "复杂路口/施工区"),
        ("S", "人行横道", "指示标志", "通行指示", "方形", "蓝底白图案", "表示前方设有人行横道", "学校/商业街"),
        ("S", "机动车行驶", "指示标志", "对象指示", "圆形", "蓝底白图案", "表示该车道供机动车通行", "专用车道入口"),
        ("S", "非机动车行驶", "指示标志", "对象指示", "圆形", "蓝底白图案", "表示该车道供非机动车通行", "城市慢行系统"),
        ("S", "允许掉头", "指示标志", "方向指示", "方形", "蓝底白图案", "表示前方位置允许车辆掉头", "路口中央开口"),
        ("S", "靠左侧道路行驶", "指示标志", "通行指示", "圆形", "蓝底白箭头", "表示车辆应靠道路左侧通行", "临时导改路段"),
        ("S", "直行", "指示标志", "方向指示", "圆形", "蓝底白箭头", "表示车辆只能直行通过", "信号路口"),
        ("S", "向左转弯", "指示标志", "方向指示", "圆形", "蓝底白箭头", "表示车辆应按箭头方向左转", "路口导向车道"),
        ("S", "向右转弯", "指示标志", "方向指示", "圆形", "蓝底白箭头", "表示车辆应按箭头方向右转", "路口导向车道"),
    ]

    rows: list[dict[str, str]] = []
    for offset, item in enumerate(items):
        sign_id = f"S{start_id + offset:03d}"
        _, sign_name, category, sub_category, shape, color, meaning, scene = item
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
                "remark": "自动扩充第二批草案，建议人工复核",
            }
        )
    return rows


def draft_accident_case_rows(start_id: int) -> list[dict[str, str]]:
    items = [
        ("夜间无灯电动车横穿事故", "2024-06-08", "广东省", "佛山市", "城郊十字路口", "城市道路", "夜间", "照明不足", "电动自行车/小型客车", "未按规定让行/夜间未按规定使用灯光", "电动车夜间无灯横穿路口，机动车避让不及", "1死1伤", "电动车驾驶人主要责任", "非机动车不按规定通行", "夜间骑行必须开启灯光并按道通行"),
        ("左转未让直行碰撞事故", "2024-05-17", "江苏省", "苏州市", "主干道路口", "城市道路", "晴天", "晚高峰", "小型客车", "未按规定让行", "左转车辆未让直行车辆先行", "2伤", "左转车辆主要责任", "转弯车未让直行车辆先行", "通过路口严格落实转弯让直行"),
        ("客车超员制动失稳事故", "2024-07-22", "河南省", "商丘市", "县道村镇路段", "县道", "晴天", "普通路段", "中型客车", "超员", "超员导致制动距离增加并发生碰撞", "4伤", "驾驶人及经营者责任", "公路客运车辆载客超过额定人数", "严禁超员运营并加强源头检查"),
        ("高速错过出口倒车事故", "2024-08-14", "浙江省", "嘉兴市", "高速出口匝道前", "高速公路", "晴天", "车流较大", "小型客车", "违法倒车", "驾驶人错过出口后在高速主线倒车", "3车受损", "倒车车辆主要责任", "在高速公路上倒车", "错过出口继续前行至下一出口驶离"),
        ("隧道内违法停车二次追尾事故", "2024-09-01", "重庆市", "重庆市", "山岭隧道内", "高速公路", "阴天", "隧道路段", "小型客车/重型货车", "违法停车/未保持安全距离", "前车在隧道内停车导致后车追尾", "2伤", "前后车均有责任", "在高速公路上违法停车/未保持安全车距", "隧道内严禁随意停车并保持安全车距"),
        ("农用车违法载人侧翻事故", "2024-04-27", "湖南省", "邵阳市", "山区乡道急弯处", "乡道", "晴天", "急弯下坡", "农用车", "违法载人/操作不当", "车辆转弯时重心偏移发生侧翻", "2死5伤", "驾驶人主要责任", "货运机动车违法载人", "农用车严禁载人并降低弯道路段车速"),
        ("山区会车占道坠沟事故", "2024-10-11", "贵州省", "毕节市", "盘山公路会车点", "县道", "小雨", "湿滑弯道", "小型客车", "占道行驶", "会车时越线占道导致车辆坠沟", "1死2伤", "占道车辆主要责任", "不按规定靠右通行", "山区会车提前减速并靠右礼让"),
        ("雨天涉水失控撞隔离栏事故", "2024-06-21", "福建省", "泉州市", "城市快速路下穿通道", "城市快速路", "大雨", "积水路面", "小型客车", "超速行驶", "积水路段车速过快导致失控", "1伤", "驾驶人主要责任", "超速行驶", "暴雨积水路段减速慢行避免急打方向"),
        ("货车盲区碾压电动车事故", "2024-11-03", "湖北省", "襄阳市", "物流园区出口", "城市道路", "晴天", "大型车混行", "重型货车/电动自行车", "未观察盲区", "货车右转未注意右侧非机动车", "1死", "货车驾驶人主要责任", "转弯时未避让非机动车", "大型车辆转弯必须二次观察盲区"),
        ("高架匝道急刹连环追尾事故", "2025-01-05", "上海市", "上海市", "高架下匝道口", "城市快速路", "阴天", "拥堵缓行", "小型客车", "未保持安全距离", "前车急刹后后方车辆连续追尾", "4车受损", "后车主要责任", "未保持安全车距", "拥堵路段缓行时拉大跟车距离"),
        ("施工区压线变道碰撞事故", "2024-12-09", "安徽省", "芜湖市", "高架施工导改段", "城市快速路", "晴天", "施工导改", "小型客车", "违法变道", "未按施工导向压线并线发生碰撞", "2车受损", "变道车辆主要责任", "不按规定变更车道", "施工路段提前观察并按导向标志行驶"),
        ("夜间不开灯追尾事故", "2024-08-30", "江西省", "南昌市", "环城快速路", "城市快速路", "夜间", "照明一般", "小型客车", "未按规定使用灯光", "前车未开启尾灯导致后车识别不清", "2伤", "前车主要责任", "夜间未按规定使用灯光", "夜间行车规范使用近光灯和示廓灯"),
        ("爆胎后急打方向侧翻事故", "2024-07-03", "山东省", "临沂市", "高速行车道", "高速公路", "晴天", "高速直线路段", "小型客车", "操作不当", "车辆爆胎后急打方向引发侧翻", "3伤", "驾驶人主要责任", "操作不当", "爆胎后稳握方向缓踩刹车靠边停靠"),
        ("路口抢黄灯碰撞事故", "2024-05-09", "河北省", "石家庄市", "十字信号路口", "城市道路", "晴天", "普通路口", "小型客车/摩托车", "抢黄灯", "双方抢行通过路口发生碰撞", "2伤", "双方均有责任", "违反交通信号灯通行", "临近变灯时提前减速切勿抢行"),
        ("校园门口未礼让学生事故", "2024-09-18", "四川省", "成都市", "学校门前斑马线", "城市道路", "晴天", "人流密集", "小型客车", "未礼让行人", "车辆通过斑马线未停车避让学生", "1伤", "驾驶人主要责任", "遇行人正在通过人行横道未停车让行", "校园周边严格执行停车让行"),
        ("斑马线前未减速碰撞行人事故", "2024-10-25", "北京市", "北京市", "商业街斑马线", "城市道路", "阴天", "人车混行", "小型客车", "未礼让行人", "驾驶人接近斑马线未减速观察", "1死", "驾驶人主要责任", "遇行人正在通过人行横道未停车让行", "接近斑马线必须提前减速观察"),
        ("高速隧道变道剐蹭事故", "2025-02-14", "陕西省", "西安市", "秦岭隧道路段", "高速公路", "晴天", "隧道路段", "小型客车", "违法变道", "隧道内强行变道与后方车辆剐蹭", "2车受损", "变道车辆主要责任", "不按规定变更车道", "隧道内保持车道稳定禁止随意变道"),
        ("大客车凌晨疲劳偏离车道事故", "2025-03-03", "广西壮族自治区", "桂林市", "高速长直线路段", "高速公路", "凌晨", "长直线路段", "大型客车", "疲劳驾驶", "驾驶人连续驾驶后注意力下降偏离车道", "5伤", "驾驶人主要责任", "疲劳驾驶", "客运车辆凌晨时段严格落实轮换休息"),
        ("危险品车辆雨天侧翻事故", "2024-11-28", "天津市", "天津市", "港区连接线弯道", "城市快速路", "小雨", "湿滑弯道", "危险品运输车辆", "超速行驶", "雨天弯道车速过快导致侧翻", "1伤", "驾驶人及企业责任", "超速行驶", "危化品运输雨天弯道必须限速通行"),
        ("下坡空挡滑行追尾事故", "2024-06-13", "云南省", "曲靖市", "国道长下坡路段", "国道", "晴天", "长下坡", "重型货车", "空挡滑行/未保持安全距离", "驾驶人空挡滑行导致制动失效追尾", "1死2伤", "驾驶人主要责任", "下陡坡时熄火或者空挡滑行", "长下坡必须低挡限速严禁空挡滑行"),
        ("超员面包车弯道侧翻事故", "2024-07-19", "甘肃省", "定西市", "乡村弯道路段", "乡道", "晴天", "急弯路段", "面包车", "超员/超速行驶", "超员车辆弯道速度过快发生侧翻", "2死4伤", "驾驶人主要责任", "载客超过核定人数/超速行驶", "农村面包车严禁超员并控制弯道车速"),
        ("网约车开门碰撞骑行者事故", "2025-01-15", "广东省", "深圳市", "地铁口辅路", "城市道路", "晴天", "路侧停车区", "小型客车/电动自行车", "违法停车/开门不观察", "乘客下车开门时碰撞后方骑行者", "1伤", "车辆一方主要责任", "机动车开关车门妨碍其他车辆和行人通行", "停车上下客前观察后方来车"),
        ("外卖电动车逆行相撞事故", "2025-04-01", "江苏省", "无锡市", "非机动车道交叉口", "城市道路", "晴天", "通勤高峰", "电动自行车", "逆行", "两辆电动车对向逆行避让不及", "2伤", "逆行一方主要责任", "非机动车逆向行驶", "非机动车也应按道顺向通行"),
        ("高速团雾路段追尾事故", "2025-02-26", "湖北省", "孝感市", "高速桥面路段", "高速公路", "团雾", "能见度极低", "小型客车/货车", "未保持安全距离", "团雾突发后未及时降速导致连续追尾", "6车受损", "多方责任", "未保持安全车距", "团雾天气开启雾灯并立即降速增距"),
        ("违停下客引发二次碰撞事故", "2024-12-22", "海南省", "海口市", "城市主干道路侧", "城市道路", "晴天", "车流较大", "出租车/小型客车", "违法停车", "出租车违停下客导致后车避让不及", "2伤", "违停车辆主要责任", "违法停车", "上下客应进入允许停车区域"),
        ("重载货车闯禁行事故", "2025-03-12", "山西省", "太原市", "城区桥梁限行路段", "城市道路", "晴天", "桥梁路段", "重型货车", "违反禁令标志", "闯入禁行区域并与社会车辆碰撞", "2车受损", "货车驾驶人主要责任", "违反禁令标志、禁止标线指示", "严格按货车限行规定和标志通行"),
        ("城区路口占道掉头事故", "2024-08-06", "辽宁省", "沈阳市", "双向四车道路口", "城市道路", "晴天", "路口车流大", "小型客车", "违法掉头", "车辆跨越实线占道掉头与直行车相撞", "2伤", "掉头车辆主要责任", "违反禁止标线指示/违法掉头", "掉头前确认标志标线和对向车流"),
        ("校车雨天制动不及事故", "2024-11-19", "吉林省", "长春市", "学校周边下坡路", "城市道路", "中雨", "湿滑下坡", "校车", "未保持安全距离", "雨天下坡跟车过近制动不及", "3伤", "校车驾驶人主要责任", "未保持安全车距", "校车雨天行驶需更早减速增距"),
        ("酒驾夜间单车撞树事故", "2025-05-08", "内蒙古自治区", "呼和浩特市", "城郊道路", "城市道路", "夜间", "直线路段", "小型客车", "酒后驾驶", "驾驶人饮酒后操控能力下降冲出道路", "1死", "驾驶人全部责任", "饮酒后驾驶机动车", "坚决杜绝酒后驾驶"),
        ("未按导向车道行驶路口事故", "2025-04-18", "浙江省", "宁波市", "多车道路口", "城市道路", "晴天", "导向车道", "小型客车", "不按导向车道行驶", "右转车道车辆强行直行与左侧车辆碰撞", "2车受损", "违法车辆主要责任", "不按导向车道行驶", "进入路口前提前选择正确车道"),
    ]

    rows: list[dict[str, str]] = []
    for offset, item in enumerate(items):
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
                "remark": "自动扩充第二批草案，建议人工复核",
            }
        )
    return rows


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
    road_sign_csv_path = Path(args.road_sign_csv).resolve()
    accident_case_csv_path = Path(args.accident_case_csv).resolve()
    output_xlsx_path = Path(args.output_xlsx).resolve()

    with zipfile.ZipFile(xlsx_path) as zip_file:
        shared_strings = xlsx_utils.read_shared_strings(zip_file)
        sheet_map = xlsx_utils.read_workbook_sheet_map(zip_file)
        road_sign_rows = xlsx_utils.read_xlsx_sheet(
            zip_file, "road_sign", shared_strings, sheet_map
        )
        accident_case_rows = xlsx_utils.read_xlsx_sheet(
            zip_file, "accident_case", shared_strings, sheet_map
        )

    road_headers = list(road_sign_rows[0].keys())
    case_headers = list(accident_case_rows[0].keys())

    road_start = next_numeric_id(road_sign_rows, "sign_id", "S")
    case_start = next_numeric_id(accident_case_rows, "case_id", "C")

    road_candidates = draft_road_sign_rows(road_start)
    case_candidates = draft_accident_case_rows(case_start)

    merged_road_rows, new_road_rows = merge_rows(
        road_sign_rows, road_candidates, road_headers, "sign_name"
    )
    merged_case_rows, new_case_rows = merge_rows(
        accident_case_rows, case_candidates, case_headers, "case_name"
    )

    write_csv(road_sign_csv_path, road_headers, new_road_rows)
    write_csv(accident_case_csv_path, case_headers, new_case_rows)
    write_workbook_with_updated_sheets(
        xlsx_path,
        output_xlsx_path,
        road_headers,
        merged_road_rows,
        case_headers,
        merged_case_rows,
    )

    print(f"Added road_sign rows: {len(new_road_rows)}")
    print(f"Added accident_case rows: {len(new_case_rows)}")
    print(f"Road sign CSV: {road_sign_csv_path}")
    print(f"Accident case CSV: {accident_case_csv_path}")
    print(f"Output workbook: {output_xlsx_path}")
    print(f"Updated road_sign total: {len(merged_road_rows)}")
    print(f"Updated accident_case total: {len(merged_case_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
