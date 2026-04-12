/**
 * VetFlow AI Chat Widget — Embeddable vanilla JS widget
 * Usage: <script src="https://your-domain/widget/CLINIC_ID/chat-widget.js" data-clinic-id="CLINIC_ID"></script>
 */
(function () {
  const script = document.currentScript;
  const clinicId = script.getAttribute("data-clinic-id") || script.src.split("/widget/")[1]?.split("/")[0];
  const baseUrl = script.src.split("/widget/")[0];
  const wsProtocol = baseUrl.startsWith("https") ? "wss" : "ws";
  const wsHost = baseUrl.replace(/^https?:\/\//, "");
  const wsUrl = `${wsProtocol}://${wsHost}/ws/chat/${clinicId}`;
  const httpUrl = `${baseUrl}/api/chat/${clinicId}/message`;

  let ws = null;
  let conversationId = null;
  let primaryColor = "#2563eb";

  // Fetch config
  fetch(`${baseUrl}/widget/${clinicId}/config`)
    .then((r) => r.json())
    .then((cfg) => {
      if (cfg.primary_color) primaryColor = cfg.primary_color;
      injectStyles();
      createWidget();
    })
    .catch(() => {
      injectStyles();
      createWidget();
    });

  function injectStyles() {
    const style = document.createElement("style");
    style.textContent = `
      #vf-widget-container { position:fixed; bottom:20px; right:20px; z-index:99999; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }
      #vf-toggle { width:60px; height:60px; border-radius:50%; background:${primaryColor}; border:none; cursor:pointer; box-shadow:0 4px 12px rgba(0,0,0,0.15); display:flex; align-items:center; justify-content:center; transition:transform 0.2s; }
      #vf-toggle:hover { transform:scale(1.1); }
      #vf-toggle svg { width:28px; height:28px; fill:white; }
      #vf-chat { display:none; width:370px; height:520px; background:white; border-radius:16px; box-shadow:0 8px 30px rgba(0,0,0,0.12); flex-direction:column; overflow:hidden; margin-bottom:12px; }
      #vf-chat.open { display:flex; }
      #vf-header { background:${primaryColor}; color:white; padding:16px; font-weight:600; font-size:15px; display:flex; justify-content:space-between; align-items:center; }
      #vf-close { background:none; border:none; color:white; cursor:pointer; font-size:20px; padding:0 4px; }
      #vf-messages { flex:1; overflow-y:auto; padding:16px; display:flex; flex-direction:column; gap:10px; }
      .vf-msg { max-width:80%; padding:10px 14px; border-radius:14px; font-size:14px; line-height:1.4; word-wrap:break-word; }
      .vf-msg.assistant { background:#f0f0f0; color:#333; align-self:flex-start; border-bottom-left-radius:4px; }
      .vf-msg.user { background:${primaryColor}; color:white; align-self:flex-end; border-bottom-right-radius:4px; }
      .vf-typing { align-self:flex-start; padding:10px 14px; background:#f0f0f0; border-radius:14px; }
      .vf-typing span { display:inline-block; width:8px; height:8px; background:#999; border-radius:50%; margin:0 2px; animation:vf-bounce 1.4s infinite; }
      .vf-typing span:nth-child(2) { animation-delay:0.2s; }
      .vf-typing span:nth-child(3) { animation-delay:0.4s; }
      @keyframes vf-bounce { 0%,60%,100%{transform:translateY(0)} 30%{transform:translateY(-6px)} }
      #vf-input-area { display:flex; padding:12px; border-top:1px solid #eee; gap:8px; }
      #vf-input { flex:1; border:1px solid #ddd; border-radius:20px; padding:10px 16px; font-size:14px; outline:none; }
      #vf-input:focus { border-color:${primaryColor}; }
      #vf-send { width:38px; height:38px; border-radius:50%; background:${primaryColor}; border:none; cursor:pointer; display:flex; align-items:center; justify-content:center; }
      #vf-send svg { width:18px; height:18px; fill:white; }
    `;
    document.head.appendChild(style);
  }

  function createWidget() {
    const container = document.createElement("div");
    container.id = "vf-widget-container";
    container.innerHTML = `
      <div id="vf-chat">
        <div id="vf-header">
          <span>VetFlow AI Assistant</span>
          <button id="vf-close">&times;</button>
        </div>
        <div id="vf-messages"></div>
        <div id="vf-input-area">
          <input id="vf-input" type="text" placeholder="Type a message..." autocomplete="off">
          <button id="vf-send"><svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg></button>
        </div>
      </div>
      <button id="vf-toggle"><svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg></button>
    `;
    document.body.appendChild(container);

    document.getElementById("vf-toggle").onclick = toggleChat;
    document.getElementById("vf-close").onclick = toggleChat;
    document.getElementById("vf-send").onclick = sendMessage;
    document.getElementById("vf-input").onkeydown = (e) => {
      if (e.key === "Enter") sendMessage();
    };
  }

  function toggleChat() {
    const chat = document.getElementById("vf-chat");
    const isOpen = chat.classList.toggle("open");
    if (isOpen && !ws) connectWebSocket();
  }

  function connectWebSocket() {
    try {
      ws = new WebSocket(wsUrl);
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        removeTyping();
        if (data.type === "message") addMessage(data.content, data.role);
        else if (data.type === "typing" && data.typing) showTyping();
        else if (data.type === "escalation") addMessage(data.message, "assistant");
      };
      ws.onclose = () => { ws = null; };
      ws.onerror = () => { ws = null; };
    } catch (e) {
      ws = null;
    }
  }

  function sendMessage() {
    const input = document.getElementById("vf-input");
    const text = input.value.trim();
    if (!text) return;

    addMessage(text, "user");
    input.value = "";

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ content: text }));
    } else {
      // HTTP fallback
      fetch(httpUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: text, conversation_id: conversationId }),
      })
        .then((r) => r.json())
        .then((data) => {
          conversationId = data.conversation_id;
          removeTyping();
          addMessage(data.response, "assistant");
        })
        .catch(() => {
          removeTyping();
          addMessage("Sorry, I'm having trouble connecting. Please try again.", "assistant");
        });
      showTyping();
    }
  }

  function addMessage(text, role) {
    const msgs = document.getElementById("vf-messages");
    const div = document.createElement("div");
    div.className = `vf-msg ${role}`;
    div.textContent = text;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function showTyping() {
    if (document.getElementById("vf-typing")) return;
    const msgs = document.getElementById("vf-messages");
    const div = document.createElement("div");
    div.id = "vf-typing";
    div.className = "vf-typing";
    div.innerHTML = "<span></span><span></span><span></span>";
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function removeTyping() {
    const t = document.getElementById("vf-typing");
    if (t) t.remove();
  }
})();
