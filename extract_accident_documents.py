from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

FIELDNAMES = [
    "case_id",
    "case_name",
    "date",
    "province",
    "city",
    "place",
    "road_name",
    "weather",
    "road_condition",
    "vehicle_type",
    "behavior",
    "cause",
    "casualties",
    "responsibility",
    "violation_name",
    "suggestion",
    "source_url",
    "remark",
]

SUPPORTED_GLOBS = ("*.docx", "*.txt", "*.doc", "*.pdf")

PROVINCES = [
    "北京市",
    "天津市",
    "上海市",
    "重庆市",
    "河北省",
    "山西省",
    "辽宁省",
    "吉林省",
    "黑龙江省",
    "江苏省",
    "浙江省",
    "安徽省",
    "福建省",
    "江西省",
    "山东省",
    "河南省",
    "湖北省",
    "湖南省",
    "广东省",
    "海南省",
    "四川省",
    "贵州省",
    "云南省",
    "陕西省",
    "甘肃省",
    "青海省",
    "台湾省",
    "内蒙古自治区",
    "广西壮族自治区",
    "西藏自治区",
    "宁夏回族自治区",
    "新疆维吾尔自治区",
    "香港特别行政区",
    "澳门特别行政区",
]

WEATHER_KEYWORDS = [
    "晴",
    "阴",
    "小雨",
    "中雨",
    "大雨",
    "暴雨",
    "雨",
    "小雪",
    "中雪",
    "大雪",
    "雪",
    "冰雪",
    "雾",
    "大雾",
    "霾",
    "沙尘",
    "雷电",
]

ROAD_CONDITION_KEYWORDS = [
    "干燥",
    "湿滑",
    "积水",
    "结冰",
    "冰雪路面",
    "施工路段",
    "弯道",
    "下坡",
    "上坡",
    "拥堵",
    "能见度低",
    "夜间照明不足",
]

VEHICLE_KEYWORDS = [
    "小型客车",
    "大型客车",
    "重型货车",
    "半挂车",
    "危险品运输车",
    "校车",
    "公交车",
    "摩托车",
    "电动自行车",
    "自行车",
]

BEHAVIOR_TO_VIOLATION = {
    "酒后驾驶": "饮酒后驾驶机动车",
    "醉酒驾驶": "醉酒驾驶机动车",
    "超速": "超速行驶",
    "疲劳驾驶": "疲劳驾驶",
    "违法变道": "不按规定变更车道",
    "未保持安全距离": "未保持安全车距",
    "闯红灯": "违反交通信号灯通行",
    "逆行": "逆向行驶",
    "违法占用应急车道": "违法占用应急车道行驶",
    "无证驾驶": "未取得机动车驾驶证驾驶机动车",
    "分心驾驶": "妨碍安全驾驶行为",
    "超载": "载物超过最大允许总质量",
    "未按规定让行": "不按规定避让行人",
}

BEHAVIOR_PATTERNS = [
    ("酒后驾驶", r"酒后驾驶|饮酒驾驶"),
    ("醉酒驾驶", r"醉酒驾驶"),
    ("超速", r"超速"),
    ("疲劳驾驶", r"疲劳驾驶"),
    ("违法变道", r"违法变道|强行并线|不按规定变更车道"),
    ("未保持安全距离", r"未保持安全距离|未保持安全车距|追尾"),
    ("闯红灯", r"闯红灯|违反交通信号灯"),
    ("逆行", r"逆行|逆向行驶"),
    ("违法占用应急车道", r"占用应急车道|违法占用应急车道"),
    ("无证驾驶", r"无证驾驶|未取得驾驶证"),
    ("分心驾驶", r"分心驾驶|使用手机"),
    ("超载", r"超载"),
    ("未按规定让行", r"未让行|不按规定让行|未按规定避让"),
]

EXCLUDE_LAW_NAME_HINTS = [
    "交通安全法",
    "实施条例",
    "法律",
    "法规",
    "办法",
]

ACCIDENT_REPORT_HINTS = [
    "事故调查报告",
    "事故调查组",
    "事故发生经过",
    "事故原因",
    "直接原因",
    "间接原因",
    "责任认定",
    "处理建议",
    "防范措施",
    "整改措施",
    "较大",
    "重大",
    "一般道路交通事故",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract traffic accident documents to accident_case CSV."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="A file path or a folder path containing docx/txt/doc/pdf files.",
    )
    parser.add_argument(
        "--output",
        default=str(Path("generated") / "extracted_accident_cases.csv"),
        help="Output CSV path.",
    )
    parser.add_argument(
        "--start-id",
        type=int,
        default=100,
        help="Start number for case_id, default: %(default)s (e.g. C100).",
    )
    parser.add_argument(
        "--source-url",
        default="",
        help="Optional source URL written into every row.",
    )
    parser.add_argument(
        "--remark",
        default="自动从事故文档抽取，建议人工复核",
        help="Remark written into every row.",
    )
    return parser.parse_args()


