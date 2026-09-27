#!/usr/bin/env python3
"""Intro game backend: "Две трети от средното" (guess 2/3 of the average).

The classroom game from the first-year intro lecture (../../vavedenie.qmd).
Students open the page from the QR code on the slides, enter a name and a
number from 0 to 100; the instructor closes the game and the projection
page reveals the results step by step.

Mirrors the sibling course apps (session-quiz, labor-auction-sim): stdlib
HTTP server, SQLite in WAL mode, vanilla JS frontend served from
``../frontend`` at the same origin. No third-party dependencies.
"""

import argparse
import base64
import csv
import hmac
import io
import json
import math
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GAME_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # ambiguous chars removed
GAME_CODE_LEN = 6
DEFAULT_TITLE = "Две трети от средното"
TITLE_MAX = 80
NAME_MAX = 40
FACTOR = 2 / 3
VALUE_MIN = 0.0
VALUE_MAX = 100.0
MAX_BODY_BYTES = 64 * 1024
STATUSES = ("open", "closed", "revealed")

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS game (
  id          TEXT PRIMARY KEY,
  code        TEXT UNIQUE NOT NULL,
  title       TEXT NOT NULL,
  status      TEXT NOT NULL CHECK(status IN ('open','closed','revealed')),
  created_at  INTEGER NOT NULL,
  closed_at   INTEGER,
  revealed_at INTEGER
);

CREATE TABLE IF NOT EXISTS entry (
  id           TEXT PRIMARY KEY,
  game_id      TEXT NOT NULL REFERENCES game(id) ON DELETE CASCADE,
  client_token TEXT NOT NULL,
  name         TEXT NOT NULL,
  value        REAL NOT NULL,
  submitted_at INTEGER NOT NULL,
  updated_at   INTEGER NOT NULL,
  hidden       INTEGER NOT NULL DEFAULT 0,
  UNIQUE (game_id, client_token)
);

