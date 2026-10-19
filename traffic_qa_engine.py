from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from import_to_neo4j import clean_text


INTENT_PENALTY = "penalty"
INTENT_LAW = "law"
INTENT_SIGN = "sign"
INTENT_ACCIDENT = "accident"
INTENT_REASONING = "reasoning"
INTENT_OVERVIEW = "overview"
INTENT_UNKNOWN = "unknown"


INTENT_LABELS = {
    INTENT_PENALTY: "处罚问答",
    INTENT_LAW: "法规问答",
    INTENT_SIGN: "标志问答",
    INTENT_ACCIDENT: "事故问答",
    INTENT_REASONING: "场景推理",
    INTENT_OVERVIEW: "图谱检索",
    INTENT_UNKNOWN: "通用问答",
}


PENALTY_KEYWORDS = ["处罚", "罚款", "扣分", "记分", "拘留", "吊销", "暂扣", "处理", "违法成本"]
LAW_KEYWORDS = ["法条", "法律", "法规", "条文", "第", "条", "依据", "规定", "要求"]
SIGN_KEYWORDS = ["标志", "标线", "什么意思", "含义", "代表什么", "这个标志", "指示什么", "牌子"]
ACCIDENT_KEYWORDS = ["事故", "风险", "案例", "原因", "隐患", "后果", "建议", "教训", "危险", "预防", "伤亡"]
REASONING_ACTION_WORDS = ["如何操作", "怎么操作", "该如何", "该怎么", "怎么办", "怎么做", "如何处理", "如何应对", "应当怎样", "怎么通行", "应该怎么办"]
OVERVIEW_KEYWORDS = ["有哪些", "哪些", "列出", "汇总", "统计", "数量", "数据量", "多少条", "多少个", "多少类", "清单", "列表"]
FOLLOW_UP_WORDS = [
    "这个",
    "这个标志",
    "这个行为",
    "这一条",
    "这个处罚",
    "这种情况",
    "这种风险",
    "这种行为",
    "它",
    "那",
    "那么",
    "那相关",
    "那这个",
    "如何预防",
    "怎么预防",
    "还有类似案例",
]

STOP_WORDS = {
    "怎么",
    "怎样",
    "如何",
    "什么",
    "哪些",
    "有没有",
    "意思",
    "处罚",
    "罚款",
    "扣分",
    "记分",
    "多少",
    "几分",
    "规定",
    "相关",
    "法条",
    "法规",
    "法律",
    "机动车",
    "车辆",
    "交通",
    "安全",
    "相关",
    "查询",
    "列出",
    "一下",
    "有哪些",
}

VIOLATION_ALIASES: dict[str, list[str]] = {
    "酒后驾驶": ["酒后驾驶", "饮酒后驾驶", "饮酒驾驶", "酒驾", "饮酒后驾驶机动车"],
    "醉酒驾驶": ["醉酒驾驶", "醉驾", "醉酒驾车"],
    "闯红灯": ["闯红灯", "违反交通信号灯通行", "红灯通行"],
    "超速行驶": ["超速", "超速行驶", "速度过快"],
    "违法占用应急车道": ["应急车道", "占用应急车道", "违法占用应急车道"],
    "驾驶时拨打手持电话": ["打电话", "开车打电话", "驾驶时拨打手持电话"],
    "不按规定使用安全带": ["安全带", "不系安全带", "未使用安全带"],
    "疲劳驾驶": ["疲劳驾驶", "疲劳开车", "困倦驾驶"],
    "逆行": ["逆行", "逆向行驶"],
    "无证驾驶": ["无证驾驶", "没有驾驶证"],
    "违法停车": ["违法停车", "乱停车"],
    "未礼让行人": ["礼让行人", "不礼让行人", "未礼让行人"],
}

LAW_ALIASES: dict[str, list[str]] = {
    "中华人民共和国道路交通安全法": ["道路交通安全法", "交安法"],
    "中华人民共和国道路交通安全法实施条例": ["道路交通安全法实施条例", "实施条例"],
    "道路交通安全违法行为记分管理办法": ["记分管理办法"],
    "机动车驾驶证申领和使用规定": ["驾驶证申领和使用规定"],
}

SIGN_ALIASES: dict[str, list[str]] = {
    "限速60": ["限速60", "限速六十"],
    "停车让行": ["停车让行"],
    "注意儿童": ["注意儿童"],
    "人行横道": ["人行横道"],
    "施工": ["施工", "道路施工", "前方施工"],
}

WEATHER_ALIASES: dict[str, list[str]] = {
    "雨天": ["雨天", "下雨", "降雨", "雨天高速"],
    "大雾": ["大雾", "雾天", "浓雾"],
    "夜间": ["夜间", "晚上", "夜晚"],
    "雪天": ["雪天", "下雪"],
}

BEHAVIOR_ALIASES: dict[str, list[str]] = {
    "疲劳驾驶": ["疲劳驾驶", "疲劳开车"],
    "超速行驶": ["超速", "超速行驶"],
    "未保持安全车距": ["安全车距", "跟车太近"],
    "分心驾驶": ["分心驾驶", "注意力不集中"],
}

CONDITION_ALIASES: dict[str, list[str]] = {
    "路面湿滑": ["路面湿滑", "地面湿滑"],
    "能见度低": ["能见度低", "看不清"],
    "急弯": ["急弯", "弯道"],
    "长下坡": ["长下坡", "下陡坡"],
    "施工导改": ["施工", "施工路段", "道路施工", "施工导改"],
}

SCENE_ALIASES: dict[str, list[str]] = {
    "高速公路": ["高速", "高速公路"],
    "施工路段": ["施工", "施工路段", "道路施工", "施工导改"],
    "限速控制": ["限速", "临时限速", "限速标志", "限速牌"],
}

STATS_LABELS: dict[str, str] = {
    "法规": "Law",
    "法条": "Article",
    "违法行为": "Violation",
    "处罚": "Penalty",
    "道路标志": "RoadSign",
    "事故案例": "AccidentCase",
    "驾驶行为": "Behavior",
    "天气": "Weather",
    "道路条件": "RoadCondition",
}

SIGN_CATEGORY_TERMS: dict[str, list[str]] = {
    "禁令": ["禁令", "禁止", "限制"],
    "警告": ["警告", "注意", "危险"],
    "指示": ["指示", "准许", "通行"],
    "指路": ["指路", "方向", "地点", "距离"],
    "旅游区": ["旅游", "景区"],
    "辅助": ["辅助", "说明"],
}

CASE_SEARCH_TERMS = [
    "高速",
    "隧道",
    "桥梁",
    "交叉口",
    "农村",
    "山区",
    "施工",
    "弯道",
    "长下坡",
    "货车",
    "客车",
    "摩托车",
    "电动车",
    "行人",
    "追尾",
    "侧翻",
    "碰撞",
    "死亡",
    "受伤",
]


@dataclass
class AnswerSection:
    title: str
    lines: list[str]


@dataclass
class AnswerPayload:
    intent: str
    intent_label: str
    title: str
    summary: str
    sections: list[AnswerSection] = field(default_factory=list)
    related_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["answer"] = self.to_text()
        return data

    def to_text(self) -> str:
        lines = [self.title, self.summary]
        for section in self.sections:
            lines.append(f"\n{section.title}")
            lines.extend(f"- {line}" for line in section.lines)
        if self.related_questions:
            lines.append("\n你还可以继续问：")
            lines.extend(f"- {item}" for item in self.related_questions)
        return "\n".join(line for line in lines if line.strip())