def clean_line(text: str) -> str:
    text = text.replace("\u3000", " ").replace("\ufeff", "").strip()
    return re.sub(r"[ \t]+", " ", text)


def clean_block(text: str) -> str:
    lines = [clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def read_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))

    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", WORD_NS):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", WORD_NS)]
        line = clean_line("".join(texts))
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def read_txt_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"Cannot decode {path}")


def run_external_text_tool(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"External tool failed: {' '.join(command)}\n{completed.stderr.strip()}"
        )
    return completed.stdout


def read_pdf_text(path: Path) -> str:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        raise ValueError(
            "PDF not supported currently. Install pdftotext, or convert PDF to TXT/DOCX first."
        )
    return run_external_text_tool([pdftotext, "-layout", str(path), "-"])


def read_doc_text(path: Path) -> str:
    antiword = shutil.which("antiword")
    if antiword:
        return run_external_text_tool([antiword, str(path)])

    soffice = shutil.which("soffice")
    if soffice:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            completed = subprocess.run(
                [soffice, "--headless", "--convert-to", "txt:Text", "--outdir", str(temp_path), str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"soffice conversion failed for {path.name}: {completed.stderr.strip()}"
                )
            txt_path = temp_path / f"{path.stem}.txt"
            if not txt_path.exists():
                raise RuntimeError(f"Converted txt not found for {path.name}")
            return txt_path.read_text(encoding="utf-8", errors="ignore")

    raise ValueError(
        "DOC not supported currently. Install antiword/LibreOffice, or convert DOC to DOCX first."
    )


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return read_docx_text(path)
    if suffix == ".txt":
        return read_txt_text(path)
    if suffix == ".pdf":
        return read_pdf_text(path)
    if suffix == ".doc":
        return read_doc_text(path)
    raise ValueError(f"Unsupported file type: {path}")


def is_law_document(file_path: Path, text: str) -> bool:
    stem = file_path.stem
    if any(hint in stem for hint in EXCLUDE_LAW_NAME_HINTS):
        return True
    # Common law structure markers: many "第X条" with chapter markers.
    article_hits = len(re.findall(r"第[一二三四五六七八九十百千万0-9]+条", text))
    chapter_hits = len(re.findall(r"第[一二三四五六七八九十百千万0-9]+章", text))
    if article_hits >= 30 and chapter_hits >= 2 and "事故调查报告" not in text:
        return True
    return False


def looks_like_accident_report(file_path: Path, text: str) -> bool:
    stem = file_path.stem
    if "事故" in stem and ("调查" in stem or "报告" in stem):
        return True
    if "事故" not in text:
        return False
    hit_count = sum(1 for hint in ACCIDENT_REPORT_HINTS if hint in text)
    return hit_count >= 2


def iter_input_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    files: list[Path] = []
    for pattern in SUPPORTED_GLOBS:
        files.extend(input_path.rglob(pattern))
    return sorted(files)


def split_sentences(text: str) -> list[str]:
    raw = re.split(r"[。！？；\n]+", text)
    return [clean_line(item) for item in raw if clean_line(item)]


def first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    return match.group(0) if match else ""


def normalize_date(date_text: str) -> str:
    if not date_text:
        return ""
    m = re.search(r"(\d{4})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})", date_text)
    if not m:
        return ""
    y, mth, d = m.groups()
    return f"{int(y):04d}-{int(mth):02d}-{int(d):02d}"


def extract_date(text: str) -> str:
    date_raw = first_match(r"\d{4}[年\-/\.]\d{1,2}[月\-/\.]\d{1,2}日?", text)
    return normalize_date(date_raw)


def extract_case_name(lines: list[str], stem: str) -> str:
    for line in lines[:10]:
        if "事故" in line and len(line) <= 80:
            return line
    return f"{stem}交通事故"


def extract_province(text: str) -> str:
    for province in PROVINCES:
        if province in text:
            return province
    return ""


def extract_city(text: str) -> str:
    match = re.search(r"([\u4e00-\u9fa5]{2,10}(?:市|州|盟))", text)
    return match.group(1) if match else ""


def extract_place(sentences: list[str]) -> str:
    patterns = [
        r"在(.{3,60}?)发生",
        r"事故发生于(.{3,60})",
        r"事故地点[:：]\s*(.{3,60})",
    ]
    for sentence in sentences:
        for pattern in patterns:
            match = re.search(pattern, sentence)
            if match:
                return clean_line(match.group(1))
    return ""


def extract_road_name(text: str) -> str:
    patterns = [
        r"(G\d+\S{0,12})",
        r"(S\d+\S{0,12})",
        r"((?:高速公路|国道|省道|县道|乡道)[^\s，。；]{0,20})",
        r"([\u4e00-\u9fa5A-Za-z0-9]+路[^\s，。；]{0,12})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return clean_line(match.group(1))
    return ""


def extract_keywords(text: str, keywords: list[str]) -> list[str]:
    found: list[str] = []
    for keyword in keywords:
        if keyword in text and keyword not in found:
            found.append(keyword)
    return found


def extract_behaviors(text: str) -> list[str]:
    found: list[str] = []
    for name, pattern in BEHAVIOR_PATTERNS:
        if re.search(pattern, text) and name not in found:
            found.append(name)
    return found


def extract_cause(sentences: list[str]) -> str:
    for sentence in sentences:
        if "直接原因" in sentence or "事故原因" in sentence:
            return sentence
    for sentence in sentences:
        if "导致" in sentence and "事故" in sentence:
            return sentence
    return ""


def extract_casualties(text: str) -> str:
    death = re.search(r"(\d+)人死亡", text)
    injury = re.search(r"(\d+)人受伤", text)
    one_death = "1人死亡" if "死亡" in text and not death else ""
    one_injury = "1人受伤" if "受伤" in text and not injury else ""

    parts: list[str] = []
    if death:
        parts.append(f"{death.group(1)}人死亡")
    elif one_death:
        parts.append(one_death)
    if injury:
        parts.append(f"{injury.group(1)}人受伤")
    elif one_injury:
        parts.append(one_injury)
    return "，".join(parts)


def extract_responsibility(sentences: list[str]) -> str:
    for sentence in sentences:
        if "责任" in sentence and ("承担" in sentence or "认定" in sentence):
            return sentence
    for sentence in sentences:
        if "责任" in sentence:
            return sentence
    return ""


def build_violation_names(behaviors: list[str]) -> str:
    names: list[str] = []
    for behavior in behaviors:
        violation = BEHAVIOR_TO_VIOLATION.get(behavior, "")
        if violation and violation not in names:
            names.append(violation)
    return "/".join(names)


def build_suggestion(behaviors: list[str], weather: list[str], road_condition: list[str]) -> str:
    if "酒后驾驶" in behaviors or "醉酒驾驶" in behaviors:
        return "严格杜绝酒驾醉驾，落实代驾或指定驾驶人。"
    if "疲劳驾驶" in behaviors:
        return "连续驾驶应依法停车休息，避免疲劳驾驶。"
    if "超速" in behaviors:
        return "按限速标志控制车速，特殊天气提前减速。"
    if "违法占用应急车道" in behaviors:
        return "非紧急情况不得占用应急车道。"
    if "雨" in "".join(weather) or "雪" in "".join(weather) or "冰雪路面" in road_condition:
        return "恶劣天气应降速、增距、谨慎制动。"
    return "加强安全驾驶教育，规范操作并提前预判风险。"


def build_case_row(
    file_path: Path,
    text: str,
    case_id: str,
    source_url: str,
    remark: str,
) -> dict[str, str]:
    cleaned = clean_block(text)
    lines = [line for line in cleaned.splitlines() if line]
    sentences = split_sentences(cleaned)

    weather = extract_keywords(cleaned, WEATHER_KEYWORDS)
    road_condition = extract_keywords(cleaned, ROAD_CONDITION_KEYWORDS)
    vehicle_type = extract_keywords(cleaned, VEHICLE_KEYWORDS)
    behaviors = extract_behaviors(cleaned)

    return {
        "case_id": case_id,
        "case_name": extract_case_name(lines, file_path.stem),
        "date": extract_date(cleaned),
        "province": extract_province(cleaned),
        "city": extract_city(cleaned),
        "place": extract_place(sentences),
        "road_name": extract_road_name(cleaned),
        "weather": "/".join(weather),
        "road_condition": "/".join(road_condition),
        "vehicle_type": "/".join(vehicle_type),
        "behavior": "/".join(behaviors),
        "cause": extract_cause(sentences),
        "casualties": extract_casualties(cleaned),
        "responsibility": extract_responsibility(sentences),
        "violation_name": build_violation_names(behaviors),
        "suggestion": build_suggestion(behaviors, weather, road_condition),
        "source_url": source_url,
        "remark": f"{remark}；来源文件: {file_path.name}",
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    files = iter_input_files(input_path)
    if not files:
        print("No supported files found.")
        return 0

    rows: list[dict[str, str]] = []
    case_no = args.start_id
    skipped: list[str] = []

    for file_path in files:
        try:
            text = read_text(file_path)
            cleaned = clean_block(text)
            if not cleaned:
                skipped.append(f"{file_path.name}: empty content")
                continue
            if is_law_document(file_path, cleaned):
                skipped.append(f"{file_path.name}: looks like law/regulation document")
                continue
            if not looks_like_accident_report(file_path, cleaned):
                skipped.append(f"{file_path.name}: not a traffic accident report")
                continue

            case_id = f"C{case_no:03d}"
            case_no += 1
            row = build_case_row(file_path, cleaned, case_id, args.source_url, args.remark)
            rows.append(row)
            print(f"{file_path.name}: extracted -> {case_id}")
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"{file_path.name}: {exc}")

    write_csv(output_path, rows)

    print(f"\nTotal extracted cases: {len(rows)}")
    print(f"Output CSV: {output_path}")
    if skipped:
        print("\nSkipped files:")
        for item in skipped:
            print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
