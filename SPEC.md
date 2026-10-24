# DSP Control Tower — Specification (v3, awaiting owner approval before build)

Status: IDEA STAGE. Per owner's process rule: idea first, his word, then build.
Nothing in this spec is built yet beyond the local v1 draft, which is NOT published.

## Structure of the operation (how it really works)

Station / DSP
  -> Outsourcing offices (each courier belongs to exactly one office)
      -> Couriers (delivery associates)

Every number in the system can be viewed at all three levels.

## Core rule added by owner (2026-10-24)

EVERY classification, ranking, and percentage in the system is computed
over a date range the user picks (from day X to day Y). No fixed "this
week only" numbers. The date-range picker sits at the top of every
screen and everything below it obeys it.

## Offices

- Each office has a profile: name, contact person, phone, how many
  couriers it supplies, since when.
- Office percentage = weighted by stops, NOT an average of courier
  percentages (a courier with 10 stops must not count like one with 150).
  Formula: total delivered / total completed outcomes across all the
  office's couriers in the chosen range.
- Office ranking table: rank, office, couriers count, stops, delivered,
  success %, returns %, trend vs the previous equal-length period.
- Fairness guard: offices under a minimum stop threshold in the range
  are listed but marked "sample too small" and kept out of the medals,
  so a tiny office cannot top the ranking by luck.
- Clicking an office opens its own page: its couriers ranked best to
  worst inside the office (same date range), its daily curve, its worst
  areas, its returns.

## Couriers

- Full profile: name, phone, office, main route, vehicle, start date,
  notes. A courier can move between offices; the move is dated, and
  historical numbers stay with the office he belonged to at that time.
- Daily detail: assigned, delivered, failed attempts with reason each,
  returns, success % for day / range, performance curve.
- Leave and absence: leave ranges by type (annual, sick, unpaid,
  unexcused absence). On leave, a courier leaves the route distribution
  automatically and his absence never counts against his percentages.
  Leave balance per courier is visible on his profile.

## Follow-up and alerts

- Follow-up log per courier and per office: calls, escalations, coaching,
  with time and outcome.
- Mid-day alerts tied to real checkpoint times, not just totals.
- Alerts can be filtered by office, so a follow-up agent who owns one
  office's couriers sees only his own fires.

## Roles and design

- Roles: admin (everything), follow-up agent (sees assigned offices),
  viewer (read-only).
- Arabic-first interface with RTL, dark clean ops-room design.
- Search any courier or office. Export any table (same date range) to CSV.

## Proposed additions from research (2026-10-24, awaiting owner's pick)

Researched from public Amazon DSP scorecard material and DSP
performance-tracking guides. NOT yet approved, NOT built.

A. Amazon's own metric language built in: DCR (delivery completion
   rate), DNR/DAR (delivered and not received), POD (photo on
   delivery quality), customer delivery feedback. Couriers and
   offices get these, not just a generic success %.
B. POD photo quality board: bad-photo flags (blurry, no house
   number, feet in frame) and a daily wall of fame / shame for load-out.
C. Safety log: speeding, distraction, seatbelt events per courier,
   with a 48-hour dispute deadline tracker so events get challenged
   in time instead of silently costing the scorecard.
D. Coaching / improvement plans: a courier banded Fair or Poor gets a
   time-bound plan with tasks and a review date. High/low performer
   share computed over a trailing 6 weeks, the way Amazon reads it.
E. Rescues: mid-day stop transfers between couriers are logged, the
   rescuer gets credit, the rescued courier's numbers stay honest.
F. Route fairness weighting: a hard rural route and an easy city
   route are not ranked as if they were the same job.
G. Office invoice check: what an office bills (courier-days) against
   what the system recorded (attendance minus leave). Money feature.
H. Tomorrow planner: expected volume -> couriers needed -> how many
   each office must supply tomorrow morning.
I. Daily WhatsApp summary to each office owner: his office's numbers
   for the day, no login needed on his side.
J. Station TV board: live leaderboard screen for the station floor.
K. Audit trail: who changed any number, when, from what to what.
   Rankings nobody can quietly edit.
L. Vehicle log: morning van check per courier, damage photos noted,
   maintenance reminders by date.

## Critique checklist (must pass before anyone says "done")

1. Weighted office percentages verified against hand-computed numbers.
2. Date range changes every number on screen; test with two ranges.
3. A courier on leave shows zero penalty and is out of distribution.
4. Office transfer mid-range keeps history with the old office.
5. Small-sample offices flagged, not ranked as champions.
6. Security tests: no data without login, wrong password rejected,
   injection attempt rejected, passwords hashed (see SECURITY.md).
7. Every screen usable in Arabic RTL without broken layout.
