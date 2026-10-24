# Critique — DSP Control Tower v2 judged against its own spec

Written after the build, per the owner's completion rule: study it,
critique it, list the gaps, fix them, and only then call it done.
Every item below was run, not assumed. Commands were run on
2026-10-24 against a fresh seed.

## Spec checklist

1. **Weighted office percentages — PASS.**
   Verified two independent ways. By hand on the fixture in
   tests/test_metrics.py: Al Nour 325 delivered / 360 completed = 90.3,
   where the naive average of courier percentages gives 90.8.
   Against the real seed by raw SQL, computed outside the app code:
   Al Nour 18,235 delivered / 19,629 completed = 92.9. The metrics module
   returned the same three numbers exactly.

2. **Date range changes every number — PASS.**
   API test compares office totals for 2026-09-14..2026-10-22 against
   2026-10-19..2026-10-22 and asserts they differ. Spot check on the
   couriers screen: Karim Sobhy carries 4,766 assigned stops over the full
   range and 537 over the last four days. The office page, courier page,
   TV board and both CSV exports take the same from/to parameters.

3. **Leave exclusion — PASS.**
   Fixture test: a record typed in for da3 on a sick day (0 delivered,
   50 failed) does not exist as far as the numbers are concerned; his
   range shows only his real day, 50/50. Seed check: Ahmed El Shenawy has
   zero records inside his sick leave 2026-10-05..2026-10-09, the
   planner for 2026-10-06 lists him as on leave and out of supply, and
   his profile reports annual leave used 2, balance 19 of 21.

4. **Office transfer keeps history — PASS.**
   Sameh Fouad moved from Al Salam to Al Nour on 2026-10-01. Raw counts:
   15 working days and 1,671 delivered under Al Salam before the move,
   19 days and 2,120 under Al Nour after it, and zero rows under Al Nour
   dated before the transfer. His profile shows both history entries
   with their dates.

5. **Small sample flag — PASS, after a real failure was caught and fixed.**
   First run of the API tests failed this item. Al Nokhba Office was over the
   100 stop threshold because one da at 46 stops a day passes 100 inside
   three days. Two fixes: offices got their own threshold (500 completed
   stops in range), and the trial office's da works three days a week
   from 2026-10-12, which is the arrangement the demo means to model.
   Final numbers: Al Nokhba completes 226 stops at a 96.0 percent success
   rate, the highest raw rate in the station, and holds rank null with
   the small sample flag on. The guard is doing exactly its job.

6. **Security — PASS.**
   From tests/test_api.py against a booted server: 401 with no token,
   401 on a wrong password, 401 on the username admin' OR '1'='1,
   403 when the viewer account tries to write, 403 when the follow-up
   agent asks for the audit trail, office scoping returns exactly one
   office for the follow-up account, an edited daily record appears in
   the audit trail with its old and new values, and the users table
   holds a 64 character hash with a 32 character salt, not a password.

7. **Screens served and checked — PASS with one honest limit.**
   In v2 the page was Arabic, lang ar, dir rtl, served 200 by the app,
   with the embedded script passing node --check. The v3 redesign at the
   end of this file supersedes the language and layout halves of this
   item: the page is now English, LTR, and checked the same way.
   Layout was verified in markup and CSS (grid collapses to one and
   two columns under 900px), not in a real device browser. Nobody here
   rendered it on a phone, so phone rendering is claimed as responsive
   design, not as device tested.

## Researched additions A to L

A Amazon metric language: PASS. DCR, DNR rate, POD score and customer
  feedback score are computed in totals() and shown for offices,
  couriers and profiles.
B POD board: PASS. Fame and shame top threes for the picked day plus the
  day's flags from pod_flags.
C Safety log with 48 hour dispute clock: PASS. Live check showed the
  2026-10-23 speeding event open with 30.5 hours left, an older event
  expired, and disputes recorded with state changes. Limit: the clock
  is wall clock, so the seeded windows read right around late October
  2026 and read expired after that. Recorded in the README too.
D Coaching plans and trailing 6 weeks share: PASS. Performer share over
  the range ending 2026-10-22: 9 eligible das, high share 11.1 percent
  (Mahmoud Radwan), low share 22.2 percent (Hassan Metwaly, Ali Tarek). Two open
  plans with review dates. Limit: with 5.7 weeks of demo data the sixth
  week is partial; eligibility requires four worked weeks, which is the
  conservative read.
E Rescues: PASS, three seeded rescues with credit to the rescuer,
  listed per range.
F Route fairness weighting: PASS. Fixture test shows the rural da at
  raw 80.0 rising to an adjusted 83.3 and passing the city da at 82.0.
  It is a shown lens next to the raw rate, never a replacement for it.
G Invoice check: PASS. Al Baraka billed 3 courier days nobody worked:
  variance 3 days, 2,550 at the seeded day rate. Other offices at zero.
H Tomorrow planner: PASS. Volume in, average stops per da from the last
  seven data days, das needed, allocation per office, leave list.
I WhatsApp summary: PASS as text generation. Nothing is sent anywhere;
  the endpoint returns the summary text and the page shows it in a box.
  (The text was Arabic in v2; v3 generates it in English, see below.)
