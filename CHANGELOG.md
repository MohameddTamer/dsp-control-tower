# Changelog

## v3 — 2026-10-24

English-only rebuild of everything user facing, and a new skin with a
point of view. The page is now a dense pro data terminal: near-black
layered surfaces, hairlines instead of cards, a scrolling station wire,
sparklines inside the office ranking, keyboard-first navigation
(/ finds, j/k walks the courier table), and values that flash once when
a range change moves them. Archivo for labels, IBM Plex Mono for every
number. The KPI stat-card row is gone on purpose. Seed names and notes
were re-rendered in English (the station is still in Tanta; the people
are still invented), the WhatsApp summary generates in English, and
every known number is unchanged: Al Nour Office still computes 92.9
percent on the same seed facts. DESIGN.md records the direction.

## v2.1 — 2026-10-24

The deepening round. CSV import for daily records with a named skipped rows report, a printable weekly report, admin backup with a timestamped database copy, live config readout, a rotating log file, and environment variable configuration. Forty two new checks in tests/test_deepening.py cover the import report, the backup file and the config.

## v2 — 2026-10-24

Rebuilt around how the work actually runs. Offices between the station
and the couriers, everything computed over a picked date range, leave
that removes a man from the numbers instead of punishing him, transfers
that keep history where it was earned.

Added the researched layer: DCR and DNR and POD as first class numbers,
the photo board, safety events with the 48 hour dispute clock, coaching
plans, rescues, the invoice check, the tomorrow planner, the TV board,
the audit trail.

Caught while testing: the small office was not small. One da at 46 stops
a day stops being a small sample inside two weeks, so offices got their
own threshold and the trial office got a three day week. The numbers in
CRITIQUE.md are the ones that proved it.

## v1 — 2026-10-24

First working draft. One screen, couriers only, no offices, no dates
worth the name. Proved the shape, then got replaced.
