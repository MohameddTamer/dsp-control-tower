#!/usr/bin/env python3
# Deepening checks: csv import, the report endpoint, backup, config from the environment.
# Boots the real server on a throwaway database, same style as test_api.py.
import json, os, sqlite3, subprocess, sys, time, urllib.request, urllib.error

ROOT = os.path.join(os.path.dirname(__file__), "..")
TMP = "/tmp/ct_deep"
DB = os.path.join(TMP, "deep.db")
BACKUPS = os.path.join(TMP, "backups")
LOGF = os.path.join(TMP, "server.log")
PORT = "8101"
BASE = f"http://127.0.0.1:{PORT}"

def call(method, path, token=None, body=None, raw=None, base=BASE):
    if raw is not None:
        data, ctype = raw.encode(), "text/csv"
    elif body is not None:
        data, ctype = json.dumps(body).encode(), "application/json"
    else:
        data, ctype = None, "application/json"
    req = urllib.request.Request(base + path, method=method, data=data,
                                 headers={"Content-Type": ctype,
                                          **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            payload = r.read()
            try:
                return r.status, json.loads(payload or b"{}")
            except json.JSONDecodeError:
                return r.status, payload
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload or b"{}")
        except json.JSONDecodeError:
            return e.code, {}

def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        raise SystemExit(1)

os.makedirs(TMP, exist_ok=True)
env = {**os.environ, "CT_DB": DB, "PORT": PORT, "CT_TOKEN_TTL": "3600",
       "CT_BACKUP_DIR": BACKUPS, "CT_LOG_FILE": LOGF}
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

    check("custom db path from env was seeded", os.path.exists(DB))
    code, page = call("GET", "/", raw=None)
    check("server answers on the custom port from env", code == 200)

    _, admin = call("POST", "/api/login", body={"username": "admin", "password": "admin1234"})
    tok = admin["token"]
    _, vw = call("POST", "/api/login", body={"username": "viewer", "password": "viewer1234"})
    _, fu = call("POST", "/api/login", body={"username": "dispatcher", "password": "demo1234"})

    code, cfg = call("GET", "/api/admin/config", tok)
    check("config endpoint answers for admin", code == 200)
    check("token ttl from env respected (3600, not the 28800 default)", cfg["token_ttl_seconds"] == 3600)
    check("config names the custom db file", cfg["db_file"] == "deep.db")
    check("config names the custom backup dir", cfg["backup_dir"] == "backups")
    code, _ = call("GET", "/api/admin/config", vw["token"])
    check("config is admin only (403 for viewer)", code == 403)

    good_csv = ("date,courier_id,assigned,delivered,attempted_failed\n"
                "2026-10-23,1,100,90,10\n"
                "2026-10-23,2,80,72,8\n"
                "2026-10-23,1,100,90,10\n")
    code, rep = call("POST", "/api/import/records", raw=good_csv)
    check("import without a token is 401 with a structured error",
          code == 401 and rep.get("code") == 401 and "error" in rep)
    code, rep = call("POST", "/api/import/records", vw["token"], raw=good_csv)
    check("viewer cannot import (403)", code == 403)

    code, rep = call("POST", "/api/import/records", tok, raw=good_csv)
    check("import answers 200", code == 200)
    check("import inserted the two new daily records", rep["inserted"] == 2)
    check("import counted every data row", rep["total_rows"] == 3)
    check("the repeated row inside the file is named as a duplicate",
          rep["skipped_duplicates"] == [{"courier_id": 1, "date": "2026-10-23"}])
    check("clean import has no rejected rows", rep["rejected_rows"] == [])

    code, rep2 = call("POST", "/api/import/records", tok, raw=good_csv)
    check("reimport inserts nothing", rep2["inserted"] == 0)
    check("reimport names all three rows as duplicates", len(rep2["skipped_duplicates"]) == 3)

    code, rep = call("GET", "/api/report?from=2026-10-23&to=2026-10-23", tok)
    check("report endpoint answers for the imported day", code == 200)
    check("report totals include the imported stops",
          rep["totals"]["assigned"] == 180 and rep["totals"]["delivered"] == 162)
    check("report trend has one day at 90.0 percent",
          len(rep["trend"]) == 1 and rep["trend"][0]["success_rate"] == 90.0)
    check("report shape carries offices and couriers",
          any(o["name"] == "Al Nour Office" for o in rep["offices"]) and len(rep["couriers"]) == 2)
    check("report echoes the range it used", rep["from"] == "2026-10-23" and rep["to"] == "2026-10-23")

    bad_csv = ("date,courier_id,assigned,delivered\n"
               "23-10-2026,1,100,90\n"
               "2026-10-24,1,abc,90\n"
               "2026-10-24,1,-5,90\n"
               "2026-10-24,999,100,90\n"
               "2026-10-24,2,100,\n")
    code, rep = call("POST", "/api/import/records", tok, raw=bad_csv)
    reasons = {r["row"]: r["reason"] for r in rep["rejected_rows"]}
    check("malformed import inserts nothing", rep["inserted"] == 0)
    check("all five bad rows are rejected, none swallowed", len(rep["rejected_rows"]) == 5)
    check("bad date rejected with its row number", 2 in reasons and "YYYY-MM-DD" in reasons[2])
    check("unknown courier rejected and named", "courier_id 999 not found" in reasons.get(5, ""))
    check("negative count rejected as out of range", "out of range" in reasons.get(4, ""))
    check("blank count rejected, not treated as zero", 6 in reasons)

    code, rep = call("POST", "/api/import/records", tok, raw="date,assigned\n2026-10-24,10\n")
    check("missing columns are a 400, not a partial import", code == 400)
    check("missing columns are named in the error",
          rep.get("missing_columns") == ["courier_id", "delivered"] and rep.get("code") == 400)
    code, rep = call("POST", "/api/import/records", tok, raw="")
    check("empty csv body is a 400 with a structured error", code == 400 and rep.get("code") == 400)

    scope_csv = "date,courier_id,assigned,delivered\n2026-10-24,5,90,80\n"
    code, rep = call("POST", "/api/import/records", fu["token"], raw=scope_csv)
    check("follow-up agent cannot import another office's courier",
          rep["inserted"] == 0 and "another office" in rep["rejected_rows"][0]["reason"])
    own_csv = "date,courier_id,assigned,delivered\n2026-10-24,1,90,81\n"
    code, rep = call("POST", "/api/import/records", fu["token"], raw=own_csv)
    check("follow-up agent can import his own office", rep["inserted"] == 1)

    code, _ = call("POST", "/api/admin/backup", fu["token"], body={})
    check("backup is admin only (403 for follow-up)", code == 403)
    code, bk = call("POST", "/api/admin/backup", tok, body={})
    check("backup answers with a file name", code == 200 and bk["backup_file"].endswith(".db"))
    bpath = os.path.join(BACKUPS, bk["backup_file"])
    check("backup file exists in the configured dir", os.path.exists(bpath))
    src = sqlite3.connect(DB)
    want = src.execute("SELECT COUNT(*) FROM daily_records").fetchone()[0]; src.close()
    copy = sqlite3.connect(bpath)
    check("backup is a valid sqlite copy with the same records",
          copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
          and copy.execute("SELECT COUNT(*) FROM daily_records").fetchone()[0] == want)
    copy.close()

    code, err = call("GET", "/api/does-not-exist", tok)
    check("unknown route is a structured 404", code == 404 and err.get("code") == 404)
    code, err = call("GET", "/api/offices?from=nope&to=nada", tok)
    check("bad range is a structured 400", code == 400 and err.get("code") == 400)
    code, err = call("POST", "/api/login", body={"username": "admin", "password": "nope"})
    check("bad login is a structured 401", code == 401 and err.get("code") == 401)
    check("log file was written by the running server",
          os.path.exists(LOGF) and "csv import" in open(LOGF, encoding="utf-8").read())
finally:
    srv.terminate()

# a second instance with a two second token ttl proves the ttl is enforced, not just reported
env2 = {**env, "PORT": "8102", "CT_TOKEN_TTL": "2", "CT_LOG_FILE": os.path.join(TMP, "short.log")}
srv2 = subprocess.Popen([sys.executable, "app.py"], cwd=os.path.join(ROOT, "backend"),
                        env=env2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    base2 = "http://127.0.0.1:8102"
    for _ in range(50):
        try:
            call("GET", "/", base=base2); break
        except Exception:
            time.sleep(0.2)
    _, sess = call("POST", "/api/login", body={"username": "admin", "password": "admin1234"}, base=base2)
    code, _ = call("GET", "/api/me", sess["token"], base=base2)
    check("fresh token works on the short ttl instance", code == 200)
    time.sleep(2.4)
    code, _ = call("GET", "/api/me", sess["token"], base=base2)
    check("token dies after the configured ttl", code == 401)
finally:
    srv2.terminate()

print("all deepening tests passed")
