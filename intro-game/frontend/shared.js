(function () {
  // The backend serves these pages itself, so the API is same-origin.
  // INTRO_API_BASE (set by the page before this script) overrides it; pages
  // opened straight from disk talk to the dev backend on port 8004.
  function defaultApiBase() {
    if (typeof window === "undefined") return "";
    if (window.INTRO_API_BASE) return window.INTRO_API_BASE;
    const { protocol, host } = window.location;
    if (protocol === "file:") return "http://localhost:8004";
    return `${protocol}//${host}`;
  }
  const API_BASE = defaultApiBase();
  const FACTOR_LABEL = "2/3";

  // Plain regex replaces: older phones (iOS < 13.4) cannot parse ?? or replaceAll.
  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function toast(message, tone = "ok", lifetimeMs = 3200) {
    let region = document.querySelector(".toast-region");
    if (!region) {
      region = document.createElement("div");
      region.className = "toast-region";
      document.body.appendChild(region);
    }
    const div = document.createElement("div");
    div.className = `toast ${tone === "error" ? "error" : tone === "ok" ? "ok" : ""}`;
    div.textContent = message;
    region.appendChild(div);
    setTimeout(() => div.remove(), lifetimeMs);
  }

  function encodeBase64Utf8(value) {
    const bytes = new TextEncoder().encode(value);
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    return btoa(binary);
  }

  function canUseRawHeaderValue(value) {
    for (let i = 0; i < value.length; i += 1) {
      const code = value.charCodeAt(i);
      if (code < 32 || code === 127 || code > 255) return false;
    }
    return true;
  }

  async function request(path, { method = "GET", body, adminKey, raw } = {}) {
    const apiBase = API_BASE.replace(/\/$/, "");
    if (window.location.protocol === "https:" && apiBase.startsWith("http://")) {
      throw new Error("This page is HTTPS, so the API base must also be HTTPS.");
    }
    const headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (adminKey) {
      // Browsers require header values to be byte strings; the base64 copy
      // lets a mistyped Cyrillic key reach the server and fail normally.
      headers["X-Admin-Key-B64"] = encodeBase64Utf8(adminKey);
      if (canUseRawHeaderValue(adminKey)) headers["X-Admin-Key"] = adminKey;
    }
    let response;
    try {
      response = await fetch(`${apiBase}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        cache: "no-store",
      });
    } catch (_) {
      throw new Error("Няма връзка със сървъра. Опитайте пак.");
    }
    if (raw) {
      if (!response.ok) {
        let msg = `Заявката не успя (${response.status}).`;
        try {
          const errPayload = await response.json();
          if (errPayload && errPayload.error) msg = errPayload.error;
        } catch (_) { /* ignore */ }
        throw new Error(msg);
      }
      return response;
    }
    const contentType = response.headers.get("Content-Type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json().catch(() => ({}))
      : await response.text();
    if (!response.ok) {
      const msg = (payload && payload.error) || `Заявката не успя (${response.status}).`;
      throw new Error(msg);
    }
    return payload;
  }

  function publicApi(path, opts) {
    return request(path, opts);
  }

  function adminApi(path, adminKey, opts = {}) {
    return request(path, { ...opts, adminKey: (adminKey || "").trim() });
  }

  // Bulgarian number format: decimal comma, at most `digits` decimals.
  function fmtNum(value, digits = 1) {
    if (value === null || value === undefined || Number.isNaN(value)) return "—";
    const factor = 10 ** digits;
    const rounded = Math.round(value * factor) / factor;
    return String(rounded).replace(".", ",");
  }

  function fmtTime(epochMs) {
    if (!epochMs) return "—";
    return new Date(epochMs).toLocaleTimeString("bg-BG", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function fmtDate(epochMs) {
    if (!epochMs) return "—";
    return new Date(epochMs).toLocaleString("bg-BG", {
      day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  }

  function plural(n, one, many) {
    return `${n} ${n === 1 ? one : many}`;
  }

  const STATUS_LABELS = {
    open: "отворена",
    closed: "затворена",
    revealed: "резултатите са на телефоните",
  };

  const LEVEL_TEXT = {
    k0: "0 хода напред: числото не отчита какво ще изберат другите.",
    k1: "1 ход напред: около 33, две трети от 50.",
    k2: "2 хода напред: около 22, две трети от 33.",
    k3: "3 хода напред: около 15, две трети от 22.",
    k4: "4 или повече хода напред.",
    kinf: "Докрай: нулата, отговорът от учебника.",
  };

  window.IntroShared = {
    API_BASE,
    FACTOR_LABEL,
    escapeHtml,
    toast,
    publicApi,
    adminApi,
    request,
    fmtNum,
    fmtTime,
    fmtDate,
    plural,
    STATUS_LABELS,
    LEVEL_TEXT,
  };
})();
