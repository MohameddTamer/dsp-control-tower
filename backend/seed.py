#!/usr/bin/env python3
# Demo data. Every name, office, phone and number below is invented.
# Dates run Mon 2026-09-14 -> Thu 2026-10-22, Fridays off (no records),
# so date ranges and the trailing-6-weeks read have something to bite on.
import os, random, secrets, sqlite3, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(__file__))
from app import hash_password, DB_PATH

START = date(2026, 9, 14)
END = date(2026, 10, 22)
rng = random.Random(42)  # fixed seed: the demo must tell the same story every run

SCHEMA = """
CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, salt TEXT, pw_hash TEXT,
                    role TEXT, office_id INTEGER);
CREATE TABLE offices (id INTEGER PRIMARY KEY, name TEXT, contact_person TEXT, phone TEXT, since_date TEXT);
CREATE TABLE routes (name TEXT PRIMARY KEY, area TEXT, difficulty REAL);
CREATE TABLE couriers (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, vehicle TEXT,
                       start_date TEXT, notes TEXT, annual_leave_total INTEGER DEFAULT 21);
CREATE TABLE office_history (id INTEGER PRIMARY KEY, courier_id INTEGER, office_id INTEGER,
                             from_date TEXT, to_date TEXT);
CREATE TABLE daily_records (id INTEGER PRIMARY KEY, date TEXT, courier_id INTEGER, office_id INTEGER,
                            route_name TEXT, assigned INTEGER, delivered INTEGER,
                            attempted_failed INTEGER, returns INTEGER, dnr INTEGER,
                            pod_good INTEGER, pod_bad INTEGER, fb_pos INTEGER, fb_neg INTEGER,
                            checkpoint_done INTEGER, UNIQUE(date, courier_id));
CREATE TABLE leaves (id INTEGER PRIMARY KEY, courier_id INTEGER, from_date TEXT, to_date TEXT, type TEXT);
CREATE TABLE followups (id INTEGER PRIMARY KEY, courier_id INTEGER, office_id INTEGER,
                        kind TEXT, note TEXT, created_at TEXT, created_by TEXT);
CREATE TABLE safety_events (id INTEGER PRIMARY KEY, courier_id INTEGER, type TEXT,
                            occurred_at TEXT, disputed INTEGER DEFAULT 0, outcome TEXT);
CREATE TABLE pod_flags (id INTEGER PRIMARY KEY, courier_id INTEGER, date TEXT, issue TEXT);
CREATE TABLE coaching_plans (id INTEGER PRIMARY KEY, courier_id INTEGER, created_date TEXT,
                             review_date TEXT, tasks TEXT, status TEXT);
CREATE TABLE rescues (id INTEGER PRIMARY KEY, date TEXT, from_courier INTEGER, to_courier INTEGER,
                      stops INTEGER, note TEXT);
CREATE TABLE invoices (id INTEGER PRIMARY KEY, office_id INTEGER, period_from TEXT, period_to TEXT,
                       billed_days INTEGER, rate_per_day REAL);
CREATE TABLE vehicle_checks (id INTEGER PRIMARY KEY, courier_id INTEGER, date TEXT,
                             van_ok INTEGER, damage_note TEXT, next_maintenance TEXT);
CREATE TABLE audit_log (id INTEGER PRIMARY KEY, username TEXT, at TEXT, entity TEXT,
                        entity_id INTEGER, field TEXT, old_value TEXT, new_value TEXT);
"""