CREATE INDEX IF NOT EXISTS idx_entry_game ON entry (game_id);
"""


def connect(db_path):
    conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def init_schema(conn):
    with conn:
        conn.executescript(SCHEMA)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def now_ms():
    return int(time.time() * 1000)


def new_id():
    return uuid.uuid4().hex


def json_dumps(value):
    return json.dumps(value, ensure_ascii=False)


def parse_json(body):
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("Невалиден JSON.")
    if not isinstance(payload, dict):
        raise ValueError("Очаква се JSON обект.")
    return payload


def make_game_code():
    return "".join(secrets.choice(GAME_CODE_CHARS) for _ in range(GAME_CODE_LEN))


def normalize_name(value):
    if not isinstance(value, str):
        raise ValueError("Въведете име.")
    cleaned = " ".join(_CONTROL_RE.sub(" ", value).split())
    if not cleaned:
        raise ValueError("Въведете име.")
    if len(cleaned) > NAME_MAX:
        raise ValueError(f"Името може да е най-много {NAME_MAX} знака.")
    return cleaned


def normalize_title(value):
    if value is None:
        return DEFAULT_TITLE
    cleaned = " ".join(_CONTROL_RE.sub(" ", str(value)).split())
    if not cleaned:
        return DEFAULT_TITLE
    if len(cleaned) > TITLE_MAX:
        raise ValueError(f"Заглавието може да е най-много {TITLE_MAX} знака.")
    return cleaned


def parse_value(raw):
    """Number from 0 to 100, whole or decimal; accepts a decimal comma."""
    if isinstance(raw, bool) or raw is None:
        raise ValueError("Въведете число от 0 до 100.")
    if isinstance(raw, (int, float)):
        try:
            value = float(raw)
        except OverflowError:
            raise ValueError("Числото трябва да е от 0 до 100.")
    else:
        text = str(raw).strip().replace(",", ".")
        if not re.match(r"^\d{1,3}(\.\d+)?$", text):
            raise ValueError("Въведете число от 0 до 100.")
        value = float(text)
    if not math.isfinite(value) or value < VALUE_MIN or value > VALUE_MAX:
        raise ValueError("Числото трябва да е от 0 до 100.")
    return round(value, 2)


def normalize_token(value):
    token = str(value or "").strip()
    if not _TOKEN_RE.match(token):
        raise ValueError("Невалиден ключ на устройството. Презаредете страницата.")
    return token


# ---------------------------------------------------------------------------
# Game logic: 2/3 of the average and "how many moves ahead"
# ---------------------------------------------------------------------------


def level_bands():
    """Level-k bands: rung k is 50·(2/3)^k (50, 33, 22, 15, 10), and each band
    ends roughly halfway between two rungs, at whole numbers the slides can
    name: over 42 = 0 moves (no thought about the others), 28–42 = 1 move,
    19–28 = 2, 12–19 = 3, 1–12 = 4+, and 0–1 = "all the way", the textbook
    equilibrium. An edge value belongs to the band below it (42 is 1 move).
    """
    rungs = [50 * FACTOR ** k for k in range(5)]
    cuts = [42.0, 28.0, 19.0, 12.0]
    return [
        {"key": "k0", "moves": 0, "label": "0 хода", "lo": cuts[0], "hi": 100.0, "rung": rungs[0]},
        {"key": "k1", "moves": 1, "label": "1 ход", "lo": cuts[1], "hi": cuts[0], "rung": rungs[1]},
        {"key": "k2", "moves": 2, "label": "2 хода", "lo": cuts[2], "hi": cuts[1], "rung": rungs[2]},
        {"key": "k3", "moves": 3, "label": "3 хода", "lo": cuts[3], "hi": cuts[2], "rung": rungs[3]},
        {"key": "k4", "moves": 4, "label": "4+ хода", "lo": 1.0, "hi": cuts[3], "rung": rungs[4]},
        {"key": "kinf", "moves": None, "label": "докрай", "lo": 0.0, "hi": 1.0, "rung": 0.0},
    ]


def classify(value, bands=None):
    for band in bands or level_bands():
        if value > band["lo"] or band["key"] == "kinf":
            return band["key"]
    return "kinf"


def compute_results(entries):
    """entries: visible rows with name/value. Returns the public result dict."""
    n = len(entries)
    bands = level_bands()
    if n == 0:
        return {
            "count": 0, "mean": None, "target": None, "winners": [],
            "winner_distance": None, "values": [],
            "levels": [{**b, "count": 0} for b in bands], "target_level": None,
        }
    values = [e["value"] for e in entries]
    mean = sum(values) / n
    target = FACTOR * mean
    distances = [abs(v - target) for v in values]
    best = min(distances)
    winners = [
        {"name": e["name"], "value": e["value"]}
        for e, d in zip(entries, distances)
        if d - best <= 1e-9
    ]
    counts = {b["key"]: 0 for b in bands}
    for v in values:
        counts[classify(v, bands)] += 1
    return {
        "count": n,
        "mean": round(mean, 4),
        "target": round(target, 4),
        "winners": winners,
        "winner_distance": round(best, 4),
        "values": sorted(values),
        "levels": [{**b, "count": counts[b["key"]]} for b in bands],
        "target_level": classify(target, bands),
    }


def exact_target(values):
    return FACTOR * sum(values) / len(values)


def rank_of(value, values, target):
    """1 = closest to the exact target; ties share a rank (same rule as winners)."""
    d = abs(value - target)
    return 1 + sum(1 for v in values if abs(v - target) < d - 1e-9)


def personal_result(entries, token):
    """Rank and distance for one device's entry (1 = closest)."""
    results = compute_results(entries)
    mine = next((e for e in entries if e["client_token"] == token), None)
    if not mine or results["count"] == 0:
        return None
    values = [e["value"] for e in entries]
    target = exact_target(values)
    my_d = abs(mine["value"] - target)
    rank = rank_of(mine["value"], values, target)
    return {
        "value": mine["value"],
        "mean": results["mean"],
        "target": results["target"],
        "distance": round(my_d, 4),
        "rank": rank,
        "count": results["count"],
        "winner": rank == 1,
        "level": classify(mine["value"]),
        "winners": results["winners"],
    }


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------


def current_game(conn):
    return conn.execute(
        "SELECT * FROM game ORDER BY created_at DESC, rowid DESC LIMIT 1"
    ).fetchone()


def game_by_code(conn, code):
    return conn.execute(
        "SELECT * FROM game WHERE code = ?", (str(code or "").upper(),)
    ).fetchone()


def visible_entries(conn, game_id):
    return conn.execute(
        """SELECT * FROM entry WHERE game_id = ? AND hidden = 0
            ORDER BY submitted_at""",
        (game_id,),
    ).fetchall()


