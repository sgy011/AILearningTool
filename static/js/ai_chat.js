(function () {
    "use strict";

    const el = (id) => document.getElementById(id);

    const sidebar = el("sidebar");
    const hamburger = el("hamburger-btn");
    const menuItems = document.querySelectorAll(".menu-item[data-view]");
    const imageArea = el("image-generation-area");
    const chatArea = el("chat-container");
    const inputArea = el("input-area");
    const modelSelect = el("header-model-select");
    const newChatBtn = el("header-new-chat-btn");
    const messagesEl = el("messages");
    const messageInput = el("message-input");
    const sendBtn = el("send-btn");
    const charCount = el("char-count");
    const generateBtn = el("generate-btn");
    const promptInput = el("prompt-input");
    const sizeSelect = el("size-select");
    const numSelect = el("num-select");
    const imageDisplay = el("image-display");
    const configAlert = el("ai-config-alert");

    const GENERATE_BTN_HTML = '<i class="fas fa-magic"></i> 生成图片';

    const STORAGE_KEY = "transvsverter_ai_chat_v1";
    const MAX_SESSIONS = 40;
    const sessionsListEl = el("sessions-list");

    let chatMessages = [];
    let sessionsList = [];
    let currentSessionId = null;
    let pollTimer = null;

    function newSessionId() {
        if (typeof crypto !== "undefined" && crypto.randomUUID) {
            return crypto.randomUUID();
        }
        return "s-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10);
    }

    function cloneMsgs(msgs) {
        try {
            return JSON.parse(JSON.stringify(msgs || []));
        } catch (_) {
            return [];
        }
    }

    function normalizeSession(s) {
        if (!s || typeof s !== "object") return null;
        const msgs = Array.isArray(s.messages)
            ? s.messages.filter(function (m) {
                  return m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string";
              })
            : [];
        return {
            id: s.id || newSessionId(),
            title: typeof s.title === "string" ? s.title : "新对话",
            preview: typeof s.preview === "string" ? s.preview : "",
            messages: msgs,
            updatedAt: typeof s.updatedAt === "number" ? s.updatedAt : 0,
        };
    }

    function deriveTitle(msgs) {
        var first = msgs.find(function (m) {
            return m.role === "user" && (m.content || "").trim();
        });
        if (!first) return "新对话";
        var t = (first.content || "").trim().slice(0, 28);
        return t || "新对话";
    }

    function derivePreview(msgs) {
        if (!msgs.length) return "暂无消息";
        var last = msgs[msgs.length - 1];
        var tag = last.role === "user" ? "你" : "AI";
        var c = (last.content || "").trim().replace(/\s+/g, " ").slice(0, 48);
        return tag + "：" + c;
    }

    function syncCurrentToSession() {
        if (!currentSessionId) return;
        var idx = sessionsList.findIndex(function (s) {
            return s.id === currentSessionId;
        });
        if (idx === -1) return;
        sessionsList[idx].messages = chatMessages.slice();
        sessionsList[idx].updatedAt = Date.now();
        sessionsList[idx].title = deriveTitle(chatMessages);
        sessionsList[idx].preview = derivePreview(chatMessages);
    }

    function persistState() {
        syncCurrentToSession();
        try {
            var list = sessionsList.slice();
            list.sort(function (a, b) {
                return (b.updatedAt || 0) - (a.updatedAt || 0);
            });
            if (list.length > MAX_SESSIONS) {
                list = list.slice(0, MAX_SESSIONS);
            }
            sessionsList = list;
            localStorage.setItem(
                STORAGE_KEY,
                JSON.stringify({ sessions: sessionsList, currentId: currentSessionId })
            );
        } catch (e) {
            console.warn("AI 历史对话保存失败", e);
        }
    }

    function renderSessionsList() {
        if (!sessionsListEl) return;
        sessionsListEl.innerHTML = "";
        var sorted = sessionsList.slice().sort(function (a, b) {
            return (b.updatedAt || 0) - (a.updatedAt || 0);
        });
        sorted.forEach(function (s) {
            var div = document.createElement("div");
            div.className = "history-item" + (s.id === currentSessionId ? " active" : "");
            div.setAttribute("data-session-id", s.id);
            var t = document.createElement("span");
            t.className = "history-title";
            t.textContent = s.title || "新对话";
            var p = document.createElement("span");
            p.className = "history-preview";
            p.textContent = s.preview || "";
            div.appendChild(t);
            div.appendChild(p);
            div.addEventListener("click", function () {
                switchSession(s.id);
            });
            sessionsListEl.appendChild(div);
        });
    }

    function switchSession(id) {
        if (!id || id === currentSessionId) return;
        syncCurrentToSession();
        persistState();
        var s = sessionsList.find(function (x) {
            return x.id === id;
        });
        if (!s) return;
        currentSessionId = id;
        chatMessages = cloneMsgs(s.messages);
        renderMessages();
        renderSessionsList();
        persistState();
    }

    function startNewSession() {
        syncCurrentToSession();
        var nid = newSessionId();
        sessionsList.unshift({
            id: nid,
            title: "新对话",
            preview: "暂无消息",
            messages: [],
            updatedAt: Date.now(),
        });
        currentSessionId = nid;
        chatMessages = [];
        if (sessionsList.length > MAX_SESSIONS) {
            sessionsList = sessionsList.slice(0, MAX_SESSIONS);
        }
        renderMessages();
        renderSessionsList();
        persistState();
    }

    function initChatSessions() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            if (raw) {
                var d = JSON.parse(raw);
                if (d.sessions && Array.isArray(d.sessions) && d.sessions.length) {
                    sessionsList = d.sessions.map(normalizeSession).filter(Boolean);
                    if (!sessionsList.length) {
                        throw new Error("empty");
                    }
                    currentSessionId = d.currentId;
                    var cur = sessionsList.find(function (s) {
                        return s.id === currentSessionId;
                    });
                    if (!cur) {
                        currentSessionId = sessionsList[0].id;
                    }
                    var active = sessionsList.find(function (s) {
                        return s.id === currentSessionId;
                    });
                    chatMessages = cloneMsgs(active.messages);
                    renderSessionsList();
                    renderMessages();
                    return;
                }
            }
        } catch (_) {}
        var id = newSessionId();
        sessionsList = [
            {
                id: id,
                title: "新对话",
                preview: "暂无消息",
                messages: [],
                updatedAt: Date.now(),
            },
        ];
        currentSessionId = id;
        chatMessages = [];
        renderSessionsList();
        renderMessages();
        persistState();
    }

    function setGenerateLoading(on) {
        if (!generateBtn) return;
        generateBtn.disabled = !!on;
        if (on) {
            generateBtn.dataset.loading = "1";
            generateBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 正在生成中...';
        } else {
            delete generateBtn.dataset.loading;
            generateBtn.innerHTML = GENERATE_BTN_HTML;
        }
    }

    function showAlert(text, isError) {
        if (!configAlert) return;
        configAlert.textContent = text;
        configAlert.classList.remove("d-none");
        configAlert.classList.toggle("error", !!isError);
        if (!isError && text) {
            setTimeout(() => {
                configAlert.classList.add("d-none");
            }, 6000);
        }
    }

    function hideAlert() {
        if (configAlert) {
            configAlert.classList.add("d-none");
        }
    }

    async function fetchConfig() {
        try {
            const r = await fetch("/api/ai/config");
            const data = await r.json();
            if (!data.configured) {
                showAlert(
                    "未检测到 MODELSCOPE_TOKEN：请在项目根目录 .env 中配置后重启服务，否则无法调用对话与文生图。",
                    true
                );
                if (generateBtn) generateBtn.disabled = true;
            } else {
                hideAlert();
                if (generateBtn) generateBtn.disabled = false;
            }
        } catch (_) {
            showAlert("无法读取服务配置。", true);
        }
    }

    function setView(view) {
        const isImage = view === "image";
        menuItems.forEach((item) => {
            item.classList.toggle("active", item.dataset.view === view);
        });
        if (imageArea) imageArea.style.display = isImage ? "" : "none";
        if (chatArea) chatArea.style.display = isImage ? "none" : "";
        if (inputArea) inputArea.style.display = isImage ? "none" : "";

        if (modelSelect) {
            if (isImage) {
                modelSelect.value = "Qwen/Qwen-Image";
            } else {
                modelSelect.value = "moonshotai/Kimi-K2.5";
            }
        }
    }

    menuItems.forEach((item) => {
        item.addEventListener("click", () => setView(item.dataset.view || "chat"));
    });

    if (hamburger && sidebar) {
        hamburger.addEventListener("click", () => {
            sidebar.classList.toggle("collapsed");
        });
    }

    function renderMessages() {
        if (!messagesEl) return;
        messagesEl.innerHTML = "";
        chatMessages.forEach((m, i) => {
            const row = document.createElement("div");
            row.className = "msg " + (m.role === "user" ? "user" : "assistant");
            row.dataset.index = String(i);
            const av = document.createElement("div");
            av.className = "msg-avatar";
            av.innerHTML =
                m.role === "user"
                    ? '<i class="fas fa-user"></i>'
                    : '<i class="fas fa-robot"></i>';
            const bubble = document.createElement("div");
            bubble.className = "msg-bubble";
            bubble.textContent = m.content || "";
            row.appendChild(av);
            row.appendChild(bubble);
            messagesEl.appendChild(row);
        });
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function appendLoading() {
        const row = document.createElement("div");
        row.className = "msg assistant msg-loading";
        row.id = "msg-loading-row";
        row.innerHTML =
            '<div class="msg-avatar"><i class="fas fa-robot"></i></div>' +
            '<div class="msg-bubble">正在思考…</div>';
        messagesEl.appendChild(row);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function removeLoading() {
        const lr = el("msg-loading-row");
        if (lr) lr.remove();
    }

    async function sendChat() {
        const text = (messageInput && messageInput.value) || "";
        const trimmed = text.trim();
        if (!trimmed) return;

        const model = (modelSelect && modelSelect.value) || "moonshotai/Kimi-K2.5";
        chatMessages.push({ role: "user", content: trimmed });
        messageInput.value = "";
        if (charCount) charCount.textContent = "0";
        renderMessages();
        appendLoading();
        sendBtn.disabled = true;

        const payload = {
            model,
            messages: chatMessages.map((m) => ({ role: m.role, content: m.content })),
        };

        try {
            const r = await fetch("/api/ai/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const data = await r.json();
            removeLoading();
            if (!r.ok || !data.success) {
                const err = data.error || "请求失败";
                chatMessages.push({ role: "assistant", content: "错误：" + err });
            } else {
                chatMessages.push({
                    role: "assistant",
                    content: data.content || "(空回复)",
                });
            }
        } catch (e) {
            removeLoading();
            chatMessages.push({
                role: "assistant",
                content: "网络错误：" + (e && e.message ? e.message : String(e)),
            });
        }
        renderMessages();
        sendBtn.disabled = false;
        persistState();
    }

    if (sendBtn) {
        sendBtn.addEventListener("click", sendChat);
    }
    if (messageInput) {
        messageInput.addEventListener("input", () => {
            if (charCount) charCount.textContent = String(messageInput.value.length);
        });
        messageInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendChat();
            }
        });
    }

    if (newChatBtn) {
        newChatBtn.addEventListener("click", function () {
            startNewSession();
        });
    }

    function clearPoll() {
        if (pollTimer) {
            clearTimeout(pollTimer);
            pollTimer = null;
        }
    }

    function showImageResults(dataUrls) {
        if (!imageDisplay) return;
        imageDisplay.innerHTML = "";
        const wrap = document.createElement("div");
        wrap.className = "image-results";
        if (dataUrls.length === 1) {
            wrap.classList.add("image-results--single");
        }
        dataUrls.forEach((u) => {
            const img = document.createElement("img");
            img.src = u;
            img.alt = "生成结果";
            wrap.appendChild(img);
        });
        imageDisplay.appendChild(wrap);
    }

    function showGenerating() {
        if (!imageDisplay) return;
        imageDisplay.innerHTML = "";
        const box = document.createElement("div");
        box.className = "display-generating";
        box.innerHTML =
            '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i><p>正在生成中...</p>';
        imageDisplay.appendChild(box);
    }

    function showPlaceholder() {
        if (!imageDisplay) return;
        imageDisplay.innerHTML = "";
        const ph = document.createElement("div");
        ph.className = "display-placeholder";
        ph.id = "image-placeholder";
        ph.innerHTML =
            '<i class="fas fa-image"></i><p>生成的图片将显示在这里</p>';
        imageDisplay.appendChild(ph);
    }

    async function pollTask(taskId) {
        clearPoll();
        const tick = async () => {
            try {
                const r = await fetch("/api/ai/images/task/" + encodeURIComponent(taskId));
                const data = await r.json();
                if (!r.ok || !data.success) {
                    setGenerateLoading(false);
                    showPlaceholder();
                    showAlert(data.error || "查询任务失败", true);
                    return;
                }
                const status = data.task_status;
                if (status === "SUCCEED") {
                    setGenerateLoading(false);
                    if (data.images && data.images.length) {
                        showImageResults(data.images);
                    } else {
                        showPlaceholder();
                        showAlert("任务成功但未返回图片。", true);
                    }
                    return;
                }
                if (status === "FAILED") {
                    setGenerateLoading(false);
                    showPlaceholder();
                    showAlert(data.error_message || "图片生成失败。", true);
                    return;
                }
                pollTimer = setTimeout(tick, 3000);
            } catch (e) {
                setGenerateLoading(false);
                showPlaceholder();
                showAlert("轮询失败：" + (e && e.message ? e.message : String(e)), true);
            }
        };
        pollTimer = setTimeout(tick, 2000);
    }

    if (generateBtn) {
        generateBtn.addEventListener("click", async () => {
            const prompt = (promptInput && promptInput.value || "").trim();
            if (!prompt) {
                showAlert("请输入图片描述。", true);
                return;
            }
            hideAlert();
            clearPoll();
            setGenerateLoading(true);
            showGenerating();
            const body = {
                prompt,
                model: "Qwen/Qwen-Image",
                size: sizeSelect ? sizeSelect.value : "1024x1024",
                n: numSelect ? parseInt(numSelect.value, 10) || 1 : 1,
            };
            try {
                const r = await fetch("/api/ai/images/generate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(body),
                });
                const data = await r.json();
                if (!r.ok || !data.success) {
                    setGenerateLoading(false);
                    showPlaceholder();
                    showAlert(data.error || "提交失败", true);
                    return;
                }
                if (data.task_id) {
                    pollTask(data.task_id);
                } else {
                    setGenerateLoading(false);
                    showPlaceholder();
                    showAlert("未返回任务 ID。", true);
                }
            } catch (e) {
                setGenerateLoading(false);
                showPlaceholder();
                showAlert("请求失败：" + (e && e.message ? e.message : String(e)), true);
            }
        });
    }

    initChatSessions();
    setView("chat");
    fetchConfig();
})();
