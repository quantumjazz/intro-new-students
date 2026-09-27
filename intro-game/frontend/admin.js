(function () {
  const { adminApi, request, escapeHtml, toast, fmtNum, fmtTime, fmtDate, STATUS_LABELS } = window.IntroShared;

  const KEY_STORAGE = "intro-game-admin-key-v1";
  const SELECTED_STORAGE = "intro-game-selected-v1";
  const LIVE_POLL_MS = 2000;

  let adminKey = "";
  let keyRequired = true;
  let selectedCode = null;
  let liveTimer = null;
  let games = [];

  const els = {
    keyStatus: document.getElementById("admin-key-status"),
    keyBtn: document.getElementById("admin-key-set"),
    keyDialog: document.getElementById("admin-key-dialog"),
    keyForm: document.getElementById("admin-key-form"),
    keyInput: document.getElementById("admin-key-input"),
    keyCancel: document.getElementById("admin-key-cancel"),
    keyClear: document.getElementById("admin-key-clear"),

    livePanel: document.getElementById("live-panel"),
    liveCode: document.getElementById("live-code"),
    liveTitle: document.getElementById("live-title"),
    liveStatus: document.getElementById("live-status"),
    liveCurrent: document.getElementById("live-current"),
    liveClose: document.getElementById("live-close"),
    liveReveal: document.getElementById("live-reveal"),
    liveReopen: document.getElementById("live-reopen"),
    liveResults: document.getElementById("live-results"),
    liveCsv: document.getElementById("live-csv"),
    statCount: document.getElementById("stat-count"),
    statMean: document.getElementById("stat-mean"),
    statTarget: document.getElementById("stat-target"),
    statWinner: document.getElementById("stat-winner"),
    entries: document.getElementById("entries-table").querySelector("tbody"),
    entriesEmpty: document.getElementById("entries-empty"),

    createForm: document.getElementById("create-form"),
    cfTitle: document.getElementById("cf-title"),
    joinUrl: document.getElementById("join-url"),
    resultsLink: document.getElementById("results-link"),

    games: document.getElementById("games-table").querySelector("tbody"),
    gamesEmpty: document.getElementById("games-empty"),
    gamesRefresh: document.getElementById("games-refresh"),
  };

  // ---- Init -----------------------------------------------------------------

  async function init() {
    adminKey = load(KEY_STORAGE) || "";
    selectedCode = load(SELECTED_STORAGE);
    try {
      const health = await request("/api/health");
      keyRequired = health.admin_key !== false;
    } catch (_) { /* assume a key is needed */ }
    refreshKeyStatus();
    els.joinUrl.textContent = window.location.host || "intro.visiometrica.com";

    els.keyBtn.addEventListener("click", openKeyDialog);
    els.keyForm.addEventListener("submit", onKeySubmit);
    els.keyCancel.addEventListener("click", closeKeyDialog);
    els.keyClear.addEventListener("click", () => { setKey(""); closeKeyDialog(); });
    els.keyDialog.addEventListener("close", () => { els.keyInput.value = ""; });

    els.createForm.addEventListener("submit", onCreate);
    els.liveClose.addEventListener("click", () => setStatus("closed"));
    els.liveReveal.addEventListener("click", () => setStatus("revealed"));
    els.liveReopen.addEventListener("click", () => setStatus("open"));
    els.liveCsv.addEventListener("click", downloadCsv);
    els.gamesRefresh.addEventListener("click", loadGames);
    els.entries.addEventListener("click", onEntryAction);
    els.games.addEventListener("click", onGameAction);

    if (keyRequired && !adminKey) openKeyDialog();
    loadGames(true);
  }

  function load(key) {
    try { return window.localStorage.getItem(key); } catch (_) { return null; }
  }
  function store(key, value) {
    try {
      if (value) window.localStorage.setItem(key, value);
      else window.localStorage.removeItem(key);
    } catch (_) { /* ignore */ }
  }

  // ---- Admin key ------------------------------------------------------------

  function refreshKeyStatus() {
    els.keyStatus.textContent = !keyRequired
      ? "ключ: не е нужен"
      : adminKey ? "ключ: зададен" : "ключ: не е зададен";
  }

  function setKey(value) {
    adminKey = value.trim();
    store(KEY_STORAGE, adminKey);
    refreshKeyStatus();
    loadGames();
  }

  function openKeyDialog() {
    els.keyInput.value = adminKey;
    if (typeof els.keyDialog.showModal === "function") els.keyDialog.showModal();
    else els.keyDialog.setAttribute("open", "");
    window.setTimeout(() => { els.keyInput.focus(); els.keyInput.select(); }, 0);
  }

  function closeKeyDialog() {
    if (typeof els.keyDialog.close === "function" && els.keyDialog.open) els.keyDialog.close();
    else els.keyDialog.removeAttribute("open");
  }

  function onKeySubmit(event) {
    event.preventDefault();
    setKey(els.keyInput.value);
    closeKeyDialog();
  }

  // ---- Games list -------------------------------------------------------------

  async function loadGames(first) {
    try {
      const payload = await adminApi("/api/admin/games", adminKey);
      games = payload.games || [];
      renderGames();
      // On opening the page, jump to a newer open game (e.g. one created on
      // another device) instead of the game remembered from last time.
      const newestOpen = games[0] && games[0].status === "open" ? games[0].code : null;
      if (first && newestOpen && newestOpen !== selectedCode) selectedCode = newestOpen;
      if (!selectedCode || !games.some((g) => g.code === selectedCode)) {
        select(games.length ? games[0].code : null);
      } else {
        loadLive();
      }
    } catch (exc) {
      toast(exc.message, "error");
    }
  }

  function renderGames() {
    els.gamesEmpty.hidden = games.length > 0;
    els.games.innerHTML = games.map((g) => `
      <tr class="${g.code === selectedCode ? "is-selected" : ""}">
        <td><strong>${escapeHtml(g.code)}</strong></td>
        <td>${escapeHtml(g.title)}</td>
        <td>${statusBadge(g.status)}</td>
        <td class="num">${g.count}</td>
        <td class="hide-sm">${fmtDate(g.created_at)}</td>
        <td class="num">
          <div class="actions compact" style="justify-content: flex-end;">
            <button class="button small" data-action="select" data-code="${escapeHtml(g.code)}" type="button">Избери</button>
            <button class="button small danger" data-action="delete" data-code="${escapeHtml(g.code)}" type="button">Изтрий</button>
          </div>
        </td>
      </tr>`).join("");
  }

  function statusTone(status) {
    return status === "open" ? "ok" : status === "revealed" ? "gold" : "muted";
  }

  function statusBadge(status) {
    return `<span class="badge ${statusTone(status)}">${escapeHtml(STATUS_LABELS[status] || status)}</span>`;
  }

  async function onGameAction(event) {
    const btn = event.target.closest("button[data-action]");
    if (!btn) return;
    const code = btn.dataset.code;
    if (btn.dataset.action === "select") {
      select(code);
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    if (btn.dataset.action === "delete") {
      if (!window.confirm(`Да изтрия ли игра ${code} с всички отговори?`)) return;
      try {
        await adminApi(`/api/admin/games/${code}`, adminKey, { method: "DELETE" });
        if (selectedCode === code) select(null);
        toast("Играта е изтрита.");
        loadGames();
      } catch (exc) {
        toast(exc.message, "error");
      }
    }
  }

  // ---- Create -----------------------------------------------------------------

  async function onCreate(event) {
    event.preventDefault();
    const open = games.find((g) => g.status === "open");
    if (open && !window.confirm(`Игра ${open.code} е още отворена и ще се затвори. Продължаваме ли?`)) return;
    try {
      const payload = await adminApi("/api/admin/games", adminKey, {
        method: "POST",
        body: { title: els.cfTitle.value.trim() || null },
      });
      els.cfTitle.value = "";
      toast(`Игра ${payload.game.code} е отворена.`);
      selectedCode = payload.game.code;
      store(SELECTED_STORAGE, selectedCode);
      loadGames();
    } catch (exc) {
      toast(exc.message, "error");
    }
  }

  // ---- Selected game --------------------------------------------------------------

  function select(code) {
    selectedCode = code;
    store(SELECTED_STORAGE, code);
    renderGames();
    clearTimeout(liveTimer);
    if (!code) {
      els.livePanel.hidden = true;
      return;
    }
    loadLive();
  }

  async function loadLive() {
    clearTimeout(liveTimer);
    const code = selectedCode;
    if (!code) return;
    try {
      const payload = await adminApi(`/api/admin/games/${code}`, adminKey);
      if (code !== selectedCode) return;
      renderLive(payload);
    } catch (exc) {
      toast(exc.message, "error");
    }
    liveTimer = setTimeout(loadLive, LIVE_POLL_MS);
  }

  function renderLive({ game, is_current: isCurrent, entries, results }) {
    els.livePanel.hidden = false;
    els.liveCode.textContent = `Игра ${game.code}`;
    els.liveTitle.textContent = game.title;
    els.liveStatus.className = `badge ${statusTone(game.status)}`;
    els.liveStatus.textContent = STATUS_LABELS[game.status] || game.status;
    els.liveCurrent.hidden = isCurrent;
    els.liveClose.hidden = game.status !== "open";
    els.liveReveal.hidden = game.status !== "closed";
    els.liveReopen.hidden = game.status === "open" || !isCurrent;
    const resultsHref = isCurrent ? "results.html" : `results.html?game=${encodeURIComponent(game.code)}`;
    els.liveResults.href = resultsHref;
    els.resultsLink.href = resultsHref;

    els.statCount.textContent = String(game.count);
    els.statMean.textContent = fmtNum(results.mean, 1);
    els.statTarget.textContent = fmtNum(results.target, 1);
    els.statWinner.textContent = results.winners.length
      ? results.winners.map((w) => `${w.name} · ${fmtNum(w.value, 2)}`).join(", ")
      : "—";

    const listed = games.find((g) => g.code === game.code);
    if (listed && (listed.count !== game.count || listed.status !== game.status)) {
      Object.assign(listed, game);
      renderGames();
    }

    els.entriesEmpty.hidden = entries.length > 0;
    els.entries.innerHTML = entries.map((e) => `
      <tr class="${e.hidden ? "is-hidden" : ""}">
        <td class="hide-sm">${fmtTime(e.updated_at)}</td>
        <td>${escapeHtml(e.name)}</td>
        <td class="num">${fmtNum(e.value, 2)}</td>
        <td class="num hide-sm">${e.distance === undefined ? "—" : fmtNum(e.distance, 2)}</td>
        <td class="num">
          <button class="button small ${e.hidden ? "" : "danger"}" type="button"
                  data-entry="${e.id}" data-hidden="${e.hidden ? "0" : "1"}">${e.hidden ? "Върни" : "Скрий"}</button>
        </td>
      </tr>`).join("");
  }

  async function setStatus(status) {
    if (!selectedCode) return;
    try {
      await adminApi(`/api/admin/games/${selectedCode}/status`, adminKey, {
        method: "POST",
        body: { status },
      });
      toast(status === "open" ? "Играта е отворена." : status === "closed" ? "Играта е затворена." : "Резултатите са на телефоните.");
      loadGames();
    } catch (exc) {
      toast(exc.message, "error");
    }
  }

  async function onEntryAction(event) {
    const btn = event.target.closest("button[data-entry]");
    if (!btn || !selectedCode) return;
    try {
      await adminApi(`/api/admin/games/${selectedCode}/entries/${btn.dataset.entry}`, adminKey, {
        method: "POST",
        body: { hidden: btn.dataset.hidden === "1" },
      });
      loadLive();
    } catch (exc) {
      toast(exc.message, "error");
    }
  }

  async function downloadCsv() {
    if (!selectedCode) return;
    try {
      const response = await adminApi(`/api/admin/games/${selectedCode}/csv`, adminKey, { raw: true });
      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="([^"]+)"/);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = match ? match[1] : `dve-treti-${selectedCode}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (exc) {
      toast(exc.message, "error");
    }
  }

  init();
})();