OFFICES = [
    (1, "Al Nour Office", "Hajj Mahmoud El Sayed", "0100 111 2233", "2024-03-01"),
    (2, "Al Salam Office", "Walid Farouk", "0100 444 5566", "2023-11-15"),
    (3, "Al Baraka Office", "Mona Adel", "0100 777 8899", "2025-01-20"),
    (4, "Al Nokhba Office", "Karim Nasser", "0100 222 9900", "2026-09-01"),
]
ROUTES = [
    ("Tanta Centre", "Tanta centre", 1.00),
    ("Tanta Outskirts", "Tanta outskirts", 1.08),
    ("El Mahalla El Kubra", "El Mahalla", 1.05),
    ("Kafr El Zayat Rural", "Kafr El Zayat villages", 1.20),
    ("Zefta Mit Ghamr Road", "Zefta road", 1.15),
    ("Samannoud", "Samannoud", 1.10),
]
# id, name, office, route, base skill (success the da settles around), stops/day
DAS = [
    (1, "Karim Sobhy", 1, "Tanta Centre", 0.972, 145),
    (2, "Ahmed El Shenawy", 1, "Kafr El Zayat Rural", 0.958, 118),
    (3, "Mahmoud Radwan", 1, "Tanta Outskirts", 0.981, 138),
    (4, "Hassan Metwaly", 1, "El Mahalla El Kubra", 0.905, 142),
    (5, "Youssef Adel", 2, "El Mahalla El Kubra", 0.966, 136),
    (6, "Omar El Sherif", 2, "Samannoud", 0.928, 124),
    (7, "Sameh Fouad", 2, "Zefta Mit Ghamr Road", 0.949, 121),   # transfers to office 1 on 2026-10-01
    (8, "Ali Tarek", 3, "Tanta Centre", 0.889, 128),
    (9, "Khaled Mansour", 3, "Tanta Outskirts", 0.941, 119),
    (10, "Mostafa Nabil", 4, "Tanta Centre", 0.995, 46),          # Al Nokhba: tiny sample on purpose
]
TRANSFER = {7: (2, 1, "2026-10-01")}
LEAVES = [
    (2, "2026-10-05", "2026-10-09", "sick"),      # El Shenawy: the leave the checklist tests
    (2, "2026-09-21", "2026-09-22", "annual"),
    (6, "2026-09-28", "2026-09-28", "unexcused"),
    (9, "2026-10-12", "2026-10-14", "annual"),
]

def office_on(da_id, day):
    if da_id in TRANSFER:
        old, new, when = TRANSFER[da_id]
        return new if day >= date.fromisoformat(when) else old
    return next(d[2] for d in DAS if d[0] == da_id)

def on_leave(da_id, day):
    return any(c == da_id and date.fromisoformat(a) <= day <= date.fromisoformat(b)
               for c, a, b, _ in LEAVES)

