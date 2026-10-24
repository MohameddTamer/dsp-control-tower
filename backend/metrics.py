# The maths the follow-up desk actually argues about.
# A percentage here is always stops weighted. Averaging courier percentages
# lets a da with 12 stops cancel out a da with 150, and that is not a table
# anyone should make decisions from.
# Leave days are cut before any ranking. A man on sick leave is not a bad
# courier. Counting his zero days against him poisons the table and the
# conversation that follows it.

MIN_SAMPLE = 100        # completed stops before a courier gets a rank
OFFICE_MIN_SAMPLE = 500  # offices move more paper; their bar is higher

def _pct(num, den):
    return round(100.0 * num / den, 1) if den else 0.0

def leave_days(conn, da_id):
    return {(r["from_date"], r["to_date"]) for r in
            conn.execute("SELECT from_date, to_date FROM leaves WHERE courier_id = ?", (da_id,))}

def _on_leave(spans, day):
    return any(a <= day <= b for a, b in spans)

def day_rows(conn, date_from, date_to, office_id=None):
    """Daily records in range, leave days already removed.
    Office on a row is the office the da belonged to THAT day (snapshot
    taken at seed/entry time) — a transfer never rewrites history."""
    sql = "SELECT * FROM daily_records WHERE date BETWEEN ? AND ?"
    args = [date_from, date_to]
    if office_id:
        sql += " AND office_id = ?"
        args.append(office_id)
    rows = [dict(r) for r in conn.execute(sql, args)]
    spans = {}
    out = []
    for r in rows:
        da = r["courier_id"]
        if da not in spans:
            spans[da] = leave_days(conn, da)
        if _on_leave(spans[da], r["date"]):
            continue  # record typed in by mistake during leave — it does not count
        out.append(r)
    return out

def totals(rows):
    t = {"assigned": 0, "delivered": 0, "attempted_failed": 0, "rts": 0,
         "dnr": 0, "pod_good": 0, "pod_bad": 0, "fb_pos": 0, "fb_neg": 0}
    for r in rows:
        for k in t:
            t[k] += r[k] if k != "rts" else r["returns"]
    t["completed"] = t["delivered"] + t["attempted_failed"]
    # DCR and success% are not the same number and mixing them up starts fights.
    # DCR: of everything he took out, how much came back delivered.
    # success%: of the stops that reached an outcome, how many were deliveries.
    t["dcr"] = _pct(t["delivered"], t["assigned"])
    t["success_rate"] = _pct(t["delivered"], t["completed"])
    t["dnr_rate"] = _pct(t["dnr"], t["delivered"])       # claims per delivered stop
    t["pod_score"] = _pct(t["pod_good"], t["pod_good"] + t["pod_bad"])
    t["feedback_score"] = _pct(t["fb_pos"], t["fb_pos"] + t["fb_neg"])
    t["rts_rate"] = _pct(t["rts"], t["assigned"])
    return t

def office_table(conn, date_from, date_to):
    offices = [dict(r) for r in conn.execute("SELECT * FROM offices ORDER BY name")]
    # previous equal-length period, for the trend arrow
    from datetime import date, timedelta
    d0, d1 = date.fromisoformat(date_from), date.fromisoformat(date_to)
    span = (d1 - d0).days + 1
    prev_to = d0 - timedelta(days=1)
    prev_from = prev_to - timedelta(days=span - 1)
    table = []
    for off in offices:
        rows = day_rows(conn, date_from, date_to, office_id=off["id"])
        t = totals(rows)
        prev = totals(day_rows(conn, prev_from.isoformat(), prev_to.isoformat(), office_id=off["id"]))
        das = {r["courier_id"] for r in rows}
        small = t["completed"] < OFFICE_MIN_SAMPLE
        table.append({**off, **t, "couriers_active": len(das),
                      "small_sample": small,
                      "trend": round(t["success_rate"] - prev["success_rate"], 1) if prev["completed"] else None})
    ranked = sorted([o for o in table if not o["small_sample"]],
                    key=lambda o: -o["success_rate"])
    for i, o in enumerate(ranked, 1):
        o["rank"] = i
    for o in table:
        o.setdefault("rank", None)  # small offices are listed, not decorated
    return sorted(table, key=lambda o: (o["rank"] is None, o["rank"] or 0, -o["success_rate"]))

