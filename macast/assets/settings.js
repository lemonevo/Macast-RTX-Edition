"use strict";

const state = {
    csrfToken: "",
};

const api = async (query, params = {}) => {
    const search = new URLSearchParams({ query, ...params });
    const response = await fetch(`/api?${search}`, {
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
    const normalized = ["1", "2", "3", "4", "5"].includes(String(page)) ? String(page) : "1";
    document.querySelectorAll("[data-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.panel !== normalized;
    });
    document.querySelectorAll("[data-page]").forEach((button) => {
        button.classList.toggle("active", button.dataset.page === normalized);
    });
    const url = new URL(window.location.href);
    url.searchParams.set("page", normalized);
    window.history.replaceState({ page: normalized }, "", url);
    return normalized;
};

const activatePage = (page) => {
    const active = showPage(page);
    if (active === "2") {
        loadPlugins();
    } else if (active === "3") {
        loadSettings();
    } else if (active === "4") {
        loadLog();
    }
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

const pluginState = {
    platform: "",
    repoPlugins: [],
    localPlugins: new Map(),
    pendingPlugins: new Map(),
};

const isInstalled = (plugin) => pluginState.localPlugins.has(plugin.title)
    || pluginState.pendingPlugins.has(plugin.title);

const collectLocalPlugins = (components) => {
    const plugins = new Map();
    components.forEach((component) => {
        if (component.title) {
            plugins.set(component.title, component);
        }
    });
    return plugins;
};

const renderPlugins = () => {
    const target = document.querySelector("#plugin-list");
    target.replaceChildren();
    pluginState.repoPlugins.forEach((plugin) => {
        const local = pluginState.localPlugins.get(plugin.title);
        const pending = pluginState.pendingPlugins.get(plugin.title);
        const supported = !plugin.platform
            || plugin.platform.split(",").map((item) => item.trim()).includes(pluginState.platform);
        const installed = isInstalled(plugin);
        const installedVersion = local ? local.version : pending;
        const upToDate = installed
            && String(installedVersion || "") === String(plugin.version || "");

        const card = document.createElement("article");
        card.className = "plugin-card";

        const header = document.createElement("header");
        const title = document.createElement("strong");
        title.textContent = plugin.title;
        const meta = document.createElement("small");
        meta.textContent = [
            plugin.version ? `v${plugin.version}` : "",
            plugin.platform || "any",
        ].filter(Boolean).join(" · ");
        header.append(title, meta);

        const description = document.createElement("p");
        description.textContent = plugin.desc || "未提供说明。";

        const footer = document.createElement("div");
        footer.className = "plugin-actions";
        const author = document.createElement("small");
        author.textContent = `${plugin.author || "Macast"} · ${plugin.type === "protocol" ? "Protocol" : "Renderer"}`;

        const buttons = document.createElement("div");
        buttons.className = "plugin-buttons";
        if (!supported) {
            const blocked = document.createElement("button");
            blocked.type = "button";
            blocked.textContent = "不支持当前平台";
            blocked.disabled = true;
            buttons.append(blocked);
        } else {
            if (installed && upToDate) {
                const badge = document.createElement("span");
                badge.className = "plugin-state";
                badge.textContent = pending ? "已安装，正在重启" : "已安装";
                buttons.append(badge);
            } else {
                const button = document.createElement("button");
                button.type = "button";
                button.textContent = installed ? `更新到 v${plugin.version}` : "安装";
                button.addEventListener("click", () => installPlugin(plugin, button));
                buttons.append(button);
            }
            if (installed) {
                const remove = document.createElement("button");
                remove.type = "button";
                remove.className = "secondary";
                remove.textContent = "卸载";
                remove.addEventListener("click", () => uninstallPlugin(plugin, remove));
                buttons.append(remove);
            }
        }
        footer.append(author, buttons);
        card.append(header, description, footer);
        target.append(card);
    });
};

const loadPlugins = async (refresh = false) => {
    const target = document.querySelector("#plugin-list");
    const message = document.querySelector("#plugin-message");
    target.replaceChildren();
    setMessage(message, refresh ? "正在重新读取插件列表……" : "正在读取插件列表……");
    try {
        const [repo, local] = await Promise.all([
            api("plugin-repo", refresh ? { refresh: "1" } : {}),
            api("plugin-info"),
        ]);
        pluginState.platform = local.platform || "";
        pluginState.localPlugins = collectLocalPlugins(
            Array.isArray(local.plugins) ? local.plugins : []);
        // A plugin that the restarted process already loaded is no longer pending.
        pluginState.localPlugins.forEach((component, title) => {
            pluginState.pendingPlugins.delete(title);
        });
        if (repo.code && repo.code !== 0) {
            throw new Error(repo.message || "无法读取插件仓库");
        }
        pluginState.repoPlugins = Array.isArray(repo.plugins) ? repo.plugins : [];
        const link = document.querySelector("#plugin-repo-link");
        if (repo.repo_url) {
            link.href = repo.repo_url;
        }
        renderPlugins();
        if (pluginState.repoPlugins.length === 0) {
            setMessage(message, "插件仓库暂时没有可安装的插件。");
            return;
        }
        const installedCount = pluginState.repoPlugins.filter(isInstalled).length;
        setMessage(message, `共 ${pluginState.repoPlugins.length} 个插件，其中 ${installedCount} 个已安装。`);
    } catch (error) {
        target.textContent = `读取失败：${error.message}`;
        setMessage(message, `读取插件列表失败：${error.message}`, true);
    }
};

const waitForRestart = async () => {
    // 重启后的进程会换一个新的会话令牌（进程级随机值），用它判断新进程是否已经起来。
    // 只等 "请求成功" 是不够的：旧进程在 execv 之前仍然会正常响应，
    // 那样会读到旧的插件列表，表现为"必须手动刷新页面才显示正确状态"。
    const previousToken = state.csrfToken;
    for (let attempt = 0; attempt < 60; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        try {
            const session = await api("session");
            if (session.csrf_token && session.csrf_token !== previousToken) {
                state.csrfToken = session.csrf_token;
                return true;
            }
        } catch (error) {
            // 服务正在重启，继续等
        }
    }
    return false;
};

const installPlugin = (plugin, button) => runPluginAction("install-plugin", plugin, button, {
    running: `正在下载并安装 ${plugin.title}……`,
    pending: `已安装 ${plugin.title}，Macast 正在重启……`,
    timeout: `已安装 ${plugin.title}，但未确认 Macast 已重启，请手动重启后使用。`,
    unsure: `安装请求已发出，但响应被重启打断；列表已刷新，请确认状态。`,
    failure: "安装失败",
    success: "安装完成，已生效。",
});

const uninstallPlugin = (plugin, button) => {
    if (!window.confirm(`确定卸载 ${plugin.title} 吗？Macast 会重启一次以更新插件列表。`)) {
        return undefined;
    }
    return runPluginAction("uninstall-plugin", plugin, button, {
        running: `正在卸载 ${plugin.title}……`,
        pending: `已卸载 ${plugin.title}，Macast 正在重启……`,
        timeout: `已卸载 ${plugin.title}，但未确认 Macast 已重启，请手动重启后使用。`,
        unsure: `卸载请求已发出，但响应被重启打断；列表已刷新，请确认状态。`,
        failure: "卸载失败",
        success: "已卸载，已生效。",
    });
};

const sendPluginAction = async (action, plugin) => {
    const body = new URLSearchParams({
        // 带上 title，让后端在提示文案里用插件名而不是文件名
        [action]: JSON.stringify({ type: plugin.type, url: plugin.url, title: plugin.title }),
    });
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
        // 后端明确拒绝（例如地址不在白名单、插件文件不存在）：直接报错，不用等重启
        const rejected = new Error(result.message || "操作失败");
        rejected.rejected = true;
        throw rejected;
    }
    return result;
};

const runPluginAction = async (action, plugin, button, messages) => {
    const message = document.querySelector("#plugin-message");
    button.disabled = true;
    setMessage(message, messages.running);

    let result = null;
    let failure = null;
    try {
        result = await sendPluginAction(action, plugin);
    } catch (error) {
        failure = error;
    }

    if (failure && failure.rejected) {
        setMessage(message, `${messages.failure}：${failure.message}`, true);
        button.disabled = false;
        return;
    }

    // 用页面上的插件名维护"待生效"状态，不依赖后端返回的标题
    if (result) {
        if (action === "uninstall-plugin") {
            pluginState.pendingPlugins.delete(plugin.title);
        } else {
            pluginState.pendingPlugins.set(plugin.title, (result.plugin || {}).version || "");
        }
    }

    // 只要后端可能已经重启（后端要求重启，或响应被重启打断），就必须等新进程起来再刷新列表，
    // 否则读到的是旧进程的插件列表
    if ((result && result.restart) || failure) {
        setMessage(message, messages.pending);
        if (!await waitForRestart()) {
            setMessage(message, messages.timeout, true);
            button.disabled = false;
            return;
        }
        await loadComponents();
        await loadPlugins();
        // 重启完成后给出终态提示（后端文案是"正在重启…"，此时已经过时）
        setMessage(message, result ? messages.success : messages.unsure, !result);
        return;
    }

    await loadComponents();
    await loadPlugins();
    setMessage(message, messages.success);
};

window.addEventListener("DOMContentLoaded", async () => {
    document.querySelectorAll("[data-page]").forEach((button) => {
        button.addEventListener("click", () => activatePage(button.dataset.page));
    });
    document.querySelector("#refresh-components").addEventListener("click", loadComponents);
    document.querySelector("#refresh-log").addEventListener("click", loadLog);
    document.querySelector("#refresh-plugins").addEventListener("click", () => loadPlugins(true));
    document.querySelector("#save-settings").addEventListener("click", saveSettings);

    activatePage(new URLSearchParams(window.location.search).get("page"));
    try {
        await loadSession();
        await loadComponents();
    } catch (error) {
        document.querySelector("#version").textContent = `连接失败 · ${error.message}`;
    }
});