@dataclass
class ConversationContext:
    last_intent: str = INTENT_UNKNOWN
    last_violation: str = ""
    last_sign: str = ""
    last_behavior: str = ""
    last_weather: str = ""
    last_condition: str = ""
    last_law: str = ""
    last_article_ref: str = ""
    last_question: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ConversationContext":
        if not data:
            return cls()
        values: dict[str, Any] = {}
        for field_name, field_def in cls.__dataclass_fields__.items():
            default = field_def.default if field_def.default is not field_def.default_factory else ""
            values[field_name] = data.get(field_name, default)
        return cls(**values)


def result_to_rows(result: Any) -> list[dict[str, Any]]:
    if hasattr(result, "records"):
        return list(result.records)
    return [dict(record) for record in result]


def contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def tokenize_question(text: str) -> list[str]:
    normalized = clean_text(text)
    for word in STOP_WORDS:
        normalized = normalized.replace(word, " ")
    tokens = re.split(r"[\s，。？！，；：,.!?;:/]+", normalized)
    return [token for token in tokens if len(token.strip()) >= 2]


def int_to_chinese(num: int) -> str:
    digits = "零一二三四五六七八九"
    if num <= 0:
        return str(num)
    if num < 10:
        return digits[num]
    if num < 20:
        return "十" + (digits[num % 10] if num % 10 else "")
    if num < 100:
        return digits[num // 10] + "十" + (digits[num % 10] if num % 10 else "")
    if num < 1000:
        head = digits[num // 100] + "百"
        rest = num % 100
        if rest == 0:
            return head
        if rest < 10:
            return head + "零" + digits[rest]
        return head + int_to_chinese(rest)
    return str(num)


def chinese_to_int(text: str) -> int | None:
    mapping = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if text.isdigit():
        return int(text)
    unit_map = {"十": 10, "百": 100, "千": 1000}
    total = 0
    current = 0
    for char in text:
        if char in mapping:
            current = mapping[char]
        elif char in unit_map:
            unit = unit_map[char]
            if current == 0:
                current = 1
            total += current * unit
            current = 0
        else:
            return None
    if current:
        total += current
    if total == 0 and text == "十":
        return 10
    return total or None


def normalize_article_refs(question: str) -> list[str]:
    refs: list[str] = []
    for match in re.findall(r"第\s*(\d+)\s*条", question):
        number = int(match)
        refs.append(f"第{number}条")
        refs.append(f"第{int_to_chinese(number)}条")
    for match in re.findall(r"第\s*([零一二三四五六七八九十百千万两]+)\s*条", question):
        cleaned = match.replace("兩", "两")
        refs.append(f"第{cleaned}条")
        number = chinese_to_int(cleaned)
        if number is not None:
            refs.append(f"第{number}条")
    return list(dict.fromkeys(refs))


def base_name(name: str) -> str:
    cleaned = clean_text(name)
    cleaned = re.sub(r"（扩展\d+）", "", cleaned)
    cleaned = re.sub(r"扩展\d+.*$", "", cleaned)
    return cleaned.strip()


def normalize_case_name(name: str) -> str:
    cleaned = base_name(name)
    cleaned = re.sub(r"^[\u4e00-\u9fa5]{2,12}市", "", cleaned)
    cleaned = re.sub(r"^[\u4e00-\u9fa5]{1,8}(?:新区|高新区|开发区|示范区|城区|区|县|市)", "", cleaned)
    return cleaned.strip() or base_name(name)


def normalize_case_place(place: str) -> str:
    cleaned = clean_text(place)
    cleaned = re.sub(r"^[\u4e00-\u9fa5]{2,12}市", "", cleaned)
    cleaned = re.sub(r"^[\u4e00-\u9fa5]{1,8}(?:新区|高新区|开发区|示范区|城区|区|县|市)", "", cleaned)
    return cleaned.strip()


def dedupe_keep_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = clean_text(value)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


class TrafficQAEngine:
    def __init__(self, session: Any, entities: dict[str, list[str]] | None = None) -> None:
        self.session = session
        self.entities = entities if entities is not None else self._load_entities()

    def _fetch_names(self, label: str, field: str = "name") -> list[str]:
        rows = result_to_rows(
            self.session.run(
                f"MATCH (n:{label}) WHERE n.{field} IS NOT NULL "
                f"RETURN n.{field} AS value ORDER BY toString(n.{field})"
            )
        )
        names = [clean_text(row.get("value")) for row in rows if clean_text(row.get("value"))]
        return dedupe_keep_order([base_name(name) for name in names] + names)

    def _load_entities(self) -> dict[str, list[str]]:
        return {
            "violations": self._fetch_names("Violation"),
            "laws": self._fetch_names("Law"),
            "signs": self._fetch_names("RoadSign"),
            "behaviors": self._fetch_names("Behavior"),
            "weathers": self._fetch_names("Weather"),
            "conditions": self._fetch_names("RoadCondition"),
        }

    def _score_name(self, question: str, name: str, aliases: list[str] | None = None) -> int:
        score = 0
        q = clean_text(question)
        n = clean_text(name)
        b = base_name(n)

        if b and b in q:
            score += 220 + len(b) * 4
        elif n and n in q:
            score += 200 + len(n) * 3

        tokens = tokenize_question(q)
        for token in tokens:
            if token == b:
                score += 120
            elif token in b:
                score += min(90, len(token) * 15)

        if aliases:
            for alias in aliases:
                alias_clean = clean_text(alias)
                if alias_clean and alias_clean in q:
                    score += 160 if alias_clean == b else 110

        if "扩展" in n:
            score -= 80
        return score

    def _best_alias_match(
        self,
        question: str,
        entity_names: list[str],
        alias_map: dict[str, list[str]],
        limit: int = 5,
    ) -> list[str]:
        scored: list[tuple[int, str]] = []
        for canonical, aliases in alias_map.items():
            candidates = [canonical] + aliases
            for candidate in candidates:
                candidate_base = base_name(candidate)
                if candidate_base not in entity_names and candidate not in entity_names:
                    continue
                score = self._score_name(question, candidate_base, aliases)
                if score > 0:
                    scored.append((score, candidate_base))
        if not scored:
            return []
        scored.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
        result: list[str] = []
        seen: set[str] = set()
        for _, name in scored:
            if name in seen:
                continue
            seen.add(name)
            result.append(name)
            if len(result) >= limit:
                break
        return result

    def _fuzzy_match(self, question: str, names: list[str], limit: int = 5) -> list[str]:
        scored: list[tuple[int, str]] = []
        for name in names:
            score = self._score_name(question, name)
            if score >= 60:
                scored.append((score, base_name(name)))
        scored.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
        result: list[str] = []
        seen: set[str] = set()
        for _, name in scored:
            if name in seen:
                continue
            seen.add(name)
            result.append(name)
            if len(result) >= limit:
                break
        return result

    def _match_violations(self, question: str, limit: int = 5) -> list[str]:
        matches = self._best_alias_match(question, self.entities["violations"], VIOLATION_ALIASES, limit=limit)
        if matches:
            return matches
        return self._fuzzy_match(question, self.entities["violations"], limit=limit)

    def _match_laws(self, question: str, limit: int = 3) -> list[str]:
        matches = self._best_alias_match(question, self.entities["laws"], LAW_ALIASES, limit=limit)
        if matches:
            return matches
        return self._fuzzy_match(question, self.entities["laws"], limit=limit)

    def _match_signs(self, question: str, limit: int = 3) -> list[str]:
        matches = self._best_alias_match(question, self.entities["signs"], SIGN_ALIASES, limit=limit)
        if matches:
            return matches
        return self._fuzzy_match(question, self.entities["signs"], limit=limit)

    def _match_behaviors(self, question: str, limit: int = 3) -> list[str]:
        matches = self._best_alias_match(question, self.entities["behaviors"], BEHAVIOR_ALIASES, limit=limit)
        if matches:
            return matches
        return self._fuzzy_match(question, self.entities["behaviors"], limit=limit)

    def _match_weathers(self, question: str, limit: int = 3) -> list[str]:
        matches = self._best_alias_match(question, self.entities["weathers"], WEATHER_ALIASES, limit=limit)
        if matches:
            return matches
        return self._fuzzy_match(question, self.entities["weathers"], limit=limit)

    def _match_conditions(self, question: str, limit: int = 3) -> list[str]:
        matches = self._best_alias_match(question, self.entities["conditions"], CONDITION_ALIASES, limit=limit)
        if matches:
            return matches
        return self._fuzzy_match(question, self.entities["conditions"], limit=limit)

    def _keyword_hits(self, question: str, alias_map: dict[str, list[str]]) -> list[str]:
        text = clean_text(question)
        hits: list[str] = []
        for name, aliases in alias_map.items():
            if any(alias in text for alias in [name] + aliases):
                hits.append(name)
        return dedupe_keep_order(hits)

    def _question_keywords(self, question: str, limit: int = 8) -> list[str]:
        text = clean_text(question)
        keywords = tokenize_question(text)
        keywords.extend(self._keyword_hits(text, WEATHER_ALIASES))
        keywords.extend(self._keyword_hits(text, CONDITION_ALIASES))
        keywords.extend(self._keyword_hits(text, SCENE_ALIASES))
        keywords.extend(self._keyword_hits(text, BEHAVIOR_ALIASES))
        keywords.extend(self._keyword_hits(text, VIOLATION_ALIASES))
        for term in CASE_SEARCH_TERMS:
            if term in text:
                keywords.append(term)
        return dedupe_keep_order([keyword for keyword in keywords if len(keyword) >= 2])[:limit]

    def _collect_reasoning_factors(self, question: str) -> dict[str, list[str]]:
        text = clean_text(question)
        return {
            "weather": self._match_weathers(text, limit=3),
            "condition": dedupe_keep_order(self._match_conditions(text, limit=3) + self._keyword_hits(text, CONDITION_ALIASES)),
            "sign": self._match_signs(text, limit=3),
            "behavior": self._match_behaviors(text, limit=3),
            "violation": self._match_violations(text, limit=3),
            "scene": self._keyword_hits(text, SCENE_ALIASES),
        }

    def _is_reasoning_question(self, question: str) -> bool:
        text = clean_text(question)
        if not contains_any(text, REASONING_ACTION_WORDS):
            return False
        factors = self._collect_reasoning_factors(text)
        factor_count = sum(1 for values in factors.values() if values)
        return factor_count >= 2

    def classify_intent(self, question: str) -> str:
        text = clean_text(question)

        if normalize_article_refs(text):
            return INTENT_LAW
        if self._is_reasoning_question(text):
            return INTENT_REASONING
        if contains_any(text, PENALTY_KEYWORDS) and self._match_violations(text, limit=1):
            return INTENT_PENALTY
        if contains_any(text, OVERVIEW_KEYWORDS):
            return INTENT_OVERVIEW
        if contains_any(text, SIGN_KEYWORDS) or self._match_signs(text, limit=1):
            return INTENT_SIGN
        if contains_any(text, PENALTY_KEYWORDS):
            return INTENT_PENALTY
        if contains_any(text, ACCIDENT_KEYWORDS):
            return INTENT_ACCIDENT
        if self._match_violations(text, limit=1):
            return INTENT_PENALTY
        if contains_any(text, LAW_KEYWORDS) or self._match_laws(text, limit=1):
            return INTENT_LAW
        if self._match_behaviors(text, limit=1) or self._match_weathers(text, limit=1) or self._match_conditions(text, limit=1):
            return INTENT_ACCIDENT
        return INTENT_UNKNOWN

    def answer(self, question: str, context: ConversationContext | None = None) -> tuple[AnswerPayload, ConversationContext]:
        ctx = context or ConversationContext()
        text = clean_text(question)

        if not text:
            payload = AnswerPayload(
                INTENT_UNKNOWN,
                INTENT_LABELS[INTENT_UNKNOWN],
                "未识别到问题",
                "请输入一个有效的中文问题。",
            )
            return payload, ctx

        intent = self.classify_intent(text)
        if intent == INTENT_UNKNOWN and ctx.last_intent != INTENT_UNKNOWN and self._looks_like_followup(text):
            intent = ctx.last_intent

        if intent == INTENT_PENALTY:
            payload, next_context = self._answer_penalty(text, ctx)
        elif intent == INTENT_LAW:
            payload, next_context = self._answer_law(text, ctx)
        elif intent == INTENT_SIGN:
            payload, next_context = self._answer_sign(text, ctx)
        elif intent == INTENT_REASONING:
            payload, next_context = self._answer_reasoning(text, ctx)
        elif intent == INTENT_OVERVIEW:
            payload, next_context = self._answer_overview(text, ctx)
        elif intent == INTENT_ACCIDENT:
            payload, next_context = self._answer_accident(text, ctx)
        else:
            payload, next_context = self._answer_unknown(text, ctx)

        return self._finalize_payload(payload, text), next_context

    def _finalize_payload(self, payload: AnswerPayload, question: str) -> AnswerPayload:
        question_key = re.sub(r"[\s，。？！，；：,.!?;:/]+", "", clean_text(question))
        cleaned_sections: list[AnswerSection] = []
        global_seen: set[str] = set()

        for section in payload.sections:
            lines: list[str] = []
            local_seen: set[str] = set()
            for line in section.lines:
                cleaned = clean_text(line)
                key = re.sub(r"[\s，。？！，；：,.!?;:/]+", "", cleaned)
                if not key or key in local_seen or key in global_seen:
                    continue
                local_seen.add(key)
                global_seen.add(key)
                lines.append(cleaned)
            if lines:
                cleaned_sections.append(AnswerSection(clean_text(section.title), lines))

        related_questions: list[str] = []
        seen_related: set[str] = set()
        for item in payload.related_questions:
            cleaned = clean_text(item)
            key = re.sub(r"[\s，。？！，；：,.!?;:/]+", "", cleaned)
            if not key or key == question_key or key in seen_related:
                continue
            seen_related.add(key)
            related_questions.append(cleaned)

        payload.sections = cleaned_sections
        payload.related_questions = related_questions[:5]
        payload.summary = clean_text(payload.summary)
        payload.title = clean_text(payload.title)
        return payload

    def _looks_like_followup(self, question: str) -> bool:
        text = clean_text(question)
        if len(text) <= 8:
            return True
        return contains_any(text, FOLLOW_UP_WORDS)

    def _query_rows(self, cypher: str, **parameters: object) -> list[dict[str, Any]]:
        return result_to_rows(self.session.run(cypher, **parameters))

    def _get_penalty_rows(self, violation_name: str) -> list[dict[str, Any]]:
        return self._query_rows(
            """
            MATCH (v:Violation)-[:PENALIZED_AS]->(p:Penalty)
            WHERE v.name = $name
            OPTIONAL MATCH (a:Article)-[:REGULATES]->(v)
            OPTIONAL MATCH (l:Law)-[:HAS_ARTICLE]->(a)
            RETURN v.name AS violation,
                   p.penalty_type AS penalty_type,
                   p.content AS content,
                   p.fine_range AS fine_range,
                   p.score_value AS score_value,
                   p.detention AS detention,
                   p.license_action AS license_action,
                   collect(DISTINCT a.article_no) AS article_refs,
                   collect(DISTINCT l.name) AS laws
            LIMIT 10
            """,
            name=violation_name,
        )

    def _get_law_rows_by_article_refs(self, article_refs: list[str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for ref in article_refs:
            rows.extend(
                self._query_rows(
                    """
                    MATCH (l:Law)-[:HAS_ARTICLE]->(a:Article)
                    WHERE a.article_no = $article_ref
                    RETURN l.name AS law_name, a.article_no AS article_no, a.title AS title, a.content AS content
                    ORDER BY a.article_no
                    LIMIT 10
                    """,
                    article_ref=ref,
                )
            )
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            key = (clean_text(row.get("law_name")), clean_text(row.get("article_no")))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped

    def _get_law_rows_by_violation(self, violation_name: str) -> list[dict[str, Any]]:
        return self._query_rows(
            """
            MATCH (l:Law)-[:HAS_ARTICLE]->(a:Article)-[:REGULATES]->(v:Violation)
            WHERE v.name = $name
            RETURN l.name AS law_name, a.article_no AS article_no, a.title AS title, a.content AS content
            ORDER BY a.article_no
            LIMIT 10
            """,
            name=violation_name,
        )

    def _get_law_rows_by_law(self, law_name: str) -> list[dict[str, Any]]:
        return self._query_rows(
            """
            MATCH (l:Law)-[:HAS_ARTICLE]->(a:Article)
            WHERE l.name = $name
            RETURN l.name AS law_name, a.article_no AS article_no, a.title AS title, a.content AS content
            ORDER BY a.article_no
            LIMIT 10
            """,
            name=law_name,
        )

    def _get_law_rows_by_keywords(self, keywords: list[str]) -> list[dict[str, Any]]:
        cleaned_keywords = dedupe_keep_order([clean_text(keyword) for keyword in keywords])[:8]
        if not cleaned_keywords:
            return []
        conditions = []
        parameters: dict[str, object] = {}
        for index, keyword in enumerate(cleaned_keywords):
            param_name = f"keyword_{index}"
            parameters[param_name] = keyword
            conditions.append(f"a.title CONTAINS ${param_name} OR a.content CONTAINS ${param_name}")
        where_clause = " OR ".join(f"({condition})" for condition in conditions)
        return self._query_rows(
            f"""
            MATCH (l:Law)-[:HAS_ARTICLE]->(a:Article)
            WHERE {where_clause}
            RETURN l.name AS law_name, a.article_no AS article_no, a.title AS title, a.content AS content
            ORDER BY l.name, a.article_no
            LIMIT 8
            """,
            **parameters,
        )

    def _get_entity_names(
        self,
        label: str,
        field: str = "name",
        limit: int = 20,
    ) -> list[str]:
        if label not in set(STATS_LABELS.values()):
            return []
        rows = self._query_rows(
            f"""
            MATCH (n:{label})
            WHERE n.{field} IS NOT NULL AND trim(toString(n.{field})) <> ''
            RETURN DISTINCT n.{field} AS value
            ORDER BY toString(value)
            LIMIT $limit
            """,
            limit=limit,
        )
        return dedupe_keep_order([clean_text(row.get("value")) for row in rows])

    def _get_graph_stats(self) -> dict[str, int]:
        stats: dict[str, int] = {}
        node_rows = self._query_rows("MATCH (n) RETURN count(n) AS count")
        relation_rows = self._query_rows("MATCH ()-[r]->() RETURN count(r) AS count")
        stats["节点"] = int(node_rows[0].get("count", 0)) if node_rows else 0
        stats["关系"] = int(relation_rows[0].get("count", 0)) if relation_rows else 0
        for name, label in STATS_LABELS.items():
            rows = self._query_rows(
                f"MATCH (n:{label}) RETURN count(n) AS count"
            )
            stats[name] = int(rows[0].get("count", 0)) if rows else 0
        return stats

    def _get_law_overview_rows(self, limit: int = 12) -> list[dict[str, Any]]:
        return self._query_rows(
            """
            MATCH (l:Law)
            OPTIONAL MATCH (l)-[:HAS_ARTICLE]->(a:Article)
            RETURN l.name AS name, count(a) AS article_count
            ORDER BY article_count DESC, name
            LIMIT $limit
            """,
            limit=limit,
        )

    def _get_sign_overview_rows(
        self,
        question: str,
        limit: int = 15,
    ) -> list[dict[str, Any]]:
        category_keyword = ""
        text = clean_text(question)
        for keyword, aliases in SIGN_CATEGORY_TERMS.items():
            if any(term in text for term in [keyword] + aliases):
                category_keyword = keyword
                break

        if category_keyword:
            return self._query_rows(
                """
                MATCH (s:RoadSign)
                WHERE s.category CONTAINS $keyword
                   OR s.sub_category CONTAINS $keyword
                   OR s.name CONTAINS $keyword
                RETURN DISTINCT s.name AS name,
                                s.category AS category,
                                s.meaning AS meaning
                ORDER BY toString(s.name)
                LIMIT $limit
                """,
                keyword=category_keyword,
                limit=limit,
            )
        return self._query_rows(
            """
            MATCH (s:RoadSign)
            RETURN DISTINCT s.name AS name,
                            s.category AS category,
                            s.meaning AS meaning
            ORDER BY toString(s.name)
            LIMIT $limit
            """,
            limit=limit,
        )

    def _get_case_overview_rows(self, question: str, limit: int = 8) -> list[dict[str, Any]]:
        factors = self._collect_reasoning_factors(question)
        rows: list[dict[str, Any]] = []
        for weather in factors.get("weather", [])[:1]:
            rows.extend(self._query_cases_by_rel("IN_WEATHER", "Weather", "name", weather))
        for behavior in factors.get("behavior", [])[:1]:
            rows.extend(self._query_cases_by_rel("HAS_BEHAVIOR", "Behavior", "name", behavior))
        for condition in factors.get("condition", [])[:1]:
            rows.extend(self._query_cases_by_rel("ON_CONDITION", "RoadCondition", "name", condition))
        for violation in factors.get("violation", [])[:1]:
            rows.extend(self._query_cases_by_rel("VIOLATES", "Violation", "name", violation))

        rows = self._dedupe_case_rows(rows)
        if rows:
            return rows[:limit]
        keyword_rows = self._get_case_rows_by_keywords(self._question_keywords(question), limit=limit)
        if keyword_rows:
            return keyword_rows
        return self._query_rows(
            """
            MATCH (c:AccidentCase)
            RETURN c.name AS case_name,
                   c.date AS date,
                   c.place AS place,
                   c.cause AS cause,
                   c.casualties AS casualties,
                   [] AS suggestions
            ORDER BY toString(c.date) DESC, toString(c.name)
            LIMIT $limit
            """,
            limit=limit,
        )

    def _get_case_rows_by_keywords(self, keywords: list[str], limit: int = 8) -> list[dict[str, Any]]:
        cleaned_keywords = dedupe_keep_order([clean_text(keyword) for keyword in keywords])[:8]
        if not cleaned_keywords:
            return []
        conditions = []
        parameters: dict[str, object] = {"limit": limit}
        for index, keyword in enumerate(cleaned_keywords):
            param_name = f"keyword_{index}"
            parameters[param_name] = keyword
            conditions.append(
                f"c.name CONTAINS ${param_name} OR c.place CONTAINS ${param_name} "
                f"OR c.road_name CONTAINS ${param_name} OR c.cause CONTAINS ${param_name} "
                f"OR c.casualties CONTAINS ${param_name}"
            )
        where_clause = " OR ".join(f"({condition})" for condition in conditions)
        rows = self._query_rows(
            f"""
            MATCH (c:AccidentCase)
            WHERE {where_clause}
            OPTIONAL MATCH (c)-[:HAS_SUGGESTION]->(s:Suggestion)
            RETURN c.name AS case_name,
                   c.date AS date,
                   c.place AS place,
                   c.cause AS cause,
                   c.casualties AS casualties,
                   collect(DISTINCT s.content) AS suggestions
            ORDER BY toString(c.date) DESC, toString(c.name)
            LIMIT $limit
            """,
            **parameters,
        )
        return self._dedupe_case_rows(rows)

    def _overview_targets(self, question: str) -> list[str]:
        text = clean_text(question)
        if contains_any(text, ["数据量", "图谱规模", "节点数", "关系数", "统计", "总量", "多少条关系"]):
            return ["stats"]
        if contains_any(text, ["事故案例", "事故", "案例", "风险", "隐患"]):
            return ["cases"]
        if contains_any(text, ["违法行为", "违法", "违章", "违规", "处罚", "扣分"]):
            return ["violations"]
        if contains_any(text, ["道路标志", "交通标志", "标志", "标线"]):
            return ["signs"]
        if contains_any(text, ["法条", "法规", "法律", "条文"]):
            return ["laws"]
        if contains_any(text, ["天气", "气象"]):
            return ["weathers"]
        if contains_any(text, ["驾驶行为", "行为"]):
            return ["behaviors"]
        if contains_any(text, ["道路条件", "路况", "路面"]):
            return ["conditions"]
        return ["stats"]

    def _answer_overview(
        self,
        question: str,
        context: ConversationContext,
    ) -> tuple[AnswerPayload, ConversationContext]:
        targets = self._overview_targets(question)
        sections: list[AnswerSection] = []
        summary = "系统已根据你的问题，从交通安全知识图谱中整理出可继续查询的内容。"

        if "stats" in targets:
            stats = self._get_graph_stats()
            stat_lines = [
                f"图谱节点：{stats.get('节点', 0)} 个；关系：{stats.get('关系', 0)} 条。",
                f"法规 {stats.get('法规', 0)} 个，法条 {stats.get('法条', 0)} 条。",
                f"违法行为 {stats.get('违法行为', 0)} 个，处罚记录 {stats.get('处罚', 0)} 条。",
                f"道路标志 {stats.get('道路标志', 0)} 个，事故案例 {stats.get('事故案例', 0)} 个。",
                f"驾驶行为 {stats.get('驾驶行为', 0)} 个，天气因素 {stats.get('天气', 0)} 个，道路条件 {stats.get('道路条件', 0)} 个。",
            ]
            sections.append(AnswerSection("图谱数据统计", stat_lines))
            summary = "当前图谱已经具备法规、违法处罚、道路标志和事故案例四类核心数据。"

        if "laws" in targets:
            rows = self._get_law_overview_rows()
            lines = [
                f"{clean_text(row.get('name'))}：约 {row.get('article_count', 0)} 条法条"
                for row in rows
                if clean_text(row.get("name"))
            ]
            if lines:
                sections.append(AnswerSection("法规清单", lines))

        if "violations" in targets:
            names = self._get_entity_names("Violation", limit=20)
            if names:
                sections.append(
                    AnswerSection(
                        "违法行为清单（部分）",
                        [f"{index}. {base_name(name)}" for index, name in enumerate(names, start=1)],
                    )
                )

        if "signs" in targets:
            rows = self._get_sign_overview_rows(question)
            lines = [
                f"{clean_text(row.get('name'))}：{clean_text(row.get('meaning')) or clean_text(row.get('category')) or '已有图谱记录'}"
                for row in rows
                if clean_text(row.get("name"))
            ]
            if lines:
                sections.append(AnswerSection("道路标志清单（部分）", lines))

        if "cases" in targets:
            rows = self._get_case_overview_rows(question)
            lines = []
            for row in rows:
                name = normalize_case_name(clean_text(row.get("case_name"))) or "未命名案例"
                detail = f"{name}：{clean_text(row.get('place')) or '地点未注明'}"
                if clean_text(row.get("cause")):
                    detail += f"；原因 {clean_text(row.get('cause'))}"
                if clean_text(row.get("casualties")):
                    detail += f"；伤亡 {clean_text(row.get('casualties'))}"
                lines.append(detail)
            if lines:
                sections.append(AnswerSection("事故案例（部分）", lines))
                summary = "系统已按问题中的天气、道路条件、驾驶行为或违法因素筛选事故案例。"

        if "weathers" in targets:
            names = self._get_entity_names("Weather", limit=15)
            if names:
                sections.append(AnswerSection("天气因素", names))

        if "behaviors" in targets:
            names = self._get_entity_names("Behavior", limit=15)
            if names:
                sections.append(AnswerSection("驾驶行为", names))

        if "conditions" in targets:
            names = self._get_entity_names("RoadCondition", limit=15)
            if names:
                sections.append(AnswerSection("道路条件", names))

        if not sections:
            payload = AnswerPayload(
                INTENT_OVERVIEW,
                INTENT_LABELS[INTENT_OVERVIEW],
                "暂未找到可展示的清单",
                "当前图谱中暂时没有匹配到这类内容，可以换成“有哪些违法行为”“有哪些道路标志”或“图谱数据量是多少”。",
                related_questions=["有哪些违法行为？", "有哪些道路标志？", "当前图谱数据量是多少？"],
            )
            return payload, context

        next_context = ConversationContext(
            last_intent=INTENT_OVERVIEW,
            last_question=question,
            last_violation=context.last_violation,
            last_sign=context.last_sign,
            last_behavior=context.last_behavior,
            last_weather=context.last_weather,
            last_condition=context.last_condition,
            last_law=context.last_law,
            last_article_ref=context.last_article_ref,
        )
        payload = AnswerPayload(
            INTENT_OVERVIEW,
            INTENT_LABELS[INTENT_OVERVIEW],
            "交通安全知识图谱检索结果",
            summary,
            sections=sections,
            related_questions=[
                "有哪些违法行为？",
                "有哪些道路标志？",
                "有哪些事故案例？",
                "当前图谱数据量是多少？",
            ],
        )
        return payload, next_context

    def _get_reasoning_case_rows(self, factors: dict[str, list[str]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for weather in factors.get("weather", [])[:1]:
            rows.extend(self._query_cases_by_rel("IN_WEATHER", "Weather", "name", weather))
        for condition in factors.get("condition", [])[:1]:
            rows.extend(self._query_cases_by_rel("ON_CONDITION", "RoadCondition", "name", condition))
        for behavior in factors.get("behavior", [])[:1]:
            rows.extend(self._query_cases_by_rel("HAS_BEHAVIOR", "Behavior", "name", behavior))
        for violation in factors.get("violation", [])[:1]:
            rows.extend(self._query_cases_by_rel("VIOLATES", "Violation", "name", violation))
        return self._dedupe_case_rows(rows)

    def _get_sign_row(self, sign_name: str) -> dict[str, Any] | None:
        rows = self._query_rows(
            """
            MATCH (s:RoadSign)
            WHERE s.name = $name
            RETURN s.name AS sign_name,
                   s.category AS category,
                   s.sub_category AS sub_category,
                   s.meaning AS meaning,
                   s.applicable_scene AS applicable_scene,
                   s.standard_no AS standard_no,
                   s.shape AS shape,
                   s.color AS color
            LIMIT 1
            """,
            name=sign_name,
        )
        return rows[0] if rows else None

    def _query_cases_by_rel(self, rel: str, label: str, field: str, value: str) -> list[dict[str, Any]]:
        return self._query_rows(
            f"""
            MATCH (c:AccidentCase)-[:{rel}]->(n:{label})
            WHERE n.{field} = $value
            OPTIONAL MATCH (c)-[:HAS_SUGGESTION]->(s:Suggestion)
            RETURN c.name AS case_name,
                   c.date AS date,
                   c.place AS place,
                   c.cause AS cause,
                   c.casualties AS casualties,
                   collect(DISTINCT s.content) AS suggestions
            LIMIT 8
            """,
            value=value,
        )

    def _dedupe_case_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        for row in rows:
            case_name = normalize_case_name(clean_text(row.get("case_name")))
            place = normalize_case_place(clean_text(row.get("place")))
            suggestions = "|".join(
                dedupe_keep_order([clean_text(item) for item in row.get("suggestions", [])])
            )
            key = (
                case_name,
                clean_text(row.get("date")),
                place,
                clean_text(row.get("cause")),
                clean_text(row.get("casualties")) or suggestions,
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped

    def _append_unique(self, lines: list[str], line: str, seen: set[str], key: str | None = None) -> None:
        normalized_key = clean_text(key or line)
        if not normalized_key or normalized_key in seen:
            return
        seen.add(normalized_key)
        lines.append(line)

    def _answer_penalty(self, question: str, context: ConversationContext) -> tuple[AnswerPayload, ConversationContext]:
        matches = self._match_violations(question, limit=4)
        if not matches and context.last_violation and self._looks_like_followup(question):
            matches = [context.last_violation]

        if not matches:
            payload = AnswerPayload(
                INTENT_PENALTY,
                INTENT_LABELS[INTENT_PENALTY],
                "未定位到具体违法行为",
                "我还没有识别到你想问的具体违法行为。你可以直接问“酒后驾驶怎么处罚”或“闯红灯扣几分”。",
                related_questions=["酒后驾驶怎么处罚？", "闯红灯扣几分？", "违法占用应急车道怎么处理？"],
            )
            return payload, context

        all_rows: list[dict[str, Any]] = []
        matched_name = ""
        for name in matches:
            rows = self._get_penalty_rows(name)
            if rows:
                all_rows = rows
                matched_name = name
                break

        if not all_rows:
            payload = AnswerPayload(
                INTENT_PENALTY,
                INTENT_LABELS[INTENT_PENALTY],
                "未查询到处罚结果",
                f"图谱里暂时没有查到“{base_name(matches[0])}”对应的处罚信息。",
            )
            return payload, context

        primary = all_rows[0]
        base_violation_name = base_name(clean_text(primary.get("violation")) or matches[0])
        summary_parts = [f"“{base_violation_name}”已在图谱中检索到处罚信息。"]
        if clean_text(primary.get("fine_range")):
            summary_parts.append(f"罚款区间一般为 {clean_text(primary.get('fine_range'))} 元。")
        if clean_text(primary.get("score_value")):
            summary_parts.append(f"常见记分为 {clean_text(primary.get('score_value'))} 分。")
        if clean_text(primary.get("license_action")) and clean_text(primary.get("license_action")) not in {"无", "否"}:
            summary_parts.append(f"同时可能涉及驾驶证处理：{clean_text(primary.get('license_action'))}。")

        penalty_lines: list[str] = []
        law_lines: list[str] = []
        seen_penalty: set[str] = set()
        seen_law: set[str] = set()

        for row in all_rows:
            violation = base_name(clean_text(row.get("violation")))
            detail = f"{violation}：{clean_text(row.get('penalty_type')) or '未注明处罚类型'}；{clean_text(row.get('content')) or '未注明处罚内容'}"
            if clean_text(row.get("fine_range")):
                detail += f"；罚款 {clean_text(row.get('fine_range'))} 元"
            if clean_text(row.get("score_value")):
                detail += f"；记分 {clean_text(row.get('score_value'))} 分"
            if clean_text(row.get("license_action")) and clean_text(row.get("license_action")) not in {"无", "否"}:
                detail += f"；驾驶证处理 {clean_text(row.get('license_action'))}"
            if detail not in seen_penalty:
                seen_penalty.add(detail)
                penalty_lines.append(detail)

            article_refs = [clean_text(item) for item in row.get("article_refs", []) if clean_text(item)]
            law_names = [clean_text(item) for item in row.get("laws", []) if clean_text(item)]
            if article_refs:
                law_line = f"{violation}：相关法条 {', '.join(article_refs[:3])}"
                if law_names:
                    law_line += f"；来源 {law_names[0]}"
                if law_line not in seen_law:
                    seen_law.add(law_line)
                    law_lines.append(law_line)

        sections = [AnswerSection("处罚结果", penalty_lines[:5])]
        if law_lines:
            sections.append(AnswerSection("相关法条", law_lines[:5]))

        next_context = ConversationContext(
            last_intent=INTENT_PENALTY,
            last_violation=matched_name or matches[0],
            last_question=question,
            last_law=context.last_law,
            last_article_ref=context.last_article_ref,
            last_sign=context.last_sign,
            last_behavior=context.last_behavior,
            last_weather=context.last_weather,
            last_condition=context.last_condition,
        )
        payload = AnswerPayload(
            INTENT_PENALTY,
            INTENT_LABELS[INTENT_PENALTY],
            f"{base_violation_name}处罚说明",
            "".join(summary_parts),
            sections=sections,
            related_questions=[
                f"{base_violation_name}相关法条有哪些？",
                f"{base_violation_name}会导致什么事故风险？",
                "醉酒驾驶怎么处罚？",
            ],
        )
        return payload, next_context

    def _answer_law(self, question: str, context: ConversationContext) -> tuple[AnswerPayload, ConversationContext]:
        article_refs = normalize_article_refs(question)
        if not article_refs and context.last_article_ref and self._looks_like_followup(question):
            article_refs = [context.last_article_ref]

        violation_matches = self._match_violations(question, limit=2)
        if not violation_matches and context.last_violation and self._looks_like_followup(question):
            violation_matches = [context.last_violation]

        law_matches = self._match_laws(question, limit=2)

        rows: list[dict[str, Any]] = []
        if article_refs:
            rows = self._get_law_rows_by_article_refs(article_refs)
        elif violation_matches:
            rows = self._get_law_rows_by_violation(violation_matches[0])
        elif law_matches:
            rows = self._get_law_rows_by_law(law_matches[0])
        else:
            rows = self._get_law_rows_by_keywords(self._question_keywords(question))

        if not rows:
            payload = AnswerPayload(
                INTENT_LAW,
                INTENT_LABELS[INTENT_LAW],
                "未定位到法条内容",
                "我还没有定位到你要查询的具体法条。你可以问“道路交通安全法第二十二条是什么”。",
                related_questions=["道路交通安全法第二十二条是什么？", "酒后驾驶对应哪条法条？", "超速行驶相关法条有哪些？"],
            )
            return payload, context

        deduped_rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            key = (clean_text(row.get("law_name")), clean_text(row.get("article_no")))
            if key in seen:
                continue
            seen.add(key)
            deduped_rows.append(row)

        first = deduped_rows[0]
        summary = f"已检索到 {clean_text(first.get('law_name'))} 中的相关法条内容。"
        section_lines: list[str] = []
        for row in deduped_rows[:5]:
            title = f"{clean_text(row.get('law_name'))} {clean_text(row.get('article_no'))}"
            if clean_text(row.get("title")):
                title += f" {clean_text(row.get('title'))}"
            content = clean_text(row.get("content")) or "暂无正文"
            section_lines.append(f"{title}：{content}")

        next_context = ConversationContext(
            last_intent=INTENT_LAW,
            last_law=clean_text(first.get("law_name")),
            last_article_ref=clean_text(first.get("article_no")),
            last_violation=violation_matches[0] if violation_matches else context.last_violation,
            last_question=question,
            last_sign=context.last_sign,
            last_behavior=context.last_behavior,
            last_weather=context.last_weather,
            last_condition=context.last_condition,
        )
        payload = AnswerPayload(
            INTENT_LAW,
            INTENT_LABELS[INTENT_LAW],
            "法规条文查询结果",
            summary,
            sections=[AnswerSection("法条内容", section_lines)],
            related_questions=["这一条对应的处罚是什么？", "这条法规主要约束什么行为？", "还有相关案例吗？"],
        )
        return payload, next_context

    def _answer_sign(self, question: str, context: ConversationContext) -> tuple[AnswerPayload, ConversationContext]:
        matches = self._match_signs(question, limit=3)
        if not matches and context.last_sign and self._looks_like_followup(question):
            matches = [context.last_sign]

        if not matches:
            payload = AnswerPayload(
                INTENT_SIGN,
                INTENT_LABELS[INTENT_SIGN],
                "未定位到具体道路标志",
                "我还没有识别到你想问的道路标志。你可以问“限速60是什么意思”或“停车让行适用于什么场景”。",
                related_questions=["限速60是什么意思？", "禁止超车适用于什么场景？", "停车让行代表什么？"],
            )
            return payload, context

        row = None
        sign_name = matches[0]
        for name in matches:
            row = self._get_sign_row(name)
            if row:
                sign_name = name
                break

        if not row:
            payload = AnswerPayload(
                INTENT_SIGN,
                INTENT_LABELS[INTENT_SIGN],
                "未找到标志详情",
                f"图谱里暂时没有查到“{base_name(matches[0])}”的详细信息。",
            )
            return payload, context

        sections = [
            AnswerSection(
                "标志说明",
                [
                    f"名称：{clean_text(row.get('sign_name'))}",
                    f"类别：{clean_text(row.get('category')) or '未注明'}",
                    f"细分类：{clean_text(row.get('sub_category')) or '未注明'}",
                    f"含义：{clean_text(row.get('meaning')) or '未注明'}",
                ],
            ),
            AnswerSection(
                "使用场景",
                [
                    f"适用场景：{clean_text(row.get('applicable_scene')) or '未注明'}",
                    f"图形形状：{clean_text(row.get('shape')) or '未注明'}",
                    f"颜色特征：{clean_text(row.get('color')) or '未注明'}",
                    f"标准编号：{clean_text(row.get('standard_no')) or '未注明'}",
                ],
            ),
        ]

        next_context = ConversationContext(
            last_intent=INTENT_SIGN,
            last_sign=sign_name,
            last_question=question,
            last_violation=context.last_violation,
            last_law=context.last_law,
            last_article_ref=context.last_article_ref,
            last_behavior=context.last_behavior,
            last_weather=context.last_weather,
            last_condition=context.last_condition,
        )
        payload = AnswerPayload(
            INTENT_SIGN,
            INTENT_LABELS[INTENT_SIGN],
            f"{base_name(sign_name)}标志解读",
            f"“{base_name(clean_text(row.get('sign_name')))}”是一类 {clean_text(row.get('category')) or '道路标志'}。",
            sections=sections,
            related_questions=["这个标志违反了会怎么处罚？", "类似的禁令标志还有哪些？", "这个标志一般出现在哪些场景？"],
        )
        return payload, next_context

    def _answer_reasoning(self, question: str, context: ConversationContext) -> tuple[AnswerPayload, ConversationContext]:
        factors = self._collect_reasoning_factors(question)
        weather = factors.get("weather", [])
        conditions = factors.get("condition", [])
        signs = factors.get("sign", [])
        scenes = factors.get("scene", [])
        behaviors = factors.get("behavior", [])

        factor_names = dedupe_keep_order(weather + conditions + signs + scenes + behaviors)
        display_factors: list[str] = []
        display_factors.extend(weather)
        if "高速公路" in scenes:
            display_factors.append("高速公路")
        if "施工路段" in scenes or "施工导改" in conditions or "施工" in signs:
            display_factors.append("施工路段")
        if "限速控制" in scenes or any("限速" in sign for sign in signs):
            display_factors.append("限速控制")
        display_factors.extend([item for item in conditions if item not in {"施工导改"}])
        display_factors.extend([item for item in signs if item != "施工"])
        display_factors.extend(behaviors)
        display_factors = dedupe_keep_order(display_factors)
        action_lines = [
            "先减速、控距、观察标志标线，再按现场临时限速和导向车道通行。",
        ]
        reasoning_lines: list[str] = []

        if "雨天" in weather:
            action_lines.append("雨天路面附着力下降，应加大跟车距离，避免急刹、急加速和急打方向。")
            reasoning_lines.append("雨天会延长制动距离，并提高侧滑、追尾等事故风险。")

        if "高速公路" in scenes:
            action_lines.append("高速公路上不要突然停车、倒车或连续急变道，需要变道时提前打转向灯并确认安全间隙。")
            reasoning_lines.append("高速车速较高，任何突然制动或临近变道都会放大追尾和剐蹭风险。")

        if "施工路段" in scenes or "施工导改" in conditions or "施工" in signs:
            action_lines.append("进入施工区前按警告标志逐级减速，服从锥桶、导向箭头、临时信号和现场人员指挥。")
            reasoning_lines.append("施工区车道宽度、通行方向和路面状态可能临时变化，应以现场交通组织为准。")

        if "限速控制" in scenes or any("限速" in sign for sign in signs):
            action_lines.append("遇到施工限速时以临时限速为准；若同时处于雨天或湿滑路面，应选择更保守的安全速度。")
            reasoning_lines.append("限速标志给出的是通行上限，多风险叠加时还需要主动降低速度。")

        if not reasoning_lines:
            reasoning_lines.append("该问题包含多个交通要素，系统按“先控制风险，再遵守现场标志，最后结合案例经验”的顺序进行推理。")

        sign_lines: list[str] = []
        seen_signs: set[str] = set()
        for sign in signs[:3]:
            row = self._get_sign_row(sign)
            if not row:
                continue
            line = f"{clean_text(row.get('sign_name'))}：{clean_text(row.get('meaning')) or clean_text(row.get('category')) or '图谱中已有该标志信息'}"
            self._append_unique(sign_lines, line, seen_signs, key=clean_text(row.get("sign_name")))

        article_keywords = dedupe_keep_order(["安全驾驶", "限速", "交通信号", "施工", "减速", "雨天"] + factor_names)
        article_rows = self._get_law_rows_by_keywords(article_keywords)
        important_article_refs = {"第二十二条": 5, "第三十八条": 4, "第四十二条": 4, "第六十二条": 3}
        article_rows.sort(
            key=lambda row: (
                important_article_refs.get(clean_text(row.get("article_no")), 0),
                clean_text(row.get("title")) in {"安全驾驶义务", "机动车限速规定", "按照交通信号通行"},
            ),
            reverse=True,
        )
        article_lines: list[str] = []
        seen_articles: set[str] = set()
        for row in article_rows[:3]:
            title = f"{clean_text(row.get('law_name'))} {clean_text(row.get('article_no'))}"
            if clean_text(row.get("title")):
                title += f" {clean_text(row.get('title'))}"
            content = clean_text(row.get("content")) or "暂无正文"
            self._append_unique(article_lines, f"{title}：{content}", seen_articles, key=title)

        case_rows = self._get_reasoning_case_rows(factors)
        case_lines: list[str] = []
        seen_cases: set[str] = set()
        for row in case_rows[:3]:
            case_name = normalize_case_name(clean_text(row.get("case_name"))) or "未命名案例"
            cause = clean_text(row.get("cause"))
            line = (
                f"{case_name}：地点 {clean_text(row.get('place')) or '未注明'}；"
                f"伤亡 {clean_text(row.get('casualties')) or '未注明'}"
            )
            if cause:
                line += f"；原因 {cause}"
            self._append_unique(case_lines, line, seen_cases, key=f"{case_name}|{cause}|{clean_text(row.get('casualties'))}")

        sections = [
            AnswerSection("操作建议", action_lines),
            AnswerSection("推理过程", reasoning_lines),
        ]
        if sign_lines:
            sections.append(AnswerSection("标志依据", sign_lines))
        if article_lines:
            sections.append(AnswerSection("法规依据", article_lines))
        if case_lines:
            sections.append(AnswerSection("案例参考", case_lines))

        next_context = ConversationContext(
            last_intent=INTENT_REASONING,
            last_sign=signs[0] if signs else context.last_sign,
            last_weather=weather[0] if weather else context.last_weather,
            last_condition=conditions[0] if conditions else context.last_condition,
            last_behavior=behaviors[0] if behaviors else context.last_behavior,
            last_violation=context.last_violation,
            last_law=context.last_law,
            last_article_ref=context.last_article_ref,
            last_question=question,
        )

        factor_summary = "、".join(display_factors[:5]) or "当前交通场景"
        payload = AnswerPayload(
            INTENT_REASONING,
            INTENT_LABELS[INTENT_REASONING],
            f"{factor_summary}综合通行建议",
            "系统已按“场景因素识别 -> 规则推理 -> 图谱证据补充”的流程生成建议。",
            sections=sections,
            related_questions=[
                "雨天高速有什么风险？",
                "施工标志是什么意思？",
                "限速60是什么意思？",
            ],
        )
        return payload, next_context

    def _answer_accident(self, question: str, context: ConversationContext) -> tuple[AnswerPayload, ConversationContext]:
        behavior_matches = self._match_behaviors(question, limit=2)
        weather_matches = self._match_weathers(question, limit=2)
        condition_matches = self._match_conditions(question, limit=2)
        violation_matches = self._match_violations(question, limit=2)

        if not behavior_matches and context.last_behavior and self._looks_like_followup(question):
            behavior_matches = [context.last_behavior]
        if not weather_matches and context.last_weather and self._looks_like_followup(question):
            weather_matches = [context.last_weather]
        if not condition_matches and context.last_condition and self._looks_like_followup(question):
            condition_matches = [context.last_condition]
        if not violation_matches and context.last_violation and self._looks_like_followup(question):
            violation_matches = [context.last_violation]

        query_rows: list[dict[str, Any]] = []
        query_label = ""
        if weather_matches:
            query_rows = self._query_cases_by_rel("IN_WEATHER", "Weather", "name", weather_matches[0])
            query_label = weather_matches[0]
        elif behavior_matches:
            query_rows = self._query_cases_by_rel("HAS_BEHAVIOR", "Behavior", "name", behavior_matches[0])
            query_label = behavior_matches[0]
        elif condition_matches:
            query_rows = self._query_cases_by_rel("ON_CONDITION", "RoadCondition", "name", condition_matches[0])
            query_label = condition_matches[0]
        elif violation_matches:
            query_rows = self._query_cases_by_rel("VIOLATES", "Violation", "name", violation_matches[0])
            query_label = violation_matches[0]
        else:
            query_rows = self._get_case_rows_by_keywords(self._question_keywords(question), limit=8)
            query_label = "关键词"

        query_rows = self._dedupe_case_rows(query_rows)

        if not query_rows:
            payload = AnswerPayload(
                INTENT_ACCIDENT,
                INTENT_LABELS[INTENT_ACCIDENT],
                "未定位到风险因素",
                "我还没有识别到具体风险因素。你可以问“雨天高速有什么风险”或“疲劳驾驶会导致什么事故”。",
                related_questions=["雨天高速有什么风险？", "疲劳驾驶会导致什么事故？", "超速行驶常见事故后果是什么？"],
            )
            return payload, context

        case_lines: list[str] = []
        risk_lines: list[str] = []
        suggestion_lines: list[str] = []
        seen_cases: set[str] = set()
        seen_risks: set[str] = set()
        seen_suggestions: set[str] = set()

        for row in query_rows[:4]:
            case_name = normalize_case_name(clean_text(row.get("case_name"))) or "未命名案例"
            cause = clean_text(row.get("cause"))
            casualties = clean_text(row.get("casualties"))
            place = clean_text(row.get("place"))
            case_line = (
                f"{case_name}：时间 {clean_text(row.get('date')) or '未注明'}；"
                f"地点 {place or '未注明'}；伤亡 {casualties or '未注明'}"
            )
            self._append_unique(
                case_lines,
                case_line,
                seen_cases,
                key=f"{case_name}|{cause}|{casualties}",
            )
            if cause:
                self._append_unique(risk_lines, f"{case_name}：{cause}", seen_risks, key=cause)
            for item in row.get("suggestions", []):
                suggestion = clean_text(item)
                self._append_unique(suggestion_lines, suggestion, seen_suggestions)

        sections = [AnswerSection("代表案例", case_lines)]
        if risk_lines:
            sections.append(AnswerSection("风险原因", risk_lines[:4]))
        if suggestion_lines:
            sections.append(AnswerSection("安全建议", suggestion_lines[:4]))

        next_context = ConversationContext(
            last_intent=INTENT_ACCIDENT,
            last_behavior=behavior_matches[0] if behavior_matches else context.last_behavior,
            last_weather=weather_matches[0] if weather_matches else context.last_weather,
            last_condition=condition_matches[0] if condition_matches else context.last_condition,
            last_violation=violation_matches[0] if violation_matches else context.last_violation,
            last_question=question,
            last_sign=context.last_sign,
            last_law=context.last_law,
            last_article_ref=context.last_article_ref,
        )
        payload = AnswerPayload(
            INTENT_ACCIDENT,
            INTENT_LABELS[INTENT_ACCIDENT],
            f"{base_name(query_label)}相关风险分析",
            f"已从知识图谱中检索到与“{base_name(query_label)}”相关的事故案例与风险信息。",
            sections=sections,
            related_questions=["这种情况一般如何预防？", "这种风险对应哪些违法行为？", "还有类似案例吗？"],
        )
        return payload, next_context

    def _answer_unknown(self, question: str, context: ConversationContext) -> tuple[AnswerPayload, ConversationContext]:
        payload = AnswerPayload(
            INTENT_UNKNOWN,
            INTENT_LABELS[INTENT_UNKNOWN],
            "我还没有完全理解这个问题",
            "你可以换一种更具体的问法，例如直接说明违法行为、法条编号、道路标志名称，或者事故风险场景。",
            sections=[
                AnswerSection(
                    "你可以这样问",
                    [
                        "酒后驾驶怎么处罚？",
                        "闯红灯扣几分？",
                        "超速行驶有哪些处罚？",
                        "违法占用应急车道怎么处理？",
                        "不系安全带会怎么处罚？",
                        "道路交通安全法第二十二条是什么？",
                        "限速60是什么意思？",
                        "雨天高速有什么风险？",
                        "有哪些道路标志？",
                        "有哪些事故案例？",
                        "当前图谱数据量是多少？",
                    ],
                )
            ],
            related_questions=[
                "酒后驾驶怎么处罚？",
                "有哪些道路标志？",
                "有哪些事故案例？",
                "当前图谱数据量是多少？",
            ],
        )
        return payload, context
