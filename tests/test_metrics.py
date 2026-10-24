#!/usr/bin/env python3
# Tests for the maths that can embarrass you in front of a station manager.
# Every number below was worked out by hand first; the test exists because
# the next person to touch metrics.py will not redo that arithmetic.
import os, sqlite3, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from seed import SCHEMA
import metrics

def fixture():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd); os.remove(path)
    conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO offices VALUES (?, ?, '', '', '2024-01-01')",
                     [(1, "Al Nour",), (2, "Al Salam",), (3, "Al Sagheer",)])
    conn.executemany("INSERT INTO routes VALUES (?, '', ?)",
                     [("City", 1.0), ("Rural", 1.25)])
    conn.executemany("INSERT INTO couriers (id, name) VALUES (?, ?)",
                     [(i, f"da{i}") for i in range(1, 8)])
    conn.executemany("INSERT INTO office_history (courier_id, office_id, from_date, to_date) VALUES (?, ?, ?, ?)",
                     [(1, 1, "2026-09-01", None), (2, 1, "2026-09-01", None),
                      (3, 2, "2026-09-01", None),
                      (4, 2, "2026-09-01", "2026-09-30"), (4, 1, "2026-10-01", None),
                      (5, 3, "2026-09-01", None), (6, 2, "2026-09-01", None), (7, 2, "2026-09-01", None)])
    conn.execute("INSERT INTO leaves (courier_id, from_date, to_date, type) VALUES (3, '2026-10-03', '2026-10-04', 'sick')")
    def rec(day, da, off, route, assigned, delivered, failed):
        conn.execute("INSERT INTO daily_records (date, courier_id, office_id, route_name, assigned,"
                     " delivered, attempted_failed, returns, dnr, pod_good, pod_bad, fb_pos, fb_neg,"
                     " checkpoint_done) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 60)",
                     (day, da, off, route, assigned, delivered, failed))
    rec("2026-10-01", 1, 1, "City", 100, 90, 10)
    rec("2026-10-02", 1, 1, "City", 100, 95, 5)
    rec("2026-10-01", 2, 1, "Rural", 100, 80, 20)
    rec("2026-10-02", 3, 2, "City", 50, 50, 0)
    rec("2026-10-03", 3, 2, "City", 50, 0, 50)    # typed in while he was on sick leave — must vanish
    rec("2026-09-30", 4, 2, "City", 40, 30, 10)   # before the transfer: Al Salam's numbers
    rec("2026-10-02", 4, 1, "City", 60, 60, 0)    # after the transfer: Al Nour's numbers
    rec("2026-10-01", 5, 3, "City", 10, 9, 1)     # tiny sample office
    rec("2026-10-10", 6, 2, "Rural", 100, 80, 20)    # hard route: raw 80%
    rec("2026-10-10", 7, 2, "City", 100, 82, 18)  # city route: raw 82%
    conn.commit()
    return conn

def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        raise SystemExit(1)

c = fixture()

# weighted office %: Al Nour = (185 + 80 + 60) delivered / (200 + 100 + 60)
# completed = 325/360 = 90.3, not the naive average of the three courier
# percentages (92.5 + 80 + 100) / 3 = 90.8
off = {o["name"]: o for o in metrics.office_table(c, "2026-10-01", "2026-10-02")}
check("office % is stops-weighted (90.3)", off["Al Nour"]["success_rate"] == 90.3)
check("transfer day counted for the new office", off["Al Nour"]["delivered"] == 325 and off["Al Nour"]["completed"] == 360)

# leave: da3's sick-leave record must not exist as far as numbers are concerned
rows = metrics.day_rows(c, "2026-10-01", "2026-10-04")
da3 = [r for r in rows if r["courier_id"] == 3]
check("leave-day record excluded", len(da3) == 1 and da3[0]["delivered"] == 50)

# transfer history: Al Salam keeps the September work, Al Nour does not inherit it
off_sept = {o["name"]: o for o in metrics.office_table(c, "2026-09-28", "2026-10-04")}
check("old office keeps pre-transfer numbers", off_sept["Al Salam"]["delivered"] == 80 and off_sept["Al Salam"]["completed"] == 90)

# small sample: listed, flagged, unranked
check("small office flagged and unranked",
      off["Al Sagheer"]["small_sample"] is True and off["Al Sagheer"]["rank"] is None)

# a day with no stops must divide by nothing and survive
check("empty totals are zeros, not a crash", metrics.totals([])["success_rate"] == 0.0)

# fairness: raw rate says city da (82) beats rural da (80);
# difficulty-adjusted says the rural da did the harder job (83.3 vs 82.0)
ct = {x["id"]: x for x in metrics.courier_table(c, "2026-10-10", "2026-10-11", office_id=2)}
check("raw rates as expected", ct[6]["success_rate"] == 80.0 and ct[7]["success_rate"] == 82.0)
check("difficulty weighting flips the order", ct[6]["adjusted_rate"] == 83.3 and ct[7]["adjusted_rate"] == 82.0)

# date ranges actually move the numbers
a = metrics.totals(metrics.day_rows(c, "2026-10-01", "2026-10-01"))
b = metrics.totals(metrics.day_rows(c, "2026-10-01", "2026-10-02"))
check("wider range, more stops", b["completed"] > a["completed"])

print("all metrics tests passed")