def count_visible(conn, game_id):
    return conn.execute(
        "SELECT COUNT(*) AS n FROM entry WHERE game_id = ? AND hidden = 0",
        (game_id,),
    ).fetchone()["n"]


def game_public(conn, row, include_title=False):
    """Game summary. The title is the instructor's own label, so only the
    admin endpoints include it."""
    if not row:
        return None
    game = {
        "code": row["code"],
        "status": row["status"],
        "created_at": row["created_at"],
        "closed_at": row["closed_at"],
        "revealed_at": row["revealed_at"],
        "count": count_visible(conn, row["id"]),
    }
    if include_title:
        game["title"] = row["title"]
    return game


def entry_public(row):
    return {
        "name": row["name"],
        "value": row["value"],
        "submitted_at": row["submitted_at"],
        "updated_at": row["updated_at"],
    }


def results_payload(conn, row):
    """Public results. While the game is open only the count is exposed, so
    nobody can read the running average and aim at it."""
    game = game_public(conn, row)
    if row["status"] == "open":
        return {"game": game, "ready": False, "count": game["count"]}
    results = compute_results(visible_entries(conn, row["id"]))
    return {"game": game, "ready": True, **results}


def export_csv(conn, row):
    entries = conn.execute(
        "SELECT * FROM entry WHERE game_id = ? ORDER BY submitted_at", (row["id"],)
    ).fetchall()
    values = [e["value"] for e in entries if not e["hidden"]]
    target = exact_target(values) if values else None
    out = io.StringIO()
    out.write("﻿")  # BOM so Excel reads the Cyrillic names as UTF-8
    writer = csv.writer(out)
    writer.writerow([
        "game", "name", "value", "distance", "rank", "winner", "level",
        "hidden", "submitted_at", "updated_at",
    ])
    for e in entries:
        if e["hidden"] or target is None:
            distance, rank, winner = "", "", ""
        else:
            distance = round(abs(e["value"] - target), 4)
            rank = rank_of(e["value"], values, target)
            winner = int(rank == 1)
        # A name typed as "=..." must stay text, not become a spreadsheet formula.
        name = e["name"]
        if name[:1] in ("=", "+", "-", "@"):
            name = "'" + name
        writer.writerow([
            row["code"], name, e["value"], distance, rank, winner,
            classify(e["value"]), int(e["hidden"]),
            _fmt_ts(e["submitted_at"]), _fmt_ts(e["updated_at"]),
        ])
    return out.getvalue()


def _fmt_ts(epoch_ms):
    # Server local time: the instructor's laptop clock, same as the class saw.
    if not epoch_ms:
        return ""
    return datetime.fromtimestamp(epoch_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


_STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
}

_PRETTY_PATHS = {"": "index.html", "/": "index.html", "/admin": "admin.html",
                 "/results": "results.html"}


def _content_type_for(filename):
    for ext, ctype in _STATIC_TYPES.items():
        if filename.lower().endswith(ext):
            return ctype
    return "application/octet-stream"


