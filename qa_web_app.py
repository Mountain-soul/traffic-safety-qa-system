from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import socket
import sys
from datetime import datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from import_to_neo4j import create_driver
from traffic_qa_engine import (
    ConversationContext,
    INTENT_LABELS,
    TrafficQAEngine,
    result_to_rows,
)


SUGGESTED_QUESTIONS = [
    "酒后驾驶怎么处罚？",
    "闯红灯扣几分？",
    "超速行驶有哪些处罚？",
    "违法占用应急车道怎么处理？",
    "不系安全带会怎么处罚？",
    "限速60是什么意思？",
    "停车让行适用于什么场景？",
    "有哪些道路标志？",
    "禁令标志有哪些？",
    "道路交通安全法第二十二条是什么？",
    "有哪些相关法规？",
    "雨天高速有什么风险？",
    "疲劳驾驶会导致什么事故？",
    "有哪些事故案例？",
    "当前图谱数据量是多少？",
]


HTML_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>交通安全智能问答</title>
  <style>
    :root {
      --bg: #f7f8fa;
      --surface: #ffffff;
      --surface-soft: #f3f5f8;
      --line: #e4e7ec;
      --line-strong: #d7dce3;
      --text: #1f2937;
      --muted: #667085;
      --muted-soft: #98a2b3;
      --accent: #2563eb;
      --accent-soft: #eff4ff;
      --success: #039855;
      --shadow: 0 12px 32px rgba(16, 24, 40, 0.08);
    }

    * { box-sizing: border-box; }

    html, body {
      margin: 0;
      min-height: 100%;
      font-family: "HarmonyOS Sans SC", "Microsoft YaHei", "PingFang SC", sans-serif;
      color: var(--text);
      background: var(--bg);
    }

    body { padding: 16px; }

    .app {
      max-width: 1360px;
      margin: 0 auto;
      min-height: calc(100vh - 32px);
      display: grid;
      grid-template-columns: 286px minmax(0, 1fr);
      gap: 16px;
    }

    .sidebar,
    .shell {
      background: var(--surface);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
    }

    .sidebar {
      border-radius: 8px;
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }

    .brand-row {
      display: flex;
      gap: 12px;
      align-items: center;
    }

    .badge {
      width: 40px;
      height: 40px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      color: #ffffff;
      background: var(--accent);
      font-size: 13px;
      font-weight: 800;
    }

    .sidebar h1 {
      margin: 0;
      font-size: 20px;
      line-height: 1.25;
    }

    .sidebar p,
    .card p {
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.65;
    }

    .card {
      padding: 14px;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
    }

    .status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--success);
      font-size: 13px;
      font-weight: 700;
    }

    .status i {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      display: block;
      background: var(--success);
    }

    .metric-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .metric {
      padding: 10px;
      border-radius: 8px;
      background: var(--surface-soft);
      border: 1px solid var(--line);
    }

    .metric strong {
      display: block;
      font-size: 18px;
      line-height: 1.2;
    }

    .metric span {
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
    }

    .section-title {
      margin: 0 0 10px;
      font-size: 12px;
      color: var(--muted);
      font-weight: 800;
    }

    .quick-list {
      display: grid;
      gap: 8px;
    }

    .chip {
      width: 100%;
      text-align: left;
      border-radius: 8px;
      padding: 10px 11px;
      font: inherit;
      color: var(--text);
      background: var(--surface-soft);
      border: 1px solid transparent;
      cursor: pointer;
      transition: background 0.16s ease, border-color 0.16s ease;
    }

    .chip:hover {
      background: #ffffff;
      border-color: var(--line-strong);
    }

    .shell {
      border-radius: 8px;
      display: grid;
      grid-template-rows: auto 1fr auto;
      overflow: hidden;
    }

    .shell-top {
      padding: 18px 22px;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      border-bottom: 1px solid var(--line);
    }

    .shell-top h2 {
      margin: 0 0 5px;
      font-size: 20px;
      line-height: 1.3;
    }

    .shell-top p {
      margin: 0;
      color: var(--muted);
      font-size: 13px;
    }

    .pill {
      flex: 0 0 auto;
      padding: 6px 10px;
      border-radius: 8px;
      border: 1px solid var(--line);
      font-size: 12px;
      color: var(--muted);
      background: var(--surface-soft);
      font-weight: 700;
    }

    .messages {
      padding: 22px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }

    .message {
      display: flex;
      gap: 10px;
      align-items: flex-start;
      animation: rise 0.2s ease;
    }

    .message.user {
      flex-direction: row-reverse;
    }

    .avatar {
      width: 34px;
      height: 34px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      font-size: 12px;
      font-weight: 800;
      flex: 0 0 auto;
    }

    .avatar.bot {
      color: #ffffff;
      background: var(--accent);
    }

    .avatar.user {
      color: #344054;
      background: var(--surface-soft);
      border: 1px solid var(--line);
    }

    .bubble-wrap {
      max-width: min(78%, 920px);
    }

    .meta-line {
      margin-bottom: 6px;
      color: var(--muted-soft);
      font-size: 12px;
    }

    .bubble {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px 16px;
      line-height: 1.72;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 15px;
    }

    .message.user .bubble {
      background: var(--accent);
      color: #ffffff;
      border-color: var(--accent);
    }

    .bubble .intent-tag {
      display: inline-flex;
      padding: 3px 8px;
      margin-bottom: 10px;
      border-radius: 8px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
    }

    .answer-title {
      font-size: 17px;
      font-weight: 800;
      margin-bottom: 6px;
    }

    .answer-summary {
      color: #344054;
      margin-bottom: 10px;
    }

    .section-block {
      margin-top: 13px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
    }

    .section-block:first-of-type {
      border-top: 0;
      padding-top: 0;
      margin-top: 0;
    }

    .section-heading {
      margin: 0 0 8px;
      font-size: 13px;
      font-weight: 800;
      color: var(--muted);
    }

    .section-list {
      display: grid;
      gap: 7px;
    }

    .section-item {
      padding: 9px 10px;
      border-radius: 8px;
      background: var(--surface-soft);
      border: 1px solid var(--line);
    }

    .related {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }

    .related button {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 7px 10px;
      background: #ffffff;
      color: var(--accent);
      cursor: pointer;
      font: inherit;
      font-size: 13px;
      font-weight: 700;
    }

    .typing {
      display: none;
      align-items: center;
      gap: 8px;
      padding: 0 22px 12px;
      color: var(--muted);
      font-size: 13px;
    }

    .typing.active { display: flex; }

    .dots { display: inline-flex; gap: 4px; }
    .dots span {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--muted-soft);
      animation: bounce 1s infinite ease-in-out;
    }

    .dots span:nth-child(2) { animation-delay: 0.15s; }
    .dots span:nth-child(3) { animation-delay: 0.3s; }

    .composer {
      padding: 16px 22px 18px;
      border-top: 1px solid var(--line);
      background: #ffffff;
    }

    .composer-shell {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: end;
      padding: 10px;
      border-radius: 8px;
      background: var(--surface);
      border: 1px solid var(--line-strong);
    }

    textarea {
      width: 100%;
      min-height: 52px;
      max-height: 160px;
      resize: none;
      border: 0;
      outline: none;
      font: inherit;
      color: var(--text);
      background: transparent;
      line-height: 1.65;
      padding: 4px 2px;
    }

    .actions {
      display: flex;
      gap: 8px;
      align-items: center;
      min-width: 170px;
    }

    .send-btn, .ghost-btn {
      border-radius: 8px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      transition: background 0.16s ease, border-color 0.16s ease;
    }

    .send-btn {
      border: 1px solid var(--accent);
      padding: 11px 14px;
      color: #ffffff;
      background: var(--accent);
    }

    .send-btn:disabled {
      opacity: 0.58;
      cursor: not-allowed;
    }

    .ghost-btn {
      border: 1px solid var(--line);
      padding: 11px 12px;
      color: var(--muted);
      background: #ffffff;
    }

    .send-btn:hover:not(:disabled) {
      background: #1d4ed8;
      border-color: #1d4ed8;
    }

    .ghost-btn:hover {
      background: var(--surface-soft);
      border-color: var(--line-strong);
    }

    @keyframes bounce {
      0%, 80%, 100% { transform: translateY(0); opacity: 0.55; }
      40% { transform: translateY(-4px); opacity: 1; }
    }

    @keyframes rise {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }

    @media (max-width: 1040px) {
      .app { grid-template-columns: 1fr; }
      .sidebar { order: 2; }
    }

    @media (max-width: 720px) {
      body { padding: 10px; }
      .app { min-height: calc(100vh - 20px); gap: 10px; }
      .shell-top {
        padding: 15px;
        display: grid;
      }
      .messages { padding: 16px; }
      .composer { padding: 12px; }
      .composer-shell { grid-template-columns: 1fr; }
      .actions { min-width: 100%; }
      .send-btn, .ghost-btn { flex: 1; }
      .bubble-wrap { max-width: 100%; }
      .avatar { display: none; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand-row">
        <div class="badge">KG</div>
        <div>
          <h1>交通安全问答</h1>
          <p>知识图谱驱动的本地问答原型</p>
        </div>
      </div>

      <div class="card">
        <div class="status"><i></i><span>本地 Neo4j 已连接</span></div>
      </div>

      <div class="card">
        <h3 class="section-title">推荐提问</h3>
        <div class="quick-list" id="quick-list"></div>
      </div>

      <div class="card">
        <h3 class="section-title">图谱数据</h3>
        <div class="metric-grid">
          <div class="metric">
            <strong id="node-count">--</strong>
            <span>节点</span>
          </div>
          <div class="metric">
            <strong id="relation-count">--</strong>
            <span>关系</span>
          </div>
        </div>
      </div>
    </aside>

    <main class="shell">
      <div class="shell-top">
        <div>
          <h2>交通问答助手</h2>
          <p>输入交通安全问题，系统会检索图谱并返回结构化答案。</p>
        </div>
        <div class="pill">本地原型</div>
      </div>

      <div class="messages" id="messages"></div>
      <div class="typing" id="typing">
        <span>正在检索知识图谱</span>
        <span class="dots"><span></span><span></span><span></span></span>
      </div>

      <div class="composer">
        <div class="composer-shell">
          <textarea id="question-input" placeholder="输入问题，例如：酒后驾驶怎么处罚？"></textarea>
          <div class="actions">
            <button class="send-btn" id="send-btn">发送问题</button>
            <button class="ghost-btn" id="clear-btn">清空上下文</button>
          </div>
        </div>
      </div>
    </main>
  </div>

  <script>
    const suggestedQuestions = __SUGGESTED_QUESTIONS__;
    const messagesEl = document.getElementById("messages");
    const inputEl = document.getElementById("question-input");
    const sendBtn = document.getElementById("send-btn");
    const clearBtn = document.getElementById("clear-btn");
    const quickListEl = document.getElementById("quick-list");
    const typingEl = document.getElementById("typing");
    const nodeCountEl = document.getElementById("node-count");
    const relationCountEl = document.getElementById("relation-count");

    function nowTime() {
      return new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
    }

    function renderBotMessage(data) {
      const row = document.createElement("div");
      row.className = "message bot";

      const avatar = document.createElement("div");
      avatar.className = "avatar bot";
      avatar.textContent = "交安";

      const wrap = document.createElement("div");
      wrap.className = "bubble-wrap";

      const meta = document.createElement("div");
      meta.className = "meta-line";
      meta.textContent = "交通问答助手 · " + nowTime();

      const bubble = document.createElement("div");
      bubble.className = "bubble";

      const tag = document.createElement("div");
      tag.className = "intent-tag";
      tag.textContent = data.intent_label || "图谱回答";
      bubble.appendChild(tag);

      const title = document.createElement("div");
      title.className = "answer-title";
      title.textContent = data.title || "回答结果";
      bubble.appendChild(title);

      const summary = document.createElement("div");
      summary.className = "answer-summary";
      summary.textContent = data.summary || "";
      bubble.appendChild(summary);

      (data.sections || []).forEach((section) => {
        const block = document.createElement("div");
        block.className = "section-block";

        const heading = document.createElement("div");
        heading.className = "section-heading";
        heading.textContent = section.title;
        block.appendChild(heading);

        const list = document.createElement("div");
        list.className = "section-list";
        (section.lines || []).forEach((line) => {
          const item = document.createElement("div");
          item.className = "section-item";
          item.textContent = line;
          list.appendChild(item);
        });
        block.appendChild(list);
        bubble.appendChild(block);
      });

      if ((data.related_questions || []).length) {
        const block = document.createElement("div");
        block.className = "section-block";

        const heading = document.createElement("div");
        heading.className = "section-heading";
        heading.textContent = "你还可以继续问";
        block.appendChild(heading);

        const related = document.createElement("div");
        related.className = "related";
        data.related_questions.forEach((question) => {
          const btn = document.createElement("button");
          btn.textContent = question;
          btn.addEventListener("click", () => askQuestion(question));
          related.appendChild(btn);
        });
        block.appendChild(related);
        bubble.appendChild(block);
      }

      wrap.appendChild(meta);
      wrap.appendChild(bubble);
      row.appendChild(avatar);
      row.appendChild(wrap);
      messagesEl.appendChild(row);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function addUserMessage(text) {
      const row = document.createElement("div");
      row.className = "message user";

      const avatar = document.createElement("div");
      avatar.className = "avatar user";
      avatar.textContent = "我";

      const wrap = document.createElement("div");
      wrap.className = "bubble-wrap";

      const meta = document.createElement("div");
      meta.className = "meta-line";
      meta.textContent = "当前提问 · " + nowTime();

      const bubble = document.createElement("div");
      bubble.className = "bubble";
      bubble.textContent = text;

      wrap.appendChild(meta);
      wrap.appendChild(bubble);
      row.appendChild(avatar);
      row.appendChild(wrap);
      messagesEl.appendChild(row);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function setTyping(active) {
      typingEl.classList.toggle("active", active);
      if (active) {
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
    }

    async function askQuestion(question) {
      const trimmed = question.trim();
      if (!trimmed) return;

      addUserMessage(trimmed);
      inputEl.value = "";
      inputEl.style.height = "56px";
      setTyping(true);
      sendBtn.disabled = true;

      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: trimmed })
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || "请求失败");
        }
        renderBotMessage(data);
      } catch (error) {
        renderBotMessage({
          intent_label: "系统提示",
          title: "请求失败",
          summary: "当前请求没有成功返回结果。",
          sections: [{ title: "错误信息", lines: [String(error.message || error)] }],
          related_questions: []
        });
      } finally {
        setTyping(false);
        sendBtn.disabled = false;
        inputEl.focus();
      }
    }

    function renderQuickQuestions() {
      suggestedQuestions.forEach((question) => {
        const button = document.createElement("button");
        button.className = "chip";
        button.textContent = question;
        button.addEventListener("click", () => askQuestion(question));
        quickListEl.appendChild(button);
      });
    }

    async function loadStats() {
      try {
        const response = await fetch("/api/stats");
        const data = await response.json();
        if (!response.ok) return;
        nodeCountEl.textContent = String(data.nodes ?? "--");
        relationCountEl.textContent = String(data.relationships ?? "--");
      } catch (error) {
      }
    }

    sendBtn.addEventListener("click", () => askQuestion(inputEl.value));

    clearBtn.addEventListener("click", async () => {
      try {
        await fetch("/api/reset", { method: "POST" });
      } catch (error) {
      }
      messagesEl.innerHTML = "";
      renderBotMessage({
        intent_label: "欢迎使用",
        title: "交通问答助手已准备就绪",
        summary: "你好，我是交通安全知识图谱问答助手。现在你可以连续提问，我会记住上一轮上下文。",
        sections: [
          {
            title: "推荐方向",
            lines: [
              "违法处罚问答",
              "法规条文查询",
              "道路标志解读",
              "事故风险分析"
            ]
          }
        ],
        related_questions: suggestedQuestions.slice(0, 3)
      });
    });

    inputEl.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        askQuestion(inputEl.value);
      }
    });

    inputEl.addEventListener("input", () => {
      inputEl.style.height = "56px";
      inputEl.style.height = Math.min(inputEl.scrollHeight, 180) + "px";
    });

    renderQuickQuestions();
    loadStats();
    clearBtn.click();
  </script>
