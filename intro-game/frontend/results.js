(function () {
  const { publicApi, fmtNum, plural, STATUS_LABELS } = window.IntroShared;

  const params = new URLSearchParams(window.location.search);
  const EMBED = params.get("embed") === "1";
  const GAME = (params.get("game") || "").trim().toUpperCase();
  const MAX_STEP = 6;
  const POLL_MS = 2000;

  // Geometry shared with the deck: 128px margins, a 0–100 ruler 1664px wide
  // (img/ruler-*.svg in the slides puts value v at 129 + 16.62·v).
  const M = 128;
  const UNIT = 16.62;
  const BASE_Y = 892;      // ruler baseline; ticks hang below it
  const CHART_TOP = 452;   // highest point a dot may reach
  const LABEL_Y = CHART_TOP - 44;
  const x = (v) => M + 1 + UNIT * v;

  const LEVEL_SUB = {
    k0: "над 42",
    k1: "около 33",
    k2: "около 22",
    k3: "около 15",
    k4: "от 1 до 12",
    kinf: "0 или 1",
  };
  const RUNG_MARK = { k0: "0", k1: "1", k2: "2", k3: "3", k4: "4+", kinf: "∞" };

  const els = {
    stage: document.getElementById("stage"),
    headline: document.getElementById("headline"),
    note: document.getElementById("note"),
    tiles: document.getElementById("tiles"),
    chart: document.getElementById("chart"),
    status: document.getElementById("status"),
    keys: document.getElementById("keys"),
  };

  let step = clampStep(Number(params.get("step") || 0));
  let data = null;
  let pollTimer = null;

  if (EMBED) document.body.classList.add("embed");

  // ---- Layout ---------------------------------------------------------------

  function fit() {
    const s = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
    const dx = (window.innerWidth - 1920 * s) / 2;
    const dy = (window.innerHeight - 1080 * s) / 2;
    els.stage.style.transform = `translate(${dx}px, ${dy}px) scale(${s})`;
  }

  function clampStep(n) {
    return Math.max(0, Math.min(MAX_STEP, Number.isFinite(n) ? Math.round(n) : 0));
  }

  // ---- SVG helpers ------------------------------------------------------------

  const NS = "http://www.w3.org/2000/svg";

  function svg(tag, attrs, parent, text) {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs || {}).forEach(([k, v]) => node.setAttribute(k, v));
    if (text !== undefined) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }

  function drawRuler(root) {
    const g = svg("g", {}, root);
    let d = `M${M} ${BASE_Y}H${M + 1664}`;
    for (let i = 0; i <= 100; i += 1) {
      const len = i % 10 === 0 ? 18 : i % 5 === 0 ? 12 : 6;
      d += `M${x(i).toFixed(2)} ${BASE_Y}V${BASE_Y + len}`;
    }
    svg("path", { d, class: "axis-line" }, g);
    for (let i = 0; i <= 100; i += 10) {
      svg("text", { x: x(i), y: BASE_Y + 50, "text-anchor": "middle", class: "axis-label" }, g, String(i));
    }
  }

  // Wilkinson dot plot: sweep the sorted values, start a new stack whenever a
  // value is more than one dot-width past the stack's first value, then keep
  // neighbouring stacks at least one dot-width apart.
  function stacksFor(values, dotPx) {
    const width = dotPx / UNIT;
    const stacks = [];
    let cur = null;
    values.forEach((v) => {
      if (cur && v - cur.start <= width) cur.values.push(v);
      else { cur = { start: v, values: [v] }; stacks.push(cur); }
    });
    let prev = -Infinity;
    stacks.forEach((s) => {
      s.center = Math.max((s.values[0] + s.values[s.values.length - 1]) / 2, prev + width);
      prev = s.center;
    });
    return stacks;
  }

  function layoutDots(values) {
    const room = BASE_Y - 8 - CHART_TOP;
    for (const dot of [30, 26, 22, 18, 15, 12, 10]) {
      const stacks = stacksFor(values, dot);
      const tallest = Math.max(...stacks.map((s) => s.values.length));
      if (tallest * (dot + 4) <= room) return { stacks, dot, pitch: dot + 4 };
    }
    const stacks = stacksFor(values, 10);
    const tallest = Math.max(...stacks.map((s) => s.values.length));
    return { stacks, dot: 10, pitch: room / tallest };
  }

  // ---- Build (once per data load) -------------------------------------------------

  function build() {
    const root = els.chart;
    root.innerHTML = "";
    drawRuler(root);
    els.tiles.innerHTML = "";
    if (!data || !data.ready || !data.count) return;

    const { stacks, dot, pitch } = layoutDots(data.values);
    const r = Math.max(3, Math.min(dot, pitch - 2) / 2);
    const winnerValues = data.winners.map((w) => w.value);
    const dotsG = svg("g", { id: "dots" }, root);
    let index = 0;
    stacks.forEach((s) => {
      s.values.forEach((v, j) => {
        const cy = BASE_Y - 8 - pitch * j - pitch / 2;
        const k = winnerValues.indexOf(v);
        const isWinner = k !== -1;
        if (isWinner) winnerValues[k] = null; // one dot per winner
        const c = svg("circle", {
          cx: x(s.center).toFixed(1), cy: cy.toFixed(1), r: r.toFixed(1),
          class: `dot${isWinner ? " win-dot" : ""}`,
          style: `transition-delay: ${Math.min(index * 6, 900)}ms, 0ms`,
        }, dotsG);
        svg("title", {}, c, fmtNum(v, 2));
        if (isWinner) {
          svg("circle", { cx: x(s.center).toFixed(1), cy: cy.toFixed(1), r: (r + 7).toFixed(1), class: "ring" }, root);
        }
        index += 1;
      });
    });

    // Mean, two thirds, and the arrow between them.
    const xm = x(data.mean);
    const xt = x(data.target);
    const meanG = svg("g", { class: "fade", id: "mean" }, root);
    svg("line", { x1: xm, x2: xm, y1: CHART_TOP - 20, y2: BASE_Y, class: "mean-line" }, meanG);
    const meanLabel = svg("g", { class: "fade", id: "mean-label" }, root);
    const meanText = svg("text", { x: xm + 14, y: LABEL_Y, class: "line-label" }, meanLabel,
      `средното ${fmtNum(data.mean, 1)}`);

    const targetG = svg("g", { class: "fade", id: "target" }, root);
    svg("line", { x1: xt, x2: xt, y1: CHART_TOP - 20, y2: BASE_Y, class: "target-line" }, targetG);
    const targetLabel = svg("g", { class: "fade", id: "target-label" }, root);
    const targetText = svg("text", {
      x: xt - 14, y: LABEL_Y, "text-anchor": "end", class: "line-label gold",
    }, targetLabel, `2/3 = ${fmtNum(data.target, 1)}`);
    const wt = textWidth(targetText);
    const wm = textWidth(meanText);
    const tight = xt - 14 - wt < M - 40;
    if (tight) {
      targetText.setAttribute("x", xt + 14);
      targetText.setAttribute("text-anchor", "start");
      meanText.setAttribute("x", Math.max(xm + 14, xt + 14 + wt + 32));
    }
    if (Number(meanText.getAttribute("x")) + wm > 1920 - M + 40) {
      meanText.setAttribute("x", xm - 14);
      meanText.setAttribute("text-anchor", "end");
    }
    const arrowG = svg("g", { class: "fade", id: "arrow" }, root);
    if (!tight && xm - xt > 60) {
      const ay = CHART_TOP - 6;
      svg("path", { d: `M${xm - 6} ${ay}H${xt + 16}`, class: "arrow" }, arrowG);
      svg("path", { d: `M${xt + 4} ${ay}l16 -9v18z`, class: "arrow-head" }, arrowG);
    }

    // "How many moves ahead": rungs at 50·(2/3)^k and at 0.
    const rungG = svg("g", { class: "fade", id: "rungs" }, root);
    data.levels.forEach((lv) => {
      const xr = x(lv.rung);
      const isTarget = lv.key === data.target_level;
      svg("line", { x1: xr, x2: xr, y1: CHART_TOP - 30, y2: BASE_Y, class: "rung-line" }, rungG);
      svg("text", {
        x: xr, y: LABEL_Y, "text-anchor": "middle",
        class: `rung-label${isTarget ? " gold" : ""}`,
      }, rungG, RUNG_MARK[lv.key]);
    });

    buildTiles();
  }

  function textWidth(node) {
    try { return node.getComputedTextLength(); } catch (_) { return node.textContent.length * 16; }
  }

  // A single winner's name shrinks to fit its tile (two-word names are common),
  // and wraps only as a last resort. Needs layout, so it reruns once fonts load.
  function fitNames() {
    els.tiles.querySelectorAll(".t-value.name").forEach((el) => {
      if (!el.clientWidth) return;
      let size = 88;
      el.style.whiteSpace = "nowrap";
      el.style.fontSize = `${size}px`;
      while (el.scrollWidth > el.clientWidth && size > 48) {
        size -= 4;
        el.style.fontSize = `${size}px`;
      }
      if (el.scrollWidth > el.clientWidth) el.style.whiteSpace = "normal";
    });
  }

  function tile({ label, value, sub, gold, name, on }) {
    return `<div class="tile${gold ? " gold" : ""}" data-on="${on}">
      <div class="t-label">${label}</div>
      <div class="t-value${name ? " name" : ""}">${value}</div>
      ${sub ? `<div class="t-sub">${sub}</div>` : ""}
    </div>`;
  }

  function esc(value) {
    return window.IntroShared.escapeHtml(value);
  }

  function buildTiles() {
    const w = data.winners;
    const single = w.length === 1;
    const main = [
      { label: "Отговори", value: String(data.count), on: 1 },
      { label: "Средното", value: fmtNum(data.mean, 1), on: 3 },
      { label: "2/3 от средното", value: fmtNum(data.target, 1), gold: true, on: 4 },
      {
        label: single ? "Победител" : "Победители",
        value: esc(single ? w[0].name : `${w.length} души`),
        sub: esc(single
          ? `с числото ${fmtNum(w[0].value, 2)}`
          : w.slice(0, 3).map((p) => `${p.name} (${fmtNum(p.value, 2)})`).join(", ")
            + (w.length > 3 ? ` и още ${w.length - 3}` : "")),
        gold: true, name: true, on: 5,
      },
    ];
    const levels = data.levels.map((lv) => ({
      label: esc(lv.label),
      value: String(lv.count),
      sub: LEVEL_SUB[lv.key] + (lv.key === data.target_level ? " · тук е целта" : ""),
      gold: lv.key === data.target_level,
      on: 6,
    }));
    els.tiles.innerHTML = `
      <div class="s-tiles" id="tiles-main">${main.map(tile).join("")}</div>
      <div class="s-tiles levels" id="tiles-levels">${levels.map(tile).join("")}</div>`;
    fitNames();
  }

  // ---- Apply step (cheap; runs on every key press) ------------------------------

  function apply() {
    const ready = Boolean(data && data.ready);
    const hasData = ready && data.count > 0;
    const s = hasData ? step : 0;

    let headline = "Да видим какво решихте.";
    let note = "";
    if (!data) {
      note = "Свързване със сървъра…";
    } else if (!data.game) {
      headline = "Няма игра.";
      note = "Създайте я от админ страницата.";
    } else if (!ready) {
      note = step > 0
        ? `Играта е още отворена: затворете я от админ страницата. ${plural(data.count, "отговор", "отговора")} до момента.`
        : `${plural(data.count, "отговор", "отговора")} до момента.`;
      if (step > 0) headline = "Играта е още отворена.";
    } else if (!data.count) {
      headline = "Никой не отговори.";
    }
    els.headline.textContent = headline;
    els.headline.style.opacity = s === 0 ? "1" : "0";
    els.note.textContent = note;
    els.note.style.opacity = s === 0 && note ? "1" : "0";

    const main = document.getElementById("tiles-main");
    const levels = document.getElementById("tiles-levels");
    if (main && levels) {
      main.style.display = s >= 6 ? "none" : "";
      levels.style.display = s >= 6 ? "" : "none";
      els.tiles.querySelectorAll(".tile").forEach((t) => {
        t.classList.toggle("on", s >= Number(t.dataset.on));
      });
    }
    const on = (id, cond) => {
      const node = document.getElementById(id);
      if (node) node.classList.toggle("on", cond);
    };
    const dots = document.getElementById("dots");
    if (dots) dots.classList.toggle("dots-on", s >= 2);
    on("mean", s >= 3);
    on("mean-label", s >= 3 && s < 6);
    on("target", s >= 4);
    on("target-label", s >= 4 && s < 6);
    on("arrow", s >= 4 && s < 6);
    on("rungs", s >= 6);
    els.chart.querySelectorAll(".win-dot").forEach((c) => c.classList.toggle("winner", s >= 5));
    els.chart.querySelectorAll(".ring").forEach((c) => { c.style.opacity = s >= 5 ? "1" : "0"; });

    if (data && data.game) {
      els.status.textContent = `Игра ${data.game.code} · ${STATUS_LABELS[data.game.status] || data.game.status} · ${plural(data.game.count, "отговор", "отговора")} · стъпка ${step}/${MAX_STEP}`;
    }
  }

  function setStep(n) {
    step = clampStep(n);
    apply();
  }

  // ---- Data -----------------------------------------------------------------

  async function load() {
    clearTimeout(pollTimer);
    const path = GAME ? `/api/game/${encodeURIComponent(GAME)}/results` : "/api/game/current/results";
    try {
      const next = await publicApi(path);
      const changed = !data || JSON.stringify(next) !== JSON.stringify(data);
      data = next;
      if (changed) build();
      apply();
      // Tell the deck we have something to show, so it swaps its offline slide
      // for this page. No game, or a closed game nobody answered: stay silent
      // and the deck keeps its hand-raising ladder.
      const showable = data.game && !(data.ready && !data.count);
      if (EMBED && showable && window.parent !== window) {
        window.parent.postMessage({ source: "intro-results", type: "ready" }, "*");
      }
    } catch (exc) {
      if (!data) apply();
    }
    if (!data || !data.ready) pollTimer = setTimeout(load, POLL_MS);
  }

  // ---- Input ------------------------------------------------------------------

  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen();
  }

  window.addEventListener("message", (event) => {
    const msg = event.data;
    if (!msg || msg.source !== "intro-deck") return;
    if (msg.type === "step") setStep(msg.step);
    if (msg.type === "refresh") load();
  });

  if (!EMBED) {
    document.addEventListener("keydown", (event) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      switch (event.key) {
        case "ArrowRight": case "ArrowDown": case "PageDown": case " ": case "Enter":
          setStep(step + 1); break;
        case "ArrowLeft": case "ArrowUp": case "PageUp": case "Backspace":
          setStep(step - 1); break;
        case "Home": setStep(0); break;
        case "End": setStep(MAX_STEP); break;
        case "f": case "F": toggleFullscreen(); break;
        case "r": case "R": load(); break;
        default: return;
      }
      event.preventDefault();
    });
    document.addEventListener("click", () => setStep(step + 1));
    setTimeout(() => { els.keys.style.opacity = "0"; }, 6000);
  }

  window.addEventListener("resize", fit);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitNames);
  fit();
  apply();
  load();
})();
