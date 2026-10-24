#!/usr/bin/env python3
# DSP Control Tower. API plus the one HTML page. Stdlib only, on purpose.
# A station machine should run this without a pip fight.
# Passwords are PBKDF2 hashes with a per user salt. Never plain, never logged.
# Every api route except login wants a bearer token. SQL is parameterised
# everywhere. A name with a quote in it is a name, not an injection.
import csv, hashlib, hmac, io, json, logging, logging.handlers, math, os, secrets, sqlite3, time
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import metrics

def _env_int(name, fallback):
    try:
        return int(os.environ.get(name, "") or fallback)
    except ValueError:
        return fallback

DB_PATH = os.environ.get("CT_DB", os.path.join(os.path.dirname(__file__), "control_tower.db"))
LOG_FILE = os.environ.get("CT_LOG_FILE", os.path.join(os.path.dirname(__file__), "control_tower.log"))
BACKUP_DIR = os.environ.get("CT_BACKUP_DIR", os.path.join(os.path.dirname(__file__), "backups"))
TOKENS = {}
TOKEN_TTL = _env_int("CT_TOKEN_TTL", 8 * 3600)

LOG = logging.getLogger("control_tower")
if not LOG.handlers:
    LOG.setLevel(logging.INFO)
    try:
        _handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        LOG.addHandler(_handler)
    except OSError:
        LOG.addHandler(logging.NullHandler())

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000).hex()

def check_password(password, salt_hex, expected_hex):
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt_hex)), expected_hex)

def parse_range(q, conn):
    lo = conn.execute("SELECT MIN(date) d FROM daily_records").fetchone()["d"]
    hi = conn.execute("SELECT MAX(date) d FROM daily_records").fetchone()["d"]
    f = q.get("from", [lo])[0]
    t = q.get("to", [hi])[0]
    try:
        d0, d1 = date.fromisoformat(f), date.fromisoformat(t)
    except ValueError:
        return None, None, "bad date, use YYYY-MM-DD"
    if d0 > d1 or (d1 - d0).days > 366:
        return None, None, "range is backwards or longer than a year"
    return f, t, None

def audit(conn, user, entity, entity_id, field, old, new):
    conn.execute("INSERT INTO audit_log (username, at, entity, entity_id, field, old_value, new_value)"
                 " VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (user, datetime.now().isoformat(timespec="seconds"), entity, entity_id,
                  field, None if old is None else str(old), None if new is None else str(new)))

