"""End-to-end smoke test against a running intro-game backend.

Usage:
    python3 smoke_test.py [--base http://localhost:8004] [--admin KEY]

The test:
  1. creates a game (it opens immediately),
  2. submits answers from several "phones", changes one, rejects bad input,
  3. checks that results stay hidden while the game is open,
  4. hides one entry, closes the game, checks mean, 2/3, winner, levels,
  5. reveals to phones and checks the personal result and rank,
  6. exports the CSV and deletes the game.

Run the server first:  python3 server.py
It uses the live database, so point it at a dev server, not the class one.
"""

import argparse
import json
import secrets
import sys
import urllib.error
import urllib.request


def request(method, url, *, body=None, headers=None, raw=False):
    data = None
    h = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = resp.read()
            return resp.status, payload if raw else json.loads(payload or b"{}")
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload or b"{}")
        except json.JSONDecodeError:
            return exc.code, {"error": payload.decode("utf-8", "replace")}


def check(cond, message):
    if not cond:
        print(f"FAIL: {message}")
        sys.exit(1)
    print(f"ok   {message}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8004")
    ap.add_argument("--admin", default="")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    admin = {"X-Admin-Key": args.admin} if args.admin else {}

    status, body = request("GET", f"{base}/api/health")
    check(status == 200 and body.get("ok"), "health")

    status, body = request("POST", f"{base}/api/admin/games", body={}, headers=admin)
    check(status == 201, f"create game ({status})")
    code = body["game"]["code"]
    check(body["game"]["status"] == "open", f"new game {code} is open")

    status, body = request("GET", f"{base}/api/game/current")
    check(body["game"]["code"] == code, "current game is the new one")
    check("title" not in body["game"], "the instructor's title is not public")

    phones = [secrets.token_hex(12) for _ in range(5)]
    answers = [("Мария", 30), ("Петър", "22,5"), ("Ива", 50), ("Жоро", 0), ("=1+1", 100)]
    for token, (name, value) in zip(phones, answers):
        status, body = request("POST", f"{base}/api/game/current/entry",
                               body={"client_token": token, "name": name, "value": value})
        check(status == 200, f"entry {name}={value}")

    status, body = request("POST", f"{base}/api/game/current/entry",
                           body={"client_token": phones[2], "name": "Ива", "value": 40})
    check(status == 200 and body["entry"]["value"] == 40, "same phone changes its answer")

    for bad in (101, -1, "abc", "", None, "1e2", 10 ** 400):
        status, body = request("POST", f"{base}/api/game/current/entry",
                               body={"client_token": phones[0], "name": "X", "value": bad})
        check(status == 400, f"rejects value {bad!r}")
    status, _ = request("POST", f"{base}/api/game/current/entry",
                        body={"client_token": "short", "name": "X", "value": 5})
    check(status == 400, "rejects a malformed device token")

    status, body = request("GET", f"{base}/api/game/current/results")
    check(body["ready"] is False and "mean" not in body and body["count"] == 5,
          "results hidden while open (count only)")

    status, detail = request("GET", f"{base}/api/admin/games/{code}", headers=admin)
    joker = next(e for e in detail["entries"] if e["name"] == "=1+1")
    status, _ = request("POST", f"{base}/api/admin/games/{code}/entries/{joker['id']}",
                        body={"hidden": True}, headers=admin)
    check(status == 200, "hide an entry")

    status, body = request("POST", f"{base}/api/admin/games/{code}/status",
                           body={"status": "closed"}, headers=admin)
    check(body["game"]["status"] == "closed", "close game")
    status, body = request("POST", f"{base}/api/game/current/entry",
                           body={"client_token": phones[0], "name": "Мария", "value": 1})
    check(status == 400, "closed game rejects entries")

    status, res = request("GET", f"{base}/api/game/current/results")
    # visible: 30, 22.5, 40, 0 -> mean 23.125, target 15.4167 -> Петър (22.5) is 7.08 away,
    # Жоро (0) is 15.42 away.
    check(res["ready"] and res["count"] == 4, "results ready, hidden entry excluded")
    check(abs(res["mean"] - 23.125) < 1e-6, f"mean {res['mean']}")
    check(abs(res["target"] - 15.4167) < 1e-3, f"target {res['target']}")
    check([w["name"] for w in res["winners"]] == ["Петър"], f"winner {res['winners']}")
    levels = {lv["key"]: lv["count"] for lv in res["levels"]}
    check(levels == {"k0": 0, "k1": 2, "k2": 1, "k3": 0, "k4": 0, "kinf": 1}, f"levels {levels}")
    check(res["target_level"] == "k3", "target sits on the 3-moves rung")

    status, me = request("GET", f"{base}/api/game/current/me?client_token={phones[1]}")
    check(me["result"] is None, "no personal result before reveal")
    request("POST", f"{base}/api/admin/games/{code}/status",
            body={"status": "revealed"}, headers=admin)
    status, me = request("GET", f"{base}/api/game/current/me?client_token={phones[1]}")
    check(me["result"]["winner"] and me["result"]["rank"] == 1, "winner sees rank 1")
    status, me = request("GET", f"{base}/api/game/current/me?client_token={phones[2]}")
    check(me["result"]["rank"] == 4, f"farthest answer sees rank 4 ({me['result']['rank']})")

    status, csv_bytes = request("GET", f"{base}/api/admin/games/{code}/csv", headers=admin, raw=True)
    text = csv_bytes.decode("utf-8-sig")
    check(status == 200 and text.startswith("game,name,value") and "Петър" in text, "csv export")
    check(",'=1+1," in text and ",=1+1," not in text, "csv keeps formula-like names as text")

    status, _ = request("DELETE", f"{base}/api/admin/games/{code}", headers=admin)
    check(status == 200, "delete game")
    print("all good")


if __name__ == "__main__":
    main()
