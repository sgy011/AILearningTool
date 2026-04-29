(function () {
    "use strict";

    var modal = document.getElementById("modelscopeConfigModal");
    if (!modal) return;

    var alertEl = document.getElementById("ms-config-alert");
    var statusEl = document.getElementById("ms-token-status");
    var providerSel = document.getElementById("ms-provider");
    var apiKeyLabel = document.getElementById("ms-api-key-label");
    var apiKeyHint = document.getElementById("ms-api-key-hint");
    var apiKeyInput = document.getElementById("ms-api-key-input");
    var clearApiKeyCb = document.getElementById("ms-clear-api-key");
    var clearApiKeyLabel = document.getElementById("ms-clear-api-key-label");
    var baseInput = document.getElementById("ms-base-url");
    var moonBaseInput = document.getElementById("ms-moonshot-base-url");
    var modelInput = document.getElementById("ms-chat-model");
    var moonModelInput = document.getElementById("ms-moonshot-chat-model");
    var saveBtn = document.getElementById("ms-save-btn");

    function showAlert(msg, isErr) {
        if (!alertEl) return;
        alertEl.classList.remove("d-none", "alert-success", "alert-danger");
        alertEl.classList.add(isErr ? "alert-danger" : "alert-success");
        alertEl.textContent = msg;
    }

    function hideAlert() {
        if (alertEl) alertEl.classList.add("d-none");
    }

    function normalizeProvider(v) {
        v = (v || "").trim().toLowerCase();
        if (!v) return "modelscope";
        if (v === "kimi") return "moonshot";
        return v;
    }

    function applyProviderUi(provider) {
        provider = normalizeProvider(provider);
        if (providerSel) providerSel.value = provider;
        if (apiKeyLabel) {
            apiKeyLabel.innerHTML =
                provider === "moonshot"
                    ? 'Moonshot API Key（<code>MOONSHOT_API_KEY</code>）'
                    : 'ModelScope Token（<code>MODELSCOPE_TOKEN</code>）';
        }
        if (apiKeyHint) {
            apiKeyHint.textContent =
                provider === "moonshot"
                    ? "请粘贴 Kimi 官方 API Key（不要带引号/空格/换行）。"
                    : "请粘贴魔塔 ModelScope 的 Token（不要带引号/空格/换行）。";
        }
        if (clearApiKeyLabel) {
            clearApiKeyLabel.textContent =
                provider === "moonshot"
                    ? "清除已保存的 Moonshot Key（运行时文件中的项）"
                    : "清除已保存的 ModelScope Token（运行时文件中的项）";
        }
        // 自动填默认 base_url（高级设置里可见）
        if (baseInput && !baseInput.value) baseInput.value = "https://api-inference.modelscope.cn/v1";
        if (moonBaseInput && !moonBaseInput.value) moonBaseInput.value = "https://api.moonshot.cn/v1";
        if (modelInput && !modelInput.value) modelInput.value = "moonshotai/Kimi-K2.5";
        if (moonModelInput && !moonModelInput.value) moonModelInput.value = "kimi-k2.5";
    }

    async function loadSettings() {
        hideAlert();
        if (apiKeyInput) apiKeyInput.value = "";
        if (clearApiKeyCb) clearApiKeyCb.checked = false;
        if (statusEl) statusEl.textContent = "加载中…";
        try {
            var r = await fetch("/api/settings/modelscope");
            var d = await r.json();
            if (!d.success) throw new Error(d.error || "加载失败");
            applyProviderUi(d.provider || "modelscope");
            if (statusEl) {
                var ms = d.token_set ? ("ModelScope 已配置 " + (d.token_preview || "")) : "ModelScope 未配置";
                var mo = d.moonshot_key_set
                    ? ("Moonshot 已配置 " + (d.moonshot_key_preview || ""))
                    : "Moonshot 未配置";
                statusEl.textContent = ms + "；" + mo;
            }
            if (baseInput) baseInput.value = d.base_url || "";
            if (moonBaseInput) moonBaseInput.value = d.moonshot_base_url || "";
            if (modelInput) modelInput.value = d.chat_model || "";
            if (moonModelInput) moonModelInput.value = d.moonshot_chat_model || "";
        } catch (e) {
            if (statusEl) statusEl.textContent = "加载失败";
            showAlert(e.message || String(e), true);
        }
    }

    modal.addEventListener("show.bs.modal", loadSettings);
    if (providerSel) {
        providerSel.addEventListener("change", function () {
            applyProviderUi(providerSel.value);
            if (apiKeyInput) apiKeyInput.value = "";
            if (clearApiKeyCb) clearApiKeyCb.checked = false;
        });
    }

    if (saveBtn) {
        saveBtn.addEventListener("click", async function () {
            hideAlert();
            try {
                var body = {
                    provider: providerSel ? normalizeProvider(providerSel.value) : "",
                    base_url: baseInput ? baseInput.value.trim() : "",
                    moonshot_base_url: moonBaseInput ? moonBaseInput.value.trim() : "",
                    chat_model: modelInput ? modelInput.value.trim() : "",
                    moonshot_chat_model: moonModelInput ? moonModelInput.value.trim() : "",
                };
                var pv = normalizeProvider(body.provider);
                var keyVal = apiKeyInput && apiKeyInput.value ? apiKeyInput.value : "";
                var clearKey = !!(clearApiKeyCb && clearApiKeyCb.checked);
                if (pv === "moonshot") {
                    body.moonshot_api_key = keyVal;
                    body.clear_moonshot_key = clearKey;
                    body.token = "";
                    body.clear_token = false;
                } else {
                    body.token = keyVal;
                    body.clear_token = clearKey;
                    body.moonshot_api_key = "";
                    body.clear_moonshot_key = false;
                }
                var r = await fetch("/api/settings/modelscope", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(body),
                });
                var d = await r.json();
                if (!r.ok || !d.success) throw new Error(d.error || "保存失败");
                var msg = "已保存并写入运行时配置。";
                if (d.refresh_error) msg += " 每日必读资讯模块：" + d.refresh_error;
                showAlert(msg, !!d.refresh_error);
                if (statusEl) {
                    var ms2 = d.token_set ? ("ModelScope 已配置 " + (d.token_preview || "")) : "ModelScope 未配置";
                    var mo2 = d.moonshot_key_set
                        ? ("Moonshot 已配置 " + (d.moonshot_key_preview || ""))
                        : "Moonshot 未配置";
                    statusEl.textContent = ms2 + "；" + mo2;
                }
                if (apiKeyInput) apiKeyInput.value = "";
                if (clearApiKeyCb) clearApiKeyCb.checked = false;
            } catch (e) {
                showAlert(e.message || String(e), true);
            }
        });
    }
})();
