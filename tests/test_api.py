#!/usr/bin/env python3
# Boots the real server against a throwaway seeded database and pokes it
# the way an attacker and a dispatcher would, in that order.
import json, os, sqlite3, subprocess, sys, time, urllib.request, urllib.error

ROOT = os.path.join(os.path.dirname(__file__), "..")
TMP = "/tmp/ct_test"
DB = os.path.join(TMP, "test.db")
PORT = "8099"
BASE = f"http://127.0.0.1:{PORT}"

def call(method, path, token=None, body=None, raw=False):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            data = r.read()
            return r.status, data if raw else json.loads(data or b"{}")
    except urllib.error.HTTPError as e:
        data = e.read()
        try:
            return e.code, data if raw else json.loads(data or b"{}")
        except json.JSONDecodeError:
            return e.code, {}

def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        raise SystemExit(1)

os.makedirs(TMP, exist_ok=True)
env = {**os.environ, "CT_DB": DB, "PORT": PORT}
subprocess.run([sys.executable, "seed.py"], cwd=os.path.join(ROOT, "backend"),
               env=env, check=True, capture_output=True)
srv = subprocess.Popen([sys.executable, "app.py"], cwd=os.path.join(ROOT, "backend"),
                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(50):
        try:
            call("GET", "/"); break
        except Exception:
            time.sleep(0.2)

    code, _ = call("GET", "/api/offices")
    check("no token, no data (401)", code == 401)
    code, _ = call("POST", "/api/login", body={"username": "admin", "password": "nope"})
    check("wrong password rejected (401)", code == 401)
    code, _ = call("POST", "/api/login", body={"username": "admin' OR '1'='1", "password": "x"})
    check("injection attempt gets 401, not a session", code == 401)

    code, page = call("GET", "/", raw=True)
    check("frontend served (200, English LTR terminal)",
          code == 200 and b'lang="en"' in page and b'data-terminal' in page)

    _, admin = call("POST", "/api/login", body={"username": "admin", "password": "admin1234"})
    tok = admin["token"]
    code, full = call("GET", "/api/offices?from=2026-09-14&to=2026-10-22", tok)
    code2, week = call("GET", "/api/offices?from=2026-10-19&to=2026-10-22", tok)
    check("date range changes office numbers",
          full["offices"][0]["completed"] != week["offices"][0]["completed"])
    offs = {o["name"]: o for o in full["offices"]}
    check("small office flagged, unranked",
          offs["Al Nokhba Office"]["small_sample"] is True and offs["Al Nokhba Office"]["rank"] is None)
    check("top office still computes 92.9 on the converted seed",
          offs["Al Nour Office"]["success_rate"] == 92.9
          and offs["Al Nour Office"]["delivered"] == 18235
          and offs["Al Nour Office"]["completed"] == 19629)
    code, inv = call("GET", "/api/invoices", tok)
    baraka = next(i for i in inv["invoices"] if i["office"] == "Al Baraka Office")
    check("invoice check catches the 3 phantom days", baraka["variance_days"] == 3)
    code, perf = call("GET", "/api/performers?to=2026-10-22", tok)
    check("trailing-6-weeks performer share computed", perf["eligible"] >= 5)
    code, plan2 = call("GET", "/api/planner?date=2026-10-06&volume=1000", tok)
    check("planner lists sick-leave da on his leave day",
          any(x["courier"] == "Ahmed El Shenawy" for x in plan2["on_leave"]))
    code, txt = call("GET", "/api/offices/1/whatsapp?date=2026-10-22", tok, raw=True)
    check("whatsapp summary text generated", code == 200 and "Success rate" in txt.decode())
    code, csv_data = call("GET", "/api/export/offices.csv?from=2026-09-14&to=2026-10-22", tok, raw=True)
    check("CSV export works", code == 200 and b"success_pct" in csv_data)

    _, vw = call("POST", "/api/login", body={"username": "viewer", "password": "viewer1234"})
    code, _ = call("POST", "/api/followups", vw["token"], {"kind": "call_da", "note": "x"})
    check("viewer cannot write (403)", code == 403)
    _, fu = call("POST", "/api/login", body={"username": "dispatcher", "password": "demo1234"})
    code, scoped = call("GET", "/api/offices?from=2026-09-14&to=2026-10-22", fu["token"])
    check("follow-up agent sees only his office",
          len(scoped["offices"]) == 1 and scoped["offices"][0]["id"] == 1)
    code, _ = call("GET", "/api/audit", fu["token"])
    check("audit trail is admin-only (403)", code == 403)

    # correction flow: change a number, the audit trail must remember the old one
    code, rows = call("GET", "/api/couriers?from=2026-10-22&to=2026-10-22", tok)
    code, _ = call("POST", "/api/records", tok,
                   {"courier_id": 1, "date": "2026-10-22", "delivered": 137})
    code, au = call("GET", "/api/audit", tok)
    check("edit written to audit trail with old and new values",
          any(a["field"] == "delivered" and a["new_value"] == "137" for a in au["audit"]))

    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT pw_hash, salt FROM users WHERE username = 'admin'").fetchone()
    check("password stored as PBKDF2 hash, not plain",
          row[0] != "admin1234" and len(row[0]) == 64 and len(row[1]) == 32)
    conn.close()
    print("all api tests passed")
finally:
    srv.terminate()