def courier_table(conn, date_from, date_to, office_id=None):
    rows = day_rows(conn, date_from, date_to, office_id=office_id)
    by_da = {}
    for r in rows:
        by_da.setdefault(r["courier_id"], []).append(r)
    profiles = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM couriers")}
    offices = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM offices")}
    weights = {r["name"]: r["difficulty"] for r in conn.execute("SELECT name, difficulty FROM routes")}
    table = []
    for da_id, drows in by_da.items():
        t = totals(drows)
        # fairness lens: a failed stop on a hard rural route counts less against
        # the da than the same failure on a city route. Toggle, not gospel.
        adj_failed = sum(r["attempted_failed"] / weights.get(r["route_name"], 1.0) for r in drows)
        t["adjusted_rate"] = _pct(t["delivered"], t["delivered"] + adj_failed)
        spans = leave_days(conn, da_id)
        leave_in_range = 0
        from datetime import date, timedelta
        d = date.fromisoformat(date_from)
        while d <= date.fromisoformat(date_to):
            if _on_leave(spans, d.isoformat()):
                leave_in_range += 1
            d += timedelta(days=1)
        t["leave_days_in_range"] = leave_in_range
        table.append({**profiles[da_id], **t,
                      "office_name": offices.get(drows[-1]["office_id"]),
                      "small_sample": t["completed"] < MIN_SAMPLE})
    ranked = sorted([c for c in table if not c["small_sample"]], key=lambda c: -c["success_rate"])
    for i, c in enumerate(ranked, 1):
        c["rank"] = i
    for c in table:
        c.setdefault("rank", None)
        c["band"] = ("fantastic" if c["success_rate"] >= 98 else
                     "great" if c["success_rate"] >= 95 else
                     "fair" if c["success_rate"] >= 90 else "poor")
    return sorted(table, key=lambda c: (c["rank"] is None, c["rank"] or 0, -c["success_rate"]))

def daily_curve(conn, date_from, date_to, office_id=None, courier_id=None):
    rows = day_rows(conn, date_from, date_to, office_id=office_id)
    if courier_id:
        rows = [r for r in rows if r["courier_id"] == courier_id]
    by_day = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r)
    return [{"date": d, **totals(by_day[d])} for d in sorted(by_day)]

def worst_areas(conn, date_from, date_to, office_id):
    rows = day_rows(conn, date_from, date_to, office_id=office_id)
    by_route = {}
    for r in rows:
        by_route.setdefault(r["route_name"], []).append(r)
    out = [{"route": name, **totals(rs)} for name, rs in by_route.items()]
    return sorted(out, key=lambda x: x["success_rate"])

def checkpoint_alerts(conn, day):
    """13:00 checkpoint. Under 45% of the route done by one o'clock with a
    full route assigned means the day is already lost unless someone calls."""
    rows = day_rows(conn, day, day)
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM couriers")}
    offices = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM offices")}
    alerts = []
    for r in rows:
        if r["assigned"] >= 40 and r["checkpoint_done"] / r["assigned"] < 0.45:
            alerts.append({"courier": names[r["courier_id"]], "courier_id": r["courier_id"],
                           "office": offices.get(r["office_id"]), "type": "behind schedule",
                           "detail": f"{r['checkpoint_done']}/{r['assigned']} stops done before the 13:00 checkpoint"})
        rate = _pct(r["delivered"], r["delivered"] + r["attempted_failed"])
        if r["delivered"] + r["attempted_failed"] >= 20 and rate < 92:
            alerts.append({"courier": names[r["courier_id"]], "courier_id": r["courier_id"],
                           "office": offices.get(r["office_id"]), "type": "rate down",
                           "detail": f"success rate {rate}% over {r['delivered'] + r['attempted_failed']} completed stops"})
    return alerts

def performer_share(conn, end_date):
    """Amazon reads people over a trailing 6 weeks, not over one bad day.
    Eligible: da worked in at least 4 of the last 6 weeks.
    High: Great/Fantastic in 4+ of those weeks. Low: Poor in 4+."""
    from datetime import date, timedelta
    end = date.fromisoformat(end_date)
    weeks = []
    for w in range(6):
        wk_end = end - timedelta(days=7 * w)
        wk_start = wk_end - timedelta(days=6)
        weeks.append((wk_start.isoformat(), wk_end.isoformat()))
    das = [r["id"] for r in conn.execute("SELECT id FROM couriers")]
    high = low = eligible = 0
    detail = {}
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM couriers")}
    for da in das:
        bands = []
        for a, b in weeks:
            t = totals([r for r in day_rows(conn, a, b) if r["courier_id"] == da])
            if t["completed"]:
                bands.append("fantastic" if t["success_rate"] >= 98 else
                             "great" if t["success_rate"] >= 95 else
                             "fair" if t["success_rate"] >= 90 else "poor")
        if len(bands) < 4:
            continue
        eligible += 1
        hi = sum(1 for x in bands if x in ("fantastic", "great"))
        lo = sum(1 for x in bands if x == "poor")
        if hi >= 4:
            high += 1; detail[names[da]] = "high"
        elif lo >= 4:
            low += 1; detail[names[da]] = "low"
    return {"eligible": eligible, "high": high, "low": low,
            "high_share": _pct(high, eligible), "low_share": _pct(low, eligible),
            "detail": detail, "weeks_used": 6}