</body>
</html>
"""


class QARequestHandler(BaseHTTPRequestHandler):
    driver = None
    database = "neo4j"
    entity_cache: dict[str, list[str]] | None = None
    sessions: dict[str, dict[str, Any]] = {}

    def do_GET(self) -> None:
        try:
            if self.path in {"/", "/index.html"}:
                page = HTML_PAGE.replace(
                    "__SUGGESTED_QUESTIONS__",
                    json.dumps(SUGGESTED_QUESTIONS, ensure_ascii=False),
                ).encode("utf-8")
                self._send_bytes(HTTPStatus.OK, page, "text/html; charset=utf-8")
                return

            if self.path == "/api/health":
                self._send_json({"status": "ok", "time": datetime.now().isoformat()})
                return

            if self.path == "/api/stats":
                try:
                    with self.driver.session(database=self.database) as session:
                        node_rows = result_to_rows(session.run("MATCH (n) RETURN count(n) AS count"))
                        rel_rows = result_to_rows(session.run("MATCH ()-[r]->() RETURN count(r) AS count"))
                    self._send_json(
                        {
                            "nodes": node_rows[0].get("count", 0) if node_rows else 0,
                            "relationships": rel_rows[0].get("count", 0) if rel_rows else 0,
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, socket.timeout):
            return

    def do_POST(self) -> None:
        try:
            if self.path == "/api/reset":
                session_id = self._ensure_session_id()
                self.sessions[session_id] = {"context": ConversationContext().to_dict(), "history": []}
                self._send_json({"status": "reset"})
                return

            if self.path != "/api/chat":
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return

            session_id = self._ensure_session_id()
            state = self.sessions.setdefault(
                session_id,
                {"context": ConversationContext().to_dict(), "history": []},
            )
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length)
            payload = json.loads(raw.decode("utf-8") or "{}")
            question = str(payload.get("question", "")).strip()
            if not question:
                self._send_json({"error": "问题不能为空"}, HTTPStatus.BAD_REQUEST)
                return

            context = ConversationContext.from_dict(state.get("context"))
            with self.driver.session(database=self.database) as session:
                engine = TrafficQAEngine(session, entities=self.entity_cache)
                answer_payload, next_context = engine.answer(question, context)

            state["context"] = next_context.to_dict()
            state["history"] = (state.get("history") or [])[-8:] + [
                {"question": question, "intent": answer_payload.intent}
            ]

            response = answer_payload.to_dict()
            response["context"] = next_context.to_dict()
            self._send_json(response)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, socket.timeout):
            return
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, fmt: str, *args) -> None:
        return None

    def _ensure_session_id(self) -> str:
        cookies = SimpleCookie(self.headers.get("Cookie"))
        session_cookie = cookies.get("traffic_qa_session")
        if session_cookie and session_cookie.value:
            self._pending_session_cookie = None
            return session_cookie.value

        session_id = secrets.token_hex(16)
        self._pending_session_cookie = f"traffic_qa_session={session_id}; Path=/; HttpOnly; SameSite=Lax"
        return session_id

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, data, "application/json; charset=utf-8")

    def _send_bytes(self, status: HTTPStatus, data: bytes, content_type: str) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            pending_cookie = getattr(self, "_pending_session_cookie", None)
            if pending_cookie:
                self.send_header("Set-Cookie", pending_cookie)
                self._pending_session_cookie = None
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, socket.timeout):
            self._pending_session_cookie = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Traffic safety QA local web app.")
    parser.add_argument("--host", default=os.getenv("TRAFFIC_QA_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("TRAFFIC_QA_PORT", "8000")))
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.getenv("NEO4J_PASSWORD"))
    parser.add_argument("--database", default=os.getenv("NEO4J_DATABASE", "neo4j"))
    parser.add_argument("--http-uri", default=os.getenv("NEO4J_HTTP_URI", "http://localhost:7474"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    password = args.password or getpass.getpass("Neo4j password (input hidden): ")
    driver = create_driver(args, password)

    try:
        driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to connect to Neo4j: {exc}", file=sys.stderr)
        driver.close()
        return 1

    QARequestHandler.driver = driver
    QARequestHandler.database = args.database
    with driver.session(database=args.database) as session:
        QARequestHandler.entity_cache = TrafficQAEngine(session).entities

    server = ThreadingHTTPServer((args.host, args.port), QARequestHandler)
    print(f"Traffic QA web app running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        return 0
    finally:
        server.server_close()
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
