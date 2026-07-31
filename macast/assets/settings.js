"use strict";

const state = {
    csrfToken: "",
};

const api = async (query) => {
    const response = await fetch(`/api?query=${encodeURIComponent(query)}`, {
        cache: "no-store",
        credentials: "same-origin",
    });
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
};

const setMessage = (element, message, isError = false) => {
    element.textContent = message;
    element.classList.toggle("error", isError);
};

const showPage = (page) => {
    const normalized = ["1", "2", "3", "4"].includes(String(page)) ? String(page) : "1";
    document.querySelectorAll("[data-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.panel !== normalized;
    });
    document.querySelectorAll("[data-page]").forEach((button) => {
        button.classList.toggle("active", button.dataset.page === normalized);
    });
    const url = new URL(window.location.href);
    url.searchParams.set("page", normalized);
    window.history.replaceState({ page: normalized }, "", url);
};

const loadSession = async () => {
    const session = await api("session");
    state.csrfToken = session.csrf_token;
};

const loadComponents = async () => {
    const target = document.querySelector("#components");
    target.textContent = "正在读取本地组件……";
    try {
        const data = await api("plugin-info");
        document.querySelector("#version").textContent = `v${data.version} · ${data.platform}`;
        target.replaceChildren();
        const components = Array.isArray(data.plugins) ? data.plugins : [];
        components.forEach((component) => {
            const card = document.createElement("article");
            const title = document.createElement("strong");
            const description = document.createElement("p");
            const meta = document.createElement("small");
            title.textContent = component.title || component.renderer || component.protocol || "Component";
            description.textContent = component.desc || "本地组件";
            meta.textContent = [
                component.version ? `v${component.version}` : "",
                component.platform || "",
                component.author || "Macast",
            ].filter(Boolean).join(" · ");
            card.append(title, description, meta);
            target.append(card);
        });
        if (components.length === 0) {
            target.textContent = "未发现额外组件。";
        }
    } catch (error) {
        target.textContent = `读取失败：${error.message}`;
    }
};

const loadSettings = async () => {
    const textarea = document.querySelector("#settings-json");
    const message = document.querySelector("#settings-message");
    setMessage(message, "正在读取……");
    try {
        const settings = await api("launch-param");
        textarea.value = JSON.stringify(settings, null, 4);
        setMessage(message, "已读取");
    } catch (error) {
        setMessage(message, `读取失败：${error.message}`, true);
    }
};

const saveSettings = async () => {
    const textarea = document.querySelector("#settings-json");
    const message = document.querySelector("#settings-message");
    let settings;
    try {
        settings = JSON.parse(textarea.value);
        if (!settings || Array.isArray(settings) || typeof settings !== "object") {
            throw new Error("必须是 JSON 对象");
        }
    } catch (error) {
        setMessage(message, `JSON 格式错误：${error.message}`, true);
        return;
    }

    setMessage(message, "正在保存……");
    const body = new URLSearchParams({
        "save-launch-param": JSON.stringify(settings),
    });
    try {
        const response = await fetch("/", {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "X-Macast-CSRF": state.csrfToken,
            },
            body,
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const result = await response.json();
        if (result.code !== 0) {
            throw new Error(result.message || "保存失败");
        }
        setMessage(message, "已保存，播放器正在重载");
    } catch (error) {
        setMessage(message, `保存连接已中断；服务可能正在重载（${error.message}）`, true);
    }
};

const loadLog = async () => {
    const target = document.querySelector("#log-output");
    target.textContent = "正在读取日志……";
    try {
        const data = await api("log");
        target.textContent = data.logs || "暂无日志。";
    } catch (error) {
        target.textContent = `读取失败：${error.message}`;
    }
};

window.addEventListener("DOMContentLoaded", async () => {
    document.querySelectorAll("[data-page]").forEach((button) => {
        button.addEventListener("click", () => {
            showPage(button.dataset.page);
            if (button.dataset.page === "2") {
                loadSettings();
            } else if (button.dataset.page === "3") {
                loadLog();
            }
        });
    });
    document.querySelector("#refresh-components").addEventListener("click", loadComponents);
    document.querySelector("#refresh-log").addEventListener("click", loadLog);
    document.querySelector("#save-settings").addEventListener("click", saveSettings);

    showPage(new URLSearchParams(window.location.search).get("page"));
    try {
        await loadSession();
        await loadComponents();
    } catch (error) {
        document.querySelector("#version").textContent = `连接失败 · ${error.message}`;
    }
});