J TV board: PASS. Range driven leaderboard screen with large type.
K Audit trail: PASS. Writes on records, leaves, follow-ups and disputes
  all land there with user, time, field, old and new. Admin only.
L Vehicle log: PASS. Morning checks list plus a maintenance due list
  (one van already inside the 7 day window in the seed).

## Code authenticity pass

Read through every file once as a stranger, looking for the smell.

Comments were rewritten to plain sentences. No comment in the code
carries a list, a banner row of dashes, or an em dash; the scan for
those patterns returns nothing. What comments remain are the ones a
person leaves when a decision is not obvious from the code: why the
percentage is weighted, why leave is cut before ranking, why DCR and
success rate are different numbers, the Friday closure inside the seed.

Names come from the floor: da, rts, dnr, checkpoint. The glossary lives
in the README instead of renaming the code into textbook words.

The tests test the arguments a station manager would start: weighted
percentages, leave days, a transfer in the middle of a range, a small
office, an empty day, and a hard route beating an easy one once the
weighting is honest. Nothing tests a getter.

Structure grew the way real projects grow: metrics split out of the
server when the maths got its own opinions, one utility module, a
changelog with short human entries, limits written in the README where
a reader will find them instead of being hidden.

## Gaps found during this critique and what happened to them

- Small office was not small. Fixed in code and seed, item 5 above.
- The profile page read a hard coded year when totalling annual leave.
  Fixed to take the year of the range being viewed.
- A search test from curl returned empty and looked like a bug.
  It was not one: browsers percent encode the query and the endpoint
  answers correctly, which was verified with an encoded request that
  returned Ahmed El Shenawy. The endpoint expects encoded input, like
  every endpoint on the web.
- The follow-up role kept its role after a page refresh only through
  /api/me, which did not exist in the first cut. Added and used at boot.

## What is honestly not done

- No public deployment. Local only, by the owner's gate.
- No device browser rendering test, see item 7.
- Login rate limiting is not implemented. SECURITY.md says so.
- The demo database file is regenerated by seed.py; it is in .gitignore
  and is not a deliverable.

## Redesign — v3, English-only dense data terminal (2026-10-24)

The owner rejected the v2 skin as a design he had seen before and
ordered two things: everything user facing in English, and a front end
from the current design world instead of the shared recipe. The mapping
in DESIGN-RESEARCH.md sends this project to the Dense Pro Data
Terminal. DESIGN.md in this folder is the design record.

What changed:
- frontend/index.html rebuilt: lang en, LTR, near-black layered
  surfaces, hairlines instead of cards, no border radius anywhere,
  Archivo + IBM Plex Mono from Google Fonts with system fallbacks, a
  scrolling station wire under the instrument bar, sparklines inside
  the office ranking cells, keyboard-first operation (/ focuses
  search, j/k walks the courier table, Enter opens the file), values
  flash once for 150ms when a range change moves them, and the board
  recomputes on range change. The KPI stat-card row is deleted; the
  station totals now sit on one ruled readout strip.
- Native controls styled end to end: dark color-scheme date inputs
  with a tinted picker indicator, and the CSV file input is a labelled
  terminal button with the chosen file name in mono. Nothing raw from
  the browser shows.
- Seed display text re-rendered in English: Al Nour, Al Salam,
  Al Baraka and Al Nokhba offices, English courier and route names,
  English notes, outcomes, flags, plan tasks and rescue notes. The
  setting stays Tanta, Egypt, in English words. The maths, the random
  seed and every fact in the data are untouched.
- Backend-generated strings are English now: checkpoint alert types
  and details in metrics.py, the dispute outcome, and the WhatsApp
  summary text in app.py.
- Tests updated where they asserted the old strings (office names,
  the served-page check, the WhatsApp text). One check was added:
  the API test now asserts the top office by name and number.

Evidence:
- Tests before the redesign: test_metrics 9 checks, test_api 16,
  test_deepening 42 — 67 passing. After: 9, 17, 42 — 68 passing,
  the extra one being the new numbers proof. Nothing was deleted to
  make a failure go away.
- Numbers unchanged, verified outside the app code on a reseeded
  database: Al Nour Office 18,235 delivered / 19,629 completed =
  92.9 percent, rank 1, exactly as before the conversion. Al Nokhba
  still 217 / 226 = 96.0 percent, small sample, rank null. Al Baraka
  still billed 51 days against 48 recorded: variance 3 days, 2,550 EGP
  at the seeded rate. Daily record count still 301.
- A scan of the project tree finds zero Arabic characters in code,
  page, tests and docs after the conversion.

Honest notes on the direction:
- The sparkline in the office table costs one extra API call per
  office per render. With four offices that is nothing; with forty it
  would want a curve field on the list endpoint instead. Recorded
  here rather than hidden.
- The ticker is a CSS marquee of live values, duplicated once for the
  loop. It stops under prefers-reduced-motion and is aria-hidden,
  because the same numbers sit in the readout strip for anyone who
  needs them still.
- The flash-on-change covers the readout strip and the ranking
  tables' success cells, not every number on every screen. Extending
  it everywhere would turn the one signal into noise, which is the
  failure mode the direction warns about.
- As before, the page was verified in markup, CSS and script syntax
  (node --check on both script blocks), and by the API tests that read
  it from the booted server — not rendered in a device browser here.
