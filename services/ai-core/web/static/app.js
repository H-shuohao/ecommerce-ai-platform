const SESSION_KEY = "presales_agent_session_id";
const messages = document.querySelector("#messages");
const form = document.querySelector("#chat-form");
const input = document.querySelector("#question");
const sendButton = document.querySelector("#send");
const sessionLabel = document.querySelector("#session-label");

let sessionId = localStorage.getItem(SESSION_KEY);

function updateSessionLabel() {
  sessionLabel.textContent = sessionId ? `会话 ${sessionId.slice(0, 8)}` : "新会话";
}

function addMessage(role, content, trace = "", runId = "") {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  if (role === "assistant") {
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = "AI";
    article.appendChild(avatar);
  }
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const paragraph = document.createElement("p");
  paragraph.textContent = content;
  bubble.appendChild(paragraph);
  article.appendChild(bubble);
  if (trace) attachTrace(article, trace, runId);
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
  return article;
}

function setMessageContent(article, content) {
  article.querySelector(".bubble > p").textContent = content;
  messages.scrollTop = messages.scrollHeight;
}

function attachTrace(article, trace, runId = "") {
  const bubble = article.querySelector(".bubble");
  if (trace) {
    const detail = document.createElement("div");
    detail.className = "trace";
    const summary = document.createElement("span");
    summary.textContent = trace;
    detail.appendChild(summary);
    if (runId) {
      const runLink = document.createElement("a");
      runLink.className = "run-link";
      runLink.href = `/api/v1/agents/runs/${encodeURIComponent(runId)}`;
      runLink.target = "_blank";
      runLink.rel = "noopener";
      runLink.textContent = `运行详情 ${runId.slice(0, 8)}`;
      runLink.title = "打开本次 Agent 的问题、工具参数、工具结果和耗时记录";
      detail.appendChild(runLink);
    }
    bubble.appendChild(detail);
  }
}

async function restoreHistory() {
  if (!sessionId) return;
  try {
    const response = await fetch(`/api/v1/agents/sessions/${encodeURIComponent(sessionId)}`);
    if (!response.ok) throw new Error("session unavailable");
    const session = await response.json();
    messages.innerHTML = "";
    session.messages.forEach((item) => addMessage(item.role, item.content));
  } catch {
    localStorage.removeItem(SESSION_KEY);
    sessionId = null;
  }
  updateSessionLabel();
}

async function submitLegacy(body, loading) {
  const response = await fetch("/api/v1/agents/presales/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "请求失败");
  sessionId = data.session_id;
  localStorage.setItem(SESSION_KEY, sessionId);
  const tools = data.tool_calls.map((call) => call.tool).join(" → ");
  const trace = `${tools ? `工具：${tools} · ` : ""}耗时：${data.duration_ms} ms`;
  loading.remove();
  addMessage("assistant", data.answer, trace, data.run_id);
  updateSessionLabel();
}

async function submitQuestion(question) {
  addMessage("user", question);
  const loading = addMessage("assistant", "正在分析商品与业务数据…");
  loading.classList.add("loading");
  sendButton.disabled = true;
  input.disabled = true;
  try {
    const body = { question };
    if (sessionId) body.session_id = sessionId;
    const response = await fetch("/api/v1/agents/presales/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (response.status === 404 || response.status === 405) {
      await submitLegacy(body, loading);
      return;
    }
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.detail || "请求失败");
    }
    if (!response.body) {
      await submitLegacy(body, loading);
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let answer = "";
    let doneData = null;
    const tools = [];

    function handleEvent(event) {
      if (event.event === "session") {
        sessionId = event.session_id;
        localStorage.setItem(SESSION_KEY, sessionId);
        updateSessionLabel();
      } else if (event.event === "status") {
        setMessageContent(loading, event.message);
      } else if (event.event === "tool") {
        tools.push(event.tool);
        setMessageContent(loading, `已调用 ${event.tool}，正在生成回答…`);
      } else if (event.event === "delta") {
        answer += event.content;
        loading.classList.remove("loading");
        setMessageContent(loading, answer);
      } else if (event.event === "done") {
        doneData = event;
        if (!answer) {
          answer = event.answer;
          setMessageContent(loading, answer);
        }
      } else if (event.event === "error") {
        throw new Error(event.message || "Agent 执行失败");
      }
    }

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (line.trim()) handleEvent(JSON.parse(line));
      }
      if (done) break;
    }
    if (buffer.trim()) handleEvent(JSON.parse(buffer));
    if (!doneData) throw new Error("流式响应未正常结束");

    loading.classList.remove("loading");
    const trace = `${tools.length ? `工具：${tools.join(" → ")} · ` : ""}耗时：${doneData.duration_ms} ms`;
    attachTrace(loading, trace, doneData.run_id);
    sessionId = doneData.session_id;
    localStorage.setItem(SESSION_KEY, sessionId);
    updateSessionLabel();
  } catch (error) {
    loading.remove();
    addMessage("assistant", `暂时无法完成请求：${error.message}`);
  } finally {
    sendButton.disabled = false;
    input.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question || sendButton.disabled) return;
  input.value = "";
  submitQuestion(question);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

document.querySelectorAll(".suggestions button").forEach((button) => {
  button.addEventListener("click", () => {
    input.value = button.textContent;
    input.focus();
  });
});

document.querySelector("#new-chat").addEventListener("click", () => {
  localStorage.removeItem(SESSION_KEY);
  sessionId = null;
  messages.innerHTML = "";
  addMessage("assistant", "新对话已开始。请告诉我你想找什么商品。");
  updateSessionLabel();
  input.focus();
});

updateSessionLabel();
restoreHistory();