def main():
    path = os.environ.get("CT_DB", DB_PATH)
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    # demo accounts. Printed in the README on purpose. Change before real use
    for uid, user, pw, role, off in [
            (1, "admin", "admin1234", "admin", None),
            (2, "dispatcher", "demo1234", "followup", 1),
            (3, "viewer", "viewer1234", "viewer", None)]:
        salt = secrets.token_bytes(16)
        conn.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                     (uid, user, salt.hex(), hash_password(pw, salt), role, off))
    conn.executemany("INSERT INTO offices VALUES (?, ?, ?, ?, ?)", OFFICES)
    conn.executemany("INSERT INTO routes VALUES (?, ?, ?)", ROUTES)
    for da_id, name, _off, _route, _skill, _stops in DAS:
        conn.execute("INSERT INTO couriers VALUES (?, ?, ?, ?, ?, ?, 21)",
                     (da_id, name, f"0100 300 44{da_id:02d}", "White van, plate SJB " + str(1200 + da_id),
                      "2025-06-01", ""))
    for da_id, name, off, route, skill, stops in DAS:
        if da_id in TRANSFER:
            old, new, when = TRANSFER[da_id]
            nxt = (date.fromisoformat(when) - timedelta(days=1)).isoformat()
            conn.executemany("INSERT INTO office_history (courier_id, office_id, from_date, to_date) VALUES (?, ?, ?, ?)",
                             [(da_id, old, START.isoformat(), nxt), (da_id, new, when, None)])
        else:
            conn.execute("INSERT INTO office_history (courier_id, office_id, from_date, to_date) VALUES (?, ?, ?, NULL)",
                         (da_id, off, START.isoformat()))
    conn.executemany("INSERT INTO leaves (courier_id, from_date, to_date, type) VALUES (?, ?, ?, ?)", LEAVES)

    day = START
    while day <= END:
        if day.weekday() != 4:  # Friday is the station day off
            for da_id, name, _o, route, skill, base_stops in DAS:
                if on_leave(da_id, day):
                    continue  # out of distribution — no row, no zero, no blame
                if da_id == 10 and (day < date(2026, 10, 12) or day.weekday() not in (5, 0, 2)):
                    continue  # Al Nokhba: new office on trial, one da, three days a week.
                              # Tiny totals are the whole point of him. The ranking must not crown him.
                assigned = int(base_stops * rng.uniform(0.88, 1.08))
                s = min(0.995, max(0.80, rng.gauss(skill, 0.018)))
                delivered = int(assigned * s * rng.uniform(0.96, 1.0))
                attempted = min(assigned - delivered, int(assigned * (1 - s) * 1.6) + rng.randint(0, 4))
                conn.execute(
                    "INSERT INTO daily_records (date, courier_id, office_id, route_name, assigned,"
                    " delivered, attempted_failed, returns, dnr, pod_good, pod_bad, fb_pos, fb_neg,"
                    " checkpoint_done) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (day.isoformat(), da_id, office_on(da_id, day), route, assigned, delivered,
                     attempted, rng.randint(0, 3), rng.choice([0, 0, 0, 1, 1, 2]),
                     int(delivered * rng.uniform(0.90, 0.99)), rng.randint(0, 5),
                     int(delivered * rng.uniform(0.55, 0.8)), rng.randint(0, 4),
                     int(assigned * rng.uniform(0.38, 0.68))))
        day += timedelta(days=1)

    conn.executemany("INSERT INTO followups (courier_id, office_id, kind, note, created_at, created_by) VALUES (?, ?, ?, ?, ?, ?)", [
        (4, 1, "coaching", "Talked to Hassan about his afternoon attempts; agreed he retries after 5pm", "2026-10-20 14:20", "dispatcher"),
        (8, 3, "call_da", "Ali had blurry POD photos three days running; warned and documented", "2026-10-21 11:05", "admin"),
        (7, 1, "escalation", "First week after the move from Al Salam; the Zefta route was split between two DAs", "2026-10-02 09:40", "admin"),
        (None, 2, "call_customer", "A customer in Samannoud is disputing a DNR; reviewed with the DA", "2026-10-19 16:30", "dispatcher"),
    ])
    conn.executemany("INSERT INTO safety_events (courier_id, type, occurred_at, disputed, outcome) VALUES (?, ?, ?, ?, ?)", [
        (4, "speeding", "2026-10-23 10:15", 0, None),          # inside the 48h window at demo time
        (4, "distraction", "2026-10-22 13:40", 1, "under review"),
        (8, "seatbelt", "2026-10-15 09:05", 0, "window closed"),
        (6, "following_distance", "2026-10-08 12:30", 1, "dispute accepted"),
        (1, "speeding", "2026-09-29 08:50", 1, "dispute rejected"),
    ])
    conn.executemany("INSERT INTO pod_flags (courier_id, date, issue) VALUES (?, ?, ?)", [
        (8, "2026-10-22", "blurry photo"), (8, "2026-10-22", "no house number in frame"),
        (8, "2026-10-21", "feet visible in frame"), (4, "2026-10-22", "blurry photo"),
        (3, "2026-10-22", "model photo"), (1, "2026-10-22", "model photo"),
    ])
    conn.executemany("INSERT INTO coaching_plans (courier_id, created_date, review_date, tasks, status) VALUES (?, ?, ?, ?, ?)", [
        (8, "2026-10-15", "2026-10-29", "Review POD photos every morning before leaving; retry any DNR after noon", "open"),
        (4, "2026-10-18", "2026-11-01", "Training on stop sequencing; 13:00 checkpoint call every day", "open"),
    ])
    conn.executemany("INSERT INTO rescues (date, from_courier, to_courier, stops, note) VALUES (?, ?, ?, ?, ?)", [
        ("2026-10-20", 4, 3, 18, "Hassan broke down in El Mahalla; Mahmoud finished his route and rescued 18 stops"),
        ("2026-10-13", 8, 9, 12, "Ali's van broke down; Khaled took the rest"),
        ("2026-09-30", 7, 5, 9, "The day before Sameh's transfer, Youssef covered the last of Zefta"),
    ])
    # invoices: billed days equal the recorded courier-days, except Al Baraka,
    # who bill 3 days nobody worked. The invoice check exists to catch exactly that.
    for off_id in (1, 2, 3, 4):
        actual = conn.execute(
            "SELECT COUNT(*) FROM (SELECT DISTINCT date, courier_id FROM daily_records"
            " WHERE office_id = ? AND date BETWEEN '2026-09-14' AND '2026-10-11')",
            (off_id,)).fetchone()[0]
        billed = actual + 3 if off_id == 3 else actual
        conn.execute("INSERT INTO invoices (office_id, period_from, period_to, billed_days, rate_per_day)"
                     " VALUES (?, '2026-09-14', '2026-10-11', ?, 850.0)", (off_id, billed))
    conn.executemany("INSERT INTO vehicle_checks (courier_id, date, van_ok, damage_note, next_maintenance) VALUES (?, ?, ?, ?, ?)", [
        (1, "2026-10-22", 1, "", "2026-11-05"), (2, "2026-10-22", 1, "", "2026-10-20"),
        (4, "2026-10-22", 0, "Scratch on the side door; photographed and logged", "2026-11-12"),
        (8, "2026-10-22", 1, "", "2026-10-25"),
    ])
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM daily_records").fetchone()[0]
    conn.close()
    print(f"Seeded {path}: {n} daily records, {START} -> {END}")

if __name__ == "__main__":
    main()