class Handler(BaseHTTPRequestHandler):
    server_version = "IntroGame/1.0"

    # -- Framework helpers --------------------------------------------------

    def _send_bytes(self, status, data, content_type, extra_headers=None,
                    cache="no-store"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self._send_cors()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _send_json(self, status, payload):
        self._send_bytes(status, json_dumps(payload).encode("utf-8"),
                         "application/json; charset=utf-8")

    def _send_error(self, status, message):
        self._send_json(status, {"error": message})

    def _send_cors(self):
        origin = self.server.allowed_origin or "*"
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type, X-Admin-Key, X-Admin-Key-B64")
        self.send_header("Vary", "Origin")

    def log_message(self, fmt, *args):
        return

    def _parse_path(self):
        parsed = urlparse(self.path)
        return parsed.path, parse_qs(parsed.query)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            raise ValueError("Заявката е твърде голяма.")
        return parse_json(self.rfile.read(length) if length > 0 else b"")

    def _read_admin_key(self):
        key_b64 = self.headers.get("X-Admin-Key-B64", "").strip()
        if key_b64:
            try:
                padding = "=" * (-len(key_b64) % 4)
                decoded = base64.b64decode(key_b64 + padding, validate=True)
                return decoded.decode("utf-8").strip()
            except (ValueError, UnicodeDecodeError):
                return ""
        return self.headers.get("X-Admin-Key", "").strip()

    def _require_admin(self):
        expected = self.server.admin_key
        if not expected:
            return True  # dev/open mode
        key = self._read_admin_key()
        if key and hmac.compare_digest(key.encode("utf-8"), expected.encode("utf-8")):
            return True
        self._send_error(401, "Нужен е валиден админ ключ.")
        return False

    def _conn(self):
        return self.server.get_conn()

    def _try_serve_static(self, path):
        if not self.server.frontend_dir:
            return False
        target = _PRETTY_PATHS.get(path, path.lstrip("/"))
        if ".." in target.split("/"):
            return False
        root = self.server.frontend_dir.resolve()
        candidate = (root / target).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return False
        if not candidate.is_file():
            return False
        try:
            data = candidate.read_bytes()
        except OSError:
            return False
        self._send_bytes(200, data, _content_type_for(candidate.name), cache="no-cache")
        return True

    def _dispatch(self, routes):
        path, qs = self._parse_path()
        try:
            for method_path, handler in routes:
                m = re.match(method_path, path)
                if m:
                    return handler(qs, *m.groups())
            if self.command in ("GET", "HEAD") and not path.startswith("/api/"):
                if self._try_serve_static(path):
                    return None
            return self._send_error(404, "Не е намерено.")
        except ValueError as exc:
            return self._send_error(400, str(exc))
        except Exception as exc:  # pragma: no cover - last-resort guard
            return self._send_error(500, f"Грешка в сървъра: {exc}")

    # -- Routing ------------------------------------------------------------

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_GET(self):
        return self._dispatch([
            (r"^/api/health$", lambda qs: self._send_json(
                200, {"ok": True, "admin_key": bool(self.server.admin_key)})),
            (r"^/api/game/current$", self._handle_current),
            (r"^/api/game/current/me$", self._handle_me),
            (r"^/api/game/current/results$", self._handle_results),
            (r"^/api/game/([A-Za-z0-9]+)/results$", self._handle_results),
            (r"^/api/admin/games$", self._admin(self._handle_admin_list)),
            (r"^/api/admin/games/([A-Za-z0-9]+)$", self._admin(self._handle_admin_game)),
            (r"^/api/admin/games/([A-Za-z0-9]+)/csv$", self._admin(self._handle_admin_csv)),
        ])

    def do_HEAD(self):
        return self.do_GET()

    def do_POST(self):
        return self._dispatch([
            (r"^/api/game/current/entry$", self._handle_entry),
            (r"^/api/admin/games$", self._admin(self._handle_admin_create)),
            (r"^/api/admin/games/([A-Za-z0-9]+)/status$", self._admin(self._handle_admin_status)),
            (r"^/api/admin/games/([A-Za-z0-9]+)/entries/([a-f0-9]+)$",
             self._admin(self._handle_admin_entry)),
        ])

    def do_DELETE(self):
        return self._dispatch([
            (r"^/api/admin/games/([A-Za-z0-9]+)$", self._admin(self._handle_admin_delete)),
        ])

    def _admin(self, handler):
        def wrapped(qs, *args):
            if not self._require_admin():
                return None
            return handler(qs, *args)
        return wrapped

    # -- Public: students and projection -----------------------------------

    def _handle_current(self, qs):
        conn = self._conn()
        return self._send_json(200, {"game": game_public(conn, current_game(conn))})

    def _handle_entry(self, qs):
        payload = self._read_json()
        token = normalize_token(payload.get("client_token"))
        name = normalize_name(payload.get("name"))
        value = parse_value(payload.get("value"))
        conn = self._conn()
        # Same lock as close/create/delete, so an answer cannot slip into a
        # game that was closed between the check and the insert.
        with self.server.write_lock:
            row = current_game(conn)
            if not row:
                raise ValueError("Играта още не е започнала.")
            if row["status"] != "open":
                raise ValueError("Играта е затворена. Отговори вече не се приемат.")
            ts = now_ms()
            with conn:
                conn.execute(
                    """INSERT INTO entry
                         (id, game_id, client_token, name, value, submitted_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT (game_id, client_token) DO UPDATE SET
                         name = excluded.name,
                         value = excluded.value,
                         updated_at = excluded.updated_at""",
                    (new_id(), row["id"], token, name, value, ts, ts),
                )
        entry = conn.execute(
            "SELECT * FROM entry WHERE game_id = ? AND client_token = ?",
            (row["id"], token),
        ).fetchone()
        return self._send_json(200, {
            "game": game_public(conn, row),
            "entry": entry_public(entry),
        })

    def _handle_me(self, qs):
        token = normalize_token((qs.get("client_token") or [""])[0])
        conn = self._conn()
        row = current_game(conn)
        if not row:
            return self._send_json(200, {"game": None, "entry": None, "result": None})
        entry = conn.execute(
            "SELECT * FROM entry WHERE game_id = ? AND client_token = ?",
            (row["id"], token),
        ).fetchone()
        result = None
        if row["status"] == "revealed":
            entries = visible_entries(conn, row["id"])
            result = personal_result(entries, token)
            if result is None:
                summary = compute_results(entries)
                result = {
                    "value": None, "mean": summary["mean"], "target": summary["target"],
                    "count": summary["count"], "winners": summary["winners"],
                }
        return self._send_json(200, {
            "game": game_public(conn, row),
            "entry": entry_public(entry) if entry else None,
            "result": result,
        })

    def _handle_results(self, qs, code=None):
        conn = self._conn()
        row = game_by_code(conn, code) if code else current_game(conn)
        if not row:
            if code:
                return self._send_error(404, "Няма такава игра.")
            return self._send_json(200, {"game": None, "ready": False, "count": 0})
        return self._send_json(200, results_payload(conn, row))

    # -- Admin ---------------------------------------------------------------

    def _handle_admin_list(self, qs):
        conn = self._conn()
        rows = conn.execute("SELECT * FROM game ORDER BY created_at DESC, rowid DESC").fetchall()
        return self._send_json(200, {"games": [game_public(conn, r, True) for r in rows]})

    def _handle_admin_create(self, qs):
        payload = self._read_json()
        title = normalize_title(payload.get("title"))
        conn = self._conn()
        with self.server.write_lock, conn:
            for _ in range(8):
                code = make_game_code()
                if not game_by_code(conn, code):
                    break
            else:
                raise ValueError("Не успях да създам код на играта. Опитайте пак.")
            ts = now_ms()
            # Only the newest game is "current": close anything still open.
            conn.execute(
                "UPDATE game SET status = 'closed', closed_at = ? WHERE status = 'open'",
                (ts,),
            )
            conn.execute(
                """INSERT INTO game (id, code, title, status, created_at)
                   VALUES (?, ?, ?, 'open', ?)""",
                (new_id(), code, title, ts),
            )
        return self._send_json(201, {"game": game_public(conn, game_by_code(conn, code), True)})

    def _admin_game_or_404(self, code):
        conn = self._conn()
        row = game_by_code(conn, code)
        if not row:
            self._send_error(404, "Няма такава игра.")
        return conn, row

    def _handle_admin_game(self, qs, code):
        conn, row = self._admin_game_or_404(code)
        if not row:
            return None
        entries = conn.execute(
            "SELECT * FROM entry WHERE game_id = ? ORDER BY submitted_at DESC",
            (row["id"],),
        ).fetchall()
        visible = [e for e in entries if not e["hidden"]]
        results = compute_results(visible)
        out = []
        for e in entries:
            item = {"id": e["id"], "hidden": bool(e["hidden"]), **entry_public(e)}
            if results["target"] is not None and not e["hidden"]:
                item["distance"] = round(abs(e["value"] - results["target"]), 4)
            out.append(item)
        latest = current_game(conn)
        return self._send_json(200, {
            "game": game_public(conn, row, True),
            "is_current": bool(latest and latest["id"] == row["id"]),
            "entries": out,
            "results": results,
        })

    def _handle_admin_status(self, qs, code):
        payload = self._read_json()
        status = str(payload.get("status") or "").strip()
        if status not in STATUSES:
            raise ValueError("status трябва да е open, closed или revealed.")
        conn, row = self._admin_game_or_404(code)
        if not row:
            return None
        latest = current_game(conn)
        if status == "open" and latest["id"] != row["id"]:
            raise ValueError("Само последната игра може да се отвори отново.")
        ts = now_ms()
        with self.server.write_lock, conn:
            if status == "open":
                conn.execute(
                    "UPDATE game SET status='open', closed_at=NULL, revealed_at=NULL WHERE id=?",
                    (row["id"],),
                )
            elif status == "closed":
                conn.execute(
                    """UPDATE game SET status='closed', revealed_at=NULL,
                              closed_at=COALESCE(closed_at, ?) WHERE id=?""",
                    (ts, row["id"]),
                )
            else:
                conn.execute(
                    """UPDATE game SET status='revealed', revealed_at=?,
                              closed_at=COALESCE(closed_at, ?) WHERE id=?""",
                    (ts, ts, row["id"]),
                )
        return self._send_json(200, {"game": game_public(conn, game_by_code(conn, code), True)})

    def _handle_admin_entry(self, qs, code, entry_id):
        payload = self._read_json()
        hidden = 1 if payload.get("hidden") else 0
        conn, row = self._admin_game_or_404(code)
        if not row:
            return None
        with conn:
            cur = conn.execute(
                "UPDATE entry SET hidden = ? WHERE id = ? AND game_id = ?",
                (hidden, entry_id, row["id"]),
            )
        if cur.rowcount == 0:
            return self._send_error(404, "Няма такъв отговор.")
        return self._send_json(200, {"ok": True, "hidden": bool(hidden)})

    def _handle_admin_csv(self, qs, code):
        conn, row = self._admin_game_or_404(code)
        if not row:
            return None
        day = datetime.fromtimestamp(row["created_at"] / 1000).strftime("%Y%m%d")
        filename = f"dve-treti-{row['code']}-{day}.csv"
        return self._send_bytes(
            200, export_csv(conn, row).encode("utf-8"), "text/csv; charset=utf-8",
            extra_headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    def _handle_admin_delete(self, qs, code):
        conn, row = self._admin_game_or_404(code)
        if not row:
            return None
        with self.server.write_lock, conn:
            conn.execute("DELETE FROM game WHERE id = ?", (row["id"],))
        return self._send_json(200, {"ok": True})


# ---------------------------------------------------------------------------
# Server wrapper
# ---------------------------------------------------------------------------


def resolve_db_path(root, cli_db):
    raw = cli_db if cli_db is not None else os.environ.get("INTRO_DB_PATH", "")
    text = str(raw or "").strip()
    if not text:
        return (root / "data" / "intro.db").resolve()
    if text.lower() == ":memory:" or "mode=memory" in text.lower():
        raise SystemExit("[intro] Refusing an in-memory database; use a file path.")
    path = Path(text).expanduser()
    return path if path.is_absolute() else (Path.cwd() / path).resolve()


class IntroServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, db_path, admin_key, allowed_origin, frontend_dir):
        super().__init__(address, handler)
        self.db_path = db_path
        self.admin_key = admin_key
        self.allowed_origin = allowed_origin
        self.frontend_dir = frontend_dir
        self.write_lock = threading.Lock()
        self._conn_lock = threading.Lock()
        self._thread_conns = {}

    def get_conn(self):
        ident = threading.get_ident()
        with self._conn_lock:
            conn = self._thread_conns.get(ident)
            if conn is None:
                conn = connect(self.db_path)
                self._thread_conns[ident] = conn
            return conn


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8004)
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    root = Path(__file__).parent.resolve()
    db_path = resolve_db_path(root, args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    admin_key = os.environ.get("INTRO_ADMIN_KEY", "").strip()
    allowed_origin = os.environ.get("INTRO_ALLOWED_ORIGIN", "").strip() or None
    frontend_env = os.environ.get("INTRO_FRONTEND_DIR", "").strip()
    if frontend_env:
        frontend_dir = Path(frontend_env)
    else:
        candidate = (root.parent / "frontend").resolve()
        frontend_dir = candidate if candidate.is_dir() else None

    init_conn = connect(str(db_path))
    try:
        init_schema(init_conn)
    finally:
        init_conn.close()

    server = IntroServer((args.host, args.port), Handler, str(db_path), admin_key,
                         allowed_origin, frontend_dir)
    print(f"[intro] listening on {args.host}:{args.port}")
    print(f"[intro] db: {db_path}")
    if admin_key:
        print("[intro] admin key is set (X-Admin-Key or X-Admin-Key-B64 header)")
    else:
        print("[intro] WARNING: no admin key set (dev mode, all admin routes open)")
    if frontend_dir:
        print(f"[intro] serving frontend from {frontend_dir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[intro] shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
