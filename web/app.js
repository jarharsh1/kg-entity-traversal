// Minimal chat UI for the Knowledge-Graph Traversal QA API.
// Talks to the same origin that serves this page: GET /health, POST /ask.

const chat = document.getElementById("chat");
const form = document.getElementById("form");
const input = document.getElementById("q");
const sendBtn = document.getElementById("send");

function addMessage(text, who) {
  const div = document.createElement("div");
  div.className = `msg ${who}`;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function addDetails(container, data) {
  const d = document.createElement("details");
  d.className = "details";
  const s = document.createElement("summary");
  const n = (data.results || []).length;
  s.textContent = `traversal details — ${n} result node(s)`;
  d.appendChild(s);

  const intent = document.createElement("div");
  intent.className = "row";
  intent.innerHTML = `intent: <code>${data.intent || "none"}</code>`;
  d.appendChild(intent);

  const matched = document.createElement("div");
  matched.className = "row";
  matched.textContent = `matched entity: ${data.matched || "(none)"}`;
  d.appendChild(matched);

  const expl = document.createElement("div");
  expl.className = "row";
  expl.textContent = data.explanation || "";
  d.appendChild(expl);

  if (n) {
    const ul = document.createElement("ul");
    for (const r of data.results) {
      const li = document.createElement("li");
      li.textContent = `${r.name} (${r.type})`;
      ul.appendChild(li);
    }
    d.appendChild(ul);
  }
  container.appendChild(d);
}

async function ask(question) {
  addMessage(question, "user");
  input.value = "";
  sendBtn.disabled = true;
  const bot = addMessage("…", "bot");
  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    bot.textContent = data.answer || "(no answer)";
    addDetails(bot, data);
  } catch (err) {
    bot.textContent = `Error: ${err.message}`;
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (q) ask(q);
});

document.getElementById("examples").addEventListener("click", (e) => {
  if (e.target.tagName === "BUTTON") ask(e.target.textContent);
});

// Populate the health pills on load.
fetch("/health")
  .then((r) => r.json())
  .then((h) => {
    document.getElementById("backend").textContent = `backend: ${h.backend}`;
    document.getElementById("nodes").textContent = `graph: ${h.graph_nodes} nodes`;
  })
  .catch(() => {});