class Handler(BaseHTTPRequestHandler):
    def _error(self, code, message):
        return self._send(code, {"error": message, "code": code})

    def _send(self, code, payload, ctype="application/json; charset=utf-8"):
        body = payload if isinstance(payload, bytes) else \
            (payload.encode() if isinstance(payload, str) else
             json.dumps(payload, ensure_ascii=False).encode())
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _session(self):
        token = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        s = TOKENS.get(token)
        return s if s and s["expires"] > time.time() else None

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20_000:
            return None
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return None

    def _scope_office(self, sess, requested):
        """A follow-up agent sees his office. Anyone else sees what they asked for."""
        if sess["role"] == "followup":
            return sess["office_id"]
        return int(requested) if requested else None

    def _post_impl(self):
        path = urlparse(self.path).path
        if path in ("/api/import/records", "/api/admin/backup"):
            sess = self._session()
            if not sess:
                return self._error(401, "login required")
            if path == "/api/admin/backup":
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                return self._backup(sess)
            return self._import_records(sess)
        data = self._body()
        if data is None:
            return self._error(400, "invalid request body")
        if path == "/api/login":
            conn = db()
            row = conn.execute("SELECT * FROM users WHERE username = ?",
                               (str(data.get("username", ""))[:40],)).fetchone()
            conn.close()
            if not row or not check_password(str(data.get("password", ""))[:100], row["salt"], row["pw_hash"]):
                return self._error(401, "wrong username or password")
            token = secrets.token_urlsafe(32)
            TOKENS[token] = {"user": row["username"], "role": row["role"],
                             "office_id": row["office_id"], "expires": time.time() + TOKEN_TTL}
            return self._send(200, {"token": token, "user": row["username"],
                                    "role": row["role"], "office_id": row["office_id"]})
        sess = self._session()
        if not sess:
            return self._error(401, "login required")
        if sess["role"] == "viewer":
            return self._error(403, "viewer accounts are read-only")
        conn = db()
        if path == "/api/followups":
            kind = str(data.get("kind", ""))[:30]
            note = str(data.get("note", ""))[:500]
            da = data.get("courier_id")
            off = data.get("office_id")
            if kind not in ("call_da", "call_customer", "escalation", "coaching") or not note:
                conn.close(); return self._error(400, "valid kind and a note are required")
            if sess["role"] == "followup":
                off = sess["office_id"]
            cur = conn.execute("INSERT INTO followups (courier_id, office_id, kind, note, created_at, created_by)"
                               " VALUES (?, ?, ?, ?, ?, ?)",
                               (da, off, kind, note, datetime.now().isoformat(timespec="minutes"), sess["user"]))
            audit(conn, sess["user"], "followup", cur.lastrowid, "created", None, kind)
            conn.commit(); conn.close()
            return self._send(201, {"ok": True})
        if path == "/api/records":
            # one day for one da. Correcting a wrong number is exactly what
            # the audit trail is for. Old value kept, who changed it kept.
            try:
                da = int(data["courier_id"]); day = str(data["date"])
                date.fromisoformat(day)
                fields = {k: int(data[k]) for k in
                          ("assigned", "delivered", "attempted_failed", "returns", "dnr",
                           "pod_good", "pod_bad", "fb_pos", "fb_neg", "checkpoint_done") if k in data}
            except (KeyError, ValueError, TypeError):
                conn.close(); return self._error(400, "courier_id, a valid date and integer counts are required")
            if any(v < 0 or v > 100000 for v in fields.values()):
                conn.close(); return self._error(400, "counts out of range")
            row = conn.execute("SELECT * FROM daily_records WHERE date = ? AND courier_id = ?",
                               (day, da)).fetchone()
            if row:
                for k, v in fields.items():
                    if row[k] != v:
                        audit(conn, sess["user"], "daily_record", row["id"], k, row[k], v)
                if fields:
                    conn.execute("UPDATE daily_records SET " +
                                 ", ".join(k + " = ?" for k in fields) + " WHERE id = ?",
                                 (*fields.values(), row["id"]))
            else:
                hist = conn.execute("SELECT office_id FROM office_history WHERE courier_id = ? AND"
                                    " from_date <= ? AND (to_date IS NULL OR to_date >= ?) ORDER BY from_date DESC",
                                    (da, day, day)).fetchone()
                route = conn.execute("SELECT route_name FROM daily_records WHERE courier_id = ?"
                                     " ORDER BY date DESC LIMIT 1", (da,)).fetchone()
                cur = conn.execute(
                    "INSERT INTO daily_records (date, courier_id, office_id, route_name, assigned, delivered,"
                    " attempted_failed, returns, dnr, pod_good, pod_bad, fb_pos, fb_neg, checkpoint_done)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (day, da, hist["office_id"] if hist else None,
                     route["route_name"] if route else "",
                     fields.get("assigned", 0), fields.get("delivered", 0), fields.get("attempted_failed", 0),
                     fields.get("returns", 0), fields.get("dnr", 0), fields.get("pod_good", 0),
                     fields.get("pod_bad", 0), fields.get("fb_pos", 0), fields.get("fb_neg", 0),
                     fields.get("checkpoint_done", 0)))
                audit(conn, sess["user"], "daily_record", cur.lastrowid, "created", None, day)
            conn.commit(); conn.close()
            return self._send(201, {"ok": True})
        if path == "/api/leaves":
            try:
                da = int(data["courier_id"])
                a, b = str(data["from_date"]), str(data["to_date"])
                date.fromisoformat(a); date.fromisoformat(b)
                kind = str(data["type"])
                assert kind in ("annual", "sick", "unpaid", "unexcused") and a <= b
            except (KeyError, ValueError, TypeError, AssertionError):
                conn.close(); return self._error(400, "courier_id, valid dates and leave type required")
            cur = conn.execute("INSERT INTO leaves (courier_id, from_date, to_date, type) VALUES (?, ?, ?, ?)",
                               (da, a, b, kind))
            audit(conn, sess["user"], "leave", cur.lastrowid, "created", None, f"{a}..{b} {kind}")
            conn.commit(); conn.close()
            return self._send(201, {"ok": True})
        if path.startswith("/api/safety/") and path.endswith("/dispute"):
            ev_id = path.split("/")[3]
            conn.execute("UPDATE safety_events SET disputed = 1, outcome = 'under review' WHERE id = ?", (ev_id,))
            audit(conn, sess["user"], "safety_event", ev_id, "disputed", 0, 1)
            conn.commit(); conn.close()
            return self._send(200, {"ok": True})
        conn.close()
        return self._error(404, "not found")

    def _get_impl(self):
        parsed = urlparse(self.path)
        path, q = parsed.path, parse_qs(parsed.query)
        if path in ("/", "/index.html"):
            fpath = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
            with open(fpath, "rb") as fh:
                return self._send(200, fh.read(), "text/html; charset=utf-8")
        if not path.startswith("/api/"):
            return self._error(404, "not found")
        sess = self._session()
        if not sess:
            return self._error(401, "login required")
        conn = db()
        if path == "/api/me":
            conn.close()
            return self._send(200, {"user": sess["user"], "role": sess["role"], "office_id": sess["office_id"]})
        f, t, err = parse_range(q, conn)
        range_paths = ("/api/offices", "/api/couriers", "/api/alerts", "/api/performers",
                       "/api/pod", "/api/rescues", "/api/tv", "/api/report", "/api/export")
        if err and any(path == r or path.startswith(r + "/") for r in range_paths):
            conn.close(); return self._send(400, {"error": err, "code": 400})
        if err:
            f, t = None, None

        if path == "/api/offices":
            table = metrics.office_table(conn, f, t)
            if sess["role"] == "followup":
                table = [o for o in table if o["id"] == sess["office_id"]]
            payload = {"offices": table, "from": f, "to": t}
        elif path.startswith("/api/offices/") and path.endswith("/whatsapp"):
            off_id = int(path.split("/")[3])
            day = q.get("date", [t])[0]
            payload = self._whatsapp(conn, off_id, day)
            conn.close()
            return self._send(200, payload, "text/plain; charset=utf-8")
        elif path.startswith("/api/offices/"):
            off_id = int(path.split("/")[3])
            if sess["role"] == "followup" and off_id != sess["office_id"]:
                conn.close(); return self._error(403, "not your office")
            off = conn.execute("SELECT * FROM offices WHERE id = ?", (off_id,)).fetchone()
            if not off:
                conn.close(); return self._error(404, "no such office")
            rows = metrics.day_rows(conn, f, t, office_id=off_id)
            payload = {"office": dict(off), "totals": metrics.totals(rows),
                       "couriers": metrics.courier_table(conn, f, t, office_id=off_id),
                       "curve": metrics.daily_curve(conn, f, t, office_id=off_id),
                       "worst_areas": metrics.worst_areas(conn, f, t, off_id)}
        elif path == "/api/couriers":
            off = self._scope_office(sess, q.get("office", [None])[0])
            payload = {"couriers": metrics.courier_table(conn, f, t, office_id=off)}
        elif path.startswith("/api/couriers/"):
            da = int(path.split("/")[3])
            prof = conn.execute("SELECT * FROM couriers WHERE id = ?", (da,)).fetchone()
            if not prof:
                conn.close(); return self._error(404, "no such courier")
            prof = dict(prof)
            rows = [r for r in metrics.day_rows(conn, f, t) if r["courier_id"] == da]
            leaves = [dict(r) for r in conn.execute("SELECT * FROM leaves WHERE courier_id = ? ORDER BY from_date", (da,))]
            used_annual = 0
            jan1 = date(int(t[:4]), 1, 1)  # annual balance is a calendar-year thing
            for lv in leaves:
                if lv["type"] == "annual":
                    a = max(date.fromisoformat(lv["from_date"]), jan1)
                    b = date.fromisoformat(lv["to_date"])
                    if b >= jan1:
                        used_annual += (b - a).days + 1
            hist = [dict(r) for r in conn.execute(
                "SELECT h.*, o.name office_name FROM office_history h JOIN offices o ON o.id = h.office_id"
                " WHERE courier_id = ? ORDER BY from_date", (da,))]
            office_now = conn.execute(
                "SELECT office_id FROM office_history WHERE courier_id = ? AND (to_date IS NULL)"
                " ORDER BY from_date DESC", (da,)).fetchone()
            payload = {"profile": prof, "totals": metrics.totals(rows),
                       "curve": metrics.daily_curve(conn, f, t, courier_id=da),
                       "leaves": leaves, "leave_used_annual": used_annual,
                       "leave_balance_annual": prof["annual_leave_total"] - used_annual,
                       "office_history": hist,
                       "office_now": office_now["office_id"] if office_now else None,
                       "plans": [dict(r) for r in conn.execute("SELECT * FROM coaching_plans WHERE courier_id = ?", (da,))],
                       "safety": [dict(r) for r in conn.execute("SELECT * FROM safety_events WHERE courier_id = ? ORDER BY occurred_at DESC", (da,))]}
        elif path == "/api/alerts":
            day = q.get("date", [t])[0]
            alerts = metrics.checkpoint_alerts(conn, day)
            if sess["role"] == "followup":
                my = {r["name"] for r in conn.execute(
                    "SELECT c.name FROM couriers c JOIN office_history h ON h.courier_id = c.id"
                    " WHERE h.office_id = ? AND h.to_date IS NULL", (sess["office_id"],))}
                alerts = [a for a in alerts if a["courier"] in my]
            payload = {"alerts": alerts, "date": day}
        elif path == "/api/performers":
            payload = metrics.performer_share(conn, t)
        elif path == "/api/pod":
            day = q.get("date", [t])[0]
            flags = [dict(r) for r in conn.execute(
                "SELECT p.*, c.name courier FROM pod_flags p JOIN couriers c ON c.id = p.courier_id"
                " WHERE p.date = ? ORDER BY p.courier_id", (day,))]
            rows = metrics.day_rows(conn, day, day)
            board = {}
            for r in rows:
                b = board.setdefault(r["courier_id"], {"good": 0, "bad": 0})
                b["good"] += r["pod_good"]; b["bad"] += r["pod_bad"]
            names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM couriers")}
            scored = [{"courier": names[k], "pod_score": metrics._pct(v["good"], v["good"] + v["bad"])}
                      for k, v in board.items() if v["good"] + v["bad"]]
            payload = {"date": day, "flags": flags,
                       "fame": sorted(scored, key=lambda x: -x["pod_score"])[:3],
                       "shame": sorted(scored, key=lambda x: x["pod_score"])[:3]}
        elif path == "/api/safety":
            now = datetime.now()
            events = []
            for r in conn.execute("SELECT s.*, c.name courier FROM safety_events s"
                                  " JOIN couriers c ON c.id = s.courier_id ORDER BY s.occurred_at DESC"):
                e = dict(r)
                deadline = datetime.fromisoformat(e["occurred_at"]) + timedelta(hours=48)
                e["dispute_deadline"] = deadline.isoformat(timespec="minutes")
                e["hours_left"] = round((deadline - now).total_seconds() / 3600, 1)
                e["window"] = ("disputed" if e["disputed"] else
                               "open" if e["hours_left"] > 0 else "expired")
                events.append(e)
            payload = {"events": events}
        elif path == "/api/plans":
            payload = {"plans": [dict(r) for r in conn.execute(
                "SELECT p.*, c.name courier FROM coaching_plans p JOIN couriers c ON c.id = p.courier_id"
                " ORDER BY p.review_date")]}
        elif path == "/api/rescues":
            payload = {"rescues": [dict(r) for r in conn.execute(
                "SELECT r.*, a.name from_name, b.name to_name FROM rescues r"
                " JOIN couriers a ON a.id = r.from_courier JOIN couriers b ON b.id = r.to_courier"
                " WHERE r.date BETWEEN ? AND ? ORDER BY r.date DESC", (f, t))]}
        elif path == "/api/invoices":
            checks = []
            for inv in conn.execute("SELECT i.*, o.name office FROM invoices i JOIN offices o ON o.id = i.office_id"):
                inv = dict(inv)
                recorded = conn.execute(
                    "SELECT COUNT(*) n FROM (SELECT DISTINCT date, courier_id FROM daily_records"
                    " WHERE office_id = ? AND date BETWEEN ? AND ?)",
                    (inv["office_id"], inv["period_from"], inv["period_to"])).fetchone()["n"]
                inv["recorded_days"] = recorded
                inv["variance_days"] = inv["billed_days"] - recorded
                inv["variance_money"] = round(inv["variance_days"] * inv["rate_per_day"], 2)
                checks.append(inv)
            payload = {"invoices": checks}
        elif path == "/api/planner":
            day = q.get("date", [None])[0]
            if not day:
                hi = conn.execute("SELECT MAX(date) d FROM daily_records").fetchone()["d"]
                day = (date.fromisoformat(hi) + timedelta(days=1)).isoformat()
            last7 = conn.execute("SELECT MAX(date) d FROM daily_records").fetchone()["d"]
            rows = metrics.day_rows(conn, (date.fromisoformat(last7) - timedelta(days=6)).isoformat(), last7)
            avg = (sum(r["assigned"] for r in rows) / len(rows)) if rows else 120
            volume = int(q.get("volume", [sum(r["assigned"] for r in rows[-10:]) or 1200])[0])
            needed = math.ceil(volume / avg) if avg else 0
            spans = {}
            active_by_office = {}
            on_leave = []
            names = {}
            for c in conn.execute("SELECT * FROM couriers"):
                names[c["id"]] = c["name"]
                lv = conn.execute("SELECT * FROM leaves WHERE courier_id = ? AND from_date <= ? AND to_date >= ?",
                                  (c["id"], day, day)).fetchone()
                hist = conn.execute("SELECT office_id FROM office_history WHERE courier_id = ? AND"
                                    " from_date <= ? AND (to_date IS NULL OR to_date >= ?)"
                                    " ORDER BY from_date DESC", (c["id"], day, day)).fetchone()
                if lv:
                    on_leave.append({"courier": c["name"], "type": lv["type"]})
                elif hist:
                    active_by_office[hist["office_id"]] = active_by_office.get(hist["office_id"], 0) + 1
            total_active = sum(active_by_office.values()) or 1
            offices = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM offices")}
            alloc = []
            given = 0
            items = sorted(active_by_office.items())
            for i, (off_id, cnt) in enumerate(items):
                share = needed - given if i == len(items) - 1 else round(needed * cnt / total_active)
                given += share
                alloc.append({"office": offices[off_id], "active_das": cnt, "must_supply": max(share, 0)})
            payload = {"date": day, "expected_volume": volume, "avg_stops_per_da": round(avg, 1),
                       "das_needed": needed, "allocation": alloc, "on_leave": on_leave}
        elif path == "/api/tv":
            payload = {"couriers": metrics.courier_table(conn, f, t),
                       "offices": metrics.office_table(conn, f, t)}
        elif path == "/api/report":
            rows = metrics.day_rows(conn, f, t)
            payload = {"from": f, "to": t, "totals": metrics.totals(rows),
                       "trend": metrics.daily_curve(conn, f, t),
                       "offices": metrics.office_table(conn, f, t),
                       "couriers": metrics.courier_table(conn, f, t)}
        elif path == "/api/admin/config":
            if sess["role"] != "admin":
                conn.close(); return self._error(403, "config is admin only")
            payload = {"token_ttl_seconds": TOKEN_TTL, "db_file": os.path.basename(DB_PATH),
                       "log_file": os.path.basename(LOG_FILE), "backup_dir": os.path.basename(BACKUP_DIR)}
        elif path == "/api/audit":
            if sess["role"] != "admin":
                conn.close(); return self._error(403, "audit trail is admin-only")
            payload = {"audit": [dict(r) for r in conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT 100")]}
        elif path == "/api/followups":
            rows = conn.execute("SELECT f.*, c.name courier FROM followups f"
                                " LEFT JOIN couriers c ON c.id = f.courier_id ORDER BY f.id DESC LIMIT 100").fetchall()
            payload = {"followups": [dict(r) for r in rows]}
        elif path == "/api/vehicles":
            payload = {"checks": [dict(r) for r in conn.execute(
                "SELECT v.*, c.name courier FROM vehicle_checks v JOIN couriers c ON c.id = v.courier_id"
                " ORDER BY v.date DESC")],
                "maintenance_due": [dict(r) for r in conn.execute(
                    "SELECT v.*, c.name courier FROM vehicle_checks v JOIN couriers c ON c.id = v.courier_id"
                    " WHERE v.next_maintenance <= date('now', '+7 days') ORDER BY v.next_maintenance")]}
        elif path == "/api/search":
            needle = "%" + q.get("q", [""])[0][:40] + "%"
            payload = {
                "couriers": [dict(r) for r in conn.execute("SELECT id, name FROM couriers WHERE name LIKE ?", (needle,))],
                "offices": [dict(r) for r in conn.execute("SELECT id, name FROM offices WHERE name LIKE ?", (needle,))]}
        elif path in ("/api/export/offices.csv", "/api/export/couriers.csv"):
            import io, csv
            buf = io.StringIO()
            w = csv.writer(buf)
            if path.endswith("offices.csv"):
                w.writerow(["office", "rank", "small_sample", "couriers", "assigned", "delivered",
                            "completed", "success_pct", "dcr", "dnr_rate", "pod_score", "rts", "trend"])
                for o in metrics.office_table(conn, f, t):
                    w.writerow([o["name"], o["rank"], o["small_sample"], o["couriers_active"], o["assigned"],
                                o["delivered"], o["completed"], o["success_rate"], o["dcr"], o["dnr_rate"],
                                o["pod_score"], o["rts"], o["trend"]])
            else:
                w.writerow(["courier", "office", "rank", "band", "assigned", "delivered", "completed",
                            "success_pct", "adjusted_pct", "dcr", "dnr_rate", "pod_score", "leave_days"])
                for c in metrics.courier_table(conn, f, t):
                    w.writerow([c["name"], c["office_name"], c["rank"], c["band"], c["assigned"],
                                c["delivered"], c["completed"], c["success_rate"], c["adjusted_rate"],
                                c["dcr"], c["dnr_rate"], c["pod_score"], c["leave_days_in_range"]])
            conn.close()
            return self._send(200, buf.getvalue(), "text/csv; charset=utf-8")
        else:
            conn.close()
            return self._error(404, "not found")
        conn.close()
        return self._send(200, payload)


    def do_POST(self):
        try:
            self._post_impl()
        except ValueError:
            LOG.exception("bad value in POST %s", self.path)
            self._error(400, "bad value in request")
        except Exception:
            LOG.exception("failed POST %s", self.path)
            self._error(500, "internal error")

    def do_GET(self):
        try:
            self._get_impl()
        except ValueError:
            LOG.exception("bad value in GET %s", self.path)
            self._error(400, "bad value in request")
        except Exception:
            LOG.exception("failed GET %s", self.path)
            self._error(500, "internal error")

    def _raw_body(self, limit=500_000):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            return None
        return self.rfile.read(n) if n else b""

    def _backup(self, sess):
        if sess["role"] != "admin":
            return self._error(403, "backup is admin only")
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        name = f"control-tower-{stamp}.db"
        dest = os.path.join(BACKUP_DIR, name)
        src = db()
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()
        LOG.info("backup written by %s: %s", sess["user"], name)
        return self._send(200, {"ok": True, "backup_file": name, "size": os.path.getsize(dest)})

    def _import_records(self, sess):
        if sess["role"] == "viewer":
            return self._error(403, "viewer accounts are read-only")
        raw = self._raw_body()
        if raw is None:
            return self._error(413, "csv body too large")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return self._error(400, "csv body must be utf-8 text")
        reader = csv.DictReader(io.StringIO(text))
        required = ["date", "courier_id", "assigned", "delivered"]
        optional = ["attempted_failed", "returns", "dnr", "pod_good", "pod_bad",
                    "fb_pos", "fb_neg", "checkpoint_done"]
        if reader.fieldnames is None:
            return self._error(400, "empty csv")
        present = [h.strip() for h in reader.fieldnames if h]
        missing = [c for c in required if c not in present]
        if missing:
            return self._send(400, {"error": "missing columns: " + ", ".join(missing),
                                    "code": 400, "missing_columns": missing})
        report = {"inserted": 0, "skipped_duplicates": [], "rejected_rows": [], "total_rows": 0}
        conn = db()
        try:
            for lineno, row in enumerate(reader, start=2):
                vals = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
                if not any(vals.values()):
                    continue
                report["total_rows"] += 1
                try:
                    day = vals["date"]
                    date.fromisoformat(day)
                    da = int(vals["courier_id"])
                    fields = {}
                    for k in required[2:] + [o for o in optional if o in vals and vals[o] != ""]:
                        fields[k] = int(vals[k])
                except ValueError:
                    report["rejected_rows"].append(
                        {"row": lineno, "reason": "date must be YYYY-MM-DD and counts must be whole numbers"})
                    continue
                if any(v < 0 or v > 100000 for v in fields.values()):
                    report["rejected_rows"].append({"row": lineno, "reason": "counts out of range"})
                    continue
                if not conn.execute("SELECT id FROM couriers WHERE id = ?", (da,)).fetchone():
                    report["rejected_rows"].append({"row": lineno, "reason": f"courier_id {da} not found"})
                    continue
                if sess["role"] == "followup":
                    hist = conn.execute(
                        "SELECT office_id FROM office_history WHERE courier_id = ? AND from_date <= ?"
                        " AND (to_date IS NULL OR to_date >= ?) ORDER BY from_date DESC",
                        (da, day, day)).fetchone()
                    if not hist or hist["office_id"] != sess["office_id"]:
                        report["rejected_rows"].append(
                            {"row": lineno, "reason": "courier belongs to another office"})
                        continue
                if conn.execute("SELECT id FROM daily_records WHERE date = ? AND courier_id = ?",
                                (day, da)).fetchone():
                    report["skipped_duplicates"].append({"courier_id": da, "date": day})
                    continue
                hist = conn.execute(
                    "SELECT office_id FROM office_history WHERE courier_id = ? AND from_date <= ?"
                    " AND (to_date IS NULL OR to_date >= ?) ORDER BY from_date DESC",
                    (da, day, day)).fetchone()
                route = conn.execute("SELECT route_name FROM daily_records WHERE courier_id = ?"
                                     " ORDER BY date DESC LIMIT 1", (da,)).fetchone()
                cur = conn.execute(
                    "INSERT INTO daily_records (date, courier_id, office_id, route_name, assigned, delivered,"
                    " attempted_failed, returns, dnr, pod_good, pod_bad, fb_pos, fb_neg, checkpoint_done)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (day, da, hist["office_id"] if hist else None,
                     route["route_name"] if route else "",
                     fields.get("assigned", 0), fields.get("delivered", 0),
                     fields.get("attempted_failed", 0), fields.get("returns", 0),
                     fields.get("dnr", 0), fields.get("pod_good", 0), fields.get("pod_bad", 0),
                     fields.get("fb_pos", 0), fields.get("fb_neg", 0), fields.get("checkpoint_done", 0)))
                audit(conn, sess["user"], "daily_record", cur.lastrowid, "imported", None, day)
                report["inserted"] += 1
            conn.commit()
        finally:
            conn.close()
        LOG.info("csv import by %s: %s", sess["user"], report)
        return self._send(200, report)

    def _whatsapp(self, conn, off_id, day):
        # generates the text only. Sending anything anywhere is not this system's job.
        off = conn.execute("SELECT * FROM offices WHERE id = ?", (off_id,)).fetchone()
        if not off:
            return "no such office"
        rows = metrics.day_rows(conn, day, day, office_id=off_id)
        t = metrics.totals(rows)
        table = metrics.courier_table(conn, day, day, office_id=off_id)
        best = table[0]["name"] if table else "-"
        lines = [f"{off['name']} summary for {day}",
                 f"Stops: {t['assigned']} | Delivered: {t['delivered']} | Success rate: {t['success_rate']}%",
                 f"DCR: {t['dcr']}% | Station returns: {t['rts']} | DNR claims: {t['dnr']}",
                 f"Best DA today: {best}",
                 "These numbers come from the tracking system. Flag any mismatch today."]
        return "\n".join(lines)

    def log_message(self, *args):
        pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8077"))
    LOG.info("starting on port %s with db %s", port, DB_PATH)
    print(f"DSP Control Tower on http://127.0.0.1:{port}  (db: {DB_PATH})")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
