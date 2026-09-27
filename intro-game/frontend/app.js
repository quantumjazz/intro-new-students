(function () {
  const { publicApi, fmtNum, plural, LEVEL_TEXT } = window.IntroShared;

  const DEVICE_KEY = "intro-game-device-v1";
  const NAME_KEY = "intro-game-name-v1";
  const POLL_MS = 3000;
  const POLL_HIDDEN_MS = 8000;

  const cards = {
    loading: document.getElementById("card-loading"),
    waiting: document.getElementById("card-waiting"),
    play: document.getElementById("card-play"),
    sent: document.getElementById("card-sent"),
    closed: document.getElementById("card-closed"),
    result: document.getElementById("card-result"),
  };

  const els = {
    form: document.getElementById("play-form"),
    name: document.getElementById("play-name"),
    value: document.getElementById("play-value"),
    error: document.getElementById("play-error"),
    sentValue: document.getElementById("sent-value"),
    sentName: document.getElementById("sent-name"),
    sentChange: document.getElementById("sent-change"),
    closedLine: document.getElementById("closed-line"),
    resultHeadline: document.getElementById("result-headline"),
    rValue: document.getElementById("r-value"),
    rTarget: document.getElementById("r-target"),
    rMean: document.getElementById("r-mean"),
    rDistance: document.getElementById("r-distance"),
    rLevel: document.getElementById("r-level"),
    rWinners: document.getElementById("r-winners"),
  };

  const token = loadDeviceToken();
  let snapshot = null;   // last /me payload
  let editing = false;   // student pressed "change" and is typing
  let submitting = false;
  let pollTimer = null;

  // --- Storage --------------------------------------------------------------

  function randomToken() {
    const bytes = new Uint8Array(16);
    (window.crypto || window.msCrypto).getRandomValues(bytes);
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  function loadDeviceToken() {
    try {
      let value = window.localStorage.getItem(DEVICE_KEY);
      if (!value || !/^[A-Za-z0-9_-]{16,64}$/.test(value)) {
        value = randomToken();
        window.localStorage.setItem(DEVICE_KEY, value);
      }
      return value;
    } catch (_) {
      return randomToken(); // private mode: one token per page load
    }
  }

  function loadName() {
    try { return window.localStorage.getItem(NAME_KEY) || ""; } catch (_) { return ""; }
  }

  function saveName(name) {
    try { window.localStorage.setItem(NAME_KEY, name); } catch (_) { /* ignore */ }
  }

  // --- Rendering ------------------------------------------------------------

  function show(name) {
    Object.entries(cards).forEach(([key, el]) => { el.hidden = key !== name; });
  }

  function render() {
    const game = snapshot && snapshot.game;
    const entry = snapshot && snapshot.entry;
    if (!game) return show("waiting");
    if (game.status === "open") {
      if (entry && !editing) {
        els.sentValue.textContent = fmtNum(entry.value, 2);
        els.sentName.textContent = entry.name;
        return show("sent");
      }
      if (!cards.play.hidden) return; // keep what the student is typing
      prefillForm(entry);
      return show("play");
    }
    editing = false;
    if (game.status === "revealed" && snapshot.result) return renderResult(snapshot.result, entry);
    els.closedLine.textContent = entry
      ? `Вашето число: ${fmtNum(entry.value, 2)}.`
      : "Не сте изпратили отговор този път.";
    return show("closed");
  }

  function prefillForm(entry) {
    els.name.value = entry ? entry.name : (els.name.value || loadName());
    els.value.value = entry ? fmtNum(entry.value, 2) : els.value.value;
    els.error.hidden = true;
  }

  function renderResult(result, entry) {
    const winners = (result.winners || []).map((w) => `${w.name} (${fmtNum(w.value, 2)})`);
    els.rTarget.textContent = fmtNum(result.target, 1);
    els.rMean.textContent = fmtNum(result.mean, 1);
    if (result.value === null || result.value === undefined || !entry) {
      els.resultHeadline.textContent = "Не сте участвали.";
      els.resultHeadline.classList.remove("win");
      els.rValue.textContent = "—";
      els.rDistance.textContent = "—";
      els.rLevel.textContent = "";
    } else {
      els.resultHeadline.textContent = result.winner
        ? "Вие печелите!"
        : `Място ${result.rank} от ${result.count}`;
      els.resultHeadline.classList.toggle("win", Boolean(result.winner));
      els.rValue.textContent = fmtNum(result.value, 2);
      els.rDistance.textContent = fmtNum(result.distance, 1);
      els.rLevel.textContent = LEVEL_TEXT[result.level] || "";
    }
    els.rWinners.textContent = winners.length
      ? `${winners.length === 1 ? "Победител" : "Победители"}: ${winners.join(", ")} · ${plural(result.count, "отговор", "отговора")}`
      : "";
    show("result");
  }

  // --- Network --------------------------------------------------------------

  async function refresh() {
    try {
      snapshot = await publicApi(`/api/game/current/me?client_token=${encodeURIComponent(token)}`);
      render();
    } catch (exc) {
      if (!snapshot) {
        cards.loading.querySelector("p").textContent = "Няма връзка със сървъра. Опитваме пак…";
        show("loading");
      }
    }
  }

  function schedule() {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(async () => {
      await refresh();
      schedule();
    }, document.hidden ? POLL_HIDDEN_MS : POLL_MS);
  }

  function parseValue(text) {
    const cleaned = String(text || "").trim().replace(",", ".");
    if (!/^\d{1,3}(\.\d+)?$/.test(cleaned)) return null;
    const value = Number(cleaned);
    return value >= 0 && value <= 100 ? value : null;
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (submitting) return;
    const name = els.name.value.trim();
    const value = parseValue(els.value.value);
    if (!name) return showError("Въведете име.", els.name);
    if (value === null) return showError("Въведете число от 0 до 100.", els.value);
    submitting = true;
    els.error.hidden = true;
    try {
      const payload = await publicApi("/api/game/current/entry", {
        method: "POST",
        body: { client_token: token, name, value },
      });
      saveName(name);
      editing = false;
      snapshot = { ...(snapshot || {}), game: payload.game, entry: payload.entry };
      els.value.blur();
      render();
    } catch (exc) {
      showError(exc.message || "Не успях да изпратя отговора. Опитайте пак.");
      refresh();
    } finally {
      submitting = false;
    }
  }

  function showError(message, focusEl) {
    els.error.textContent = message;
    els.error.hidden = false;
    if (focusEl) focusEl.focus();
  }

  function onChange() {
    editing = true;
    prefillForm(snapshot && snapshot.entry);
    show("play");
    els.value.focus();
    els.value.select();
  }

  els.form.addEventListener("submit", onSubmit);
  els.sentChange.addEventListener("click", onChange);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
    schedule();
  });

  refresh().then(schedule);
})();
