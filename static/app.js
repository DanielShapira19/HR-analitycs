const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const formEl = document.getElementById("composer");
const sendEl = document.getElementById("send");
const fileListEl = document.getElementById("file-list");
const fileInputEl = document.getElementById("file-input");
const uploadMsgEl = document.getElementById("upload-msg");
const readyBadgeEl = document.getElementById("ready-badge");
const modelLabelEl = document.getElementById("model-label");

const history = [];

function addBubble(role, text, extra = "") {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.textContent = text;
  if (extra) {
    const code = document.createElement("pre");
    code.className = "code";
    code.textContent = extra;
    div.appendChild(code);
  }
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

function renderStatus(status) {
  fileListEl.innerHTML = "";
  status.files.forEach((file) => {
    const li = document.createElement("li");
    li.innerHTML = `<span><span class="dot ${file.loaded ? "on" : ""}"></span>${file.filename}</span><span>${file.loaded ? file.rows + " rows" : "missing"}</span>`;
    fileListEl.appendChild(li);
  });
  readyBadgeEl.textContent = status.ready ? "Data ready" : `${status.loaded_count}/${status.expected_count} files`;
  readyBadgeEl.classList.toggle("ready", status.ready);
  modelLabelEl.textContent = `Model: ${status.model}`;
}

async function loadStatus() {
  const res = await fetch("/api/status");
  renderStatus(await res.json());
}

async function sendMessage(text) {
  const message = text.trim();
  if (!message) return;
  addBubble("user", message);
  inputEl.value = "";
  sendEl.disabled = true;
  const thinking = addBubble("assistant", "Analyzing the HR data...");
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
    });
    const data = await res.json();
    thinking.remove();
    if (!res.ok) {
      addBubble("error", data.detail || "The request failed.");
      return;
    }
    history.push({ role: "user", content: message });
    history.push({ role: "assistant", content: data.answer });
    const extra = data.code_runs && data.code_runs.length
      ? data.code_runs.map((c, i) => `Query ${i + 1}:\n${c}`).join("\n\n")
      : "";
    addBubble("assistant", data.answer, extra);
    if (data.model) modelLabelEl.textContent = `Model: ${data.model}`;
  } catch (err) {
    thinking.remove();
    addBubble("error", "Could not reach the chatbot server.");
  } finally {
    sendEl.disabled = false;
    inputEl.focus();
  }
}

formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  sendMessage(inputEl.value);
});

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage(inputEl.value);
  }
});

document.querySelectorAll(".chip").forEach((btn) => {
  btn.addEventListener("click", () => sendMessage(btn.dataset.q));
});

fileInputEl.addEventListener("change", async () => {
  const files = fileInputEl.files;
  if (!files.length) return;
  const body = new FormData();
  for (const file of files) body.append("files", file);
  uploadMsgEl.textContent = "Uploading...";
  const res = await fetch("/api/upload", { method: "POST", body });
  const data = await res.json();
  renderStatus(data.status);
  const rejected = data.rejected && data.rejected.length ? ` Ignored: ${data.rejected.join(", ")}` : "";
  uploadMsgEl.textContent = `Saved ${data.saved.length} file(s).${rejected}`;
  fileInputEl.value = "";
});

loadStatus();
