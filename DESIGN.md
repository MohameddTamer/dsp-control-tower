# Design, DSP Control Tower

## Concept

A control tower is not a website. The screen is a wall of live
instruments: every office, every courier, every alert visible at once,
and the eye, not the mouse, does the searching. This page is built
like a Bloomberg-class operations terminal that happens to run a
delivery station in Tanta: density is the aesthetic, and restraint
with color is what keeps the density readable at hour six of a shift.

## Palette

| Role | Hex | Where it lives |
|---|---|---|
| Void | `#0A0C0A` | Page background, the deepest layer |
| Panel | `#10140F` | Instrument bar, panels |
| Panel raised | `#161B14` | Buttons, hover rows, the readout strip |
| Hairline | `#263026` | Every divider. Panels are separated by lines, never by shadow |
| Hairline faint | `#1B241B` | Row rules inside tables |
| Text | `#D8E2D4` | Primary reading color |
| Dim | `#7E8F79` | Labels, metadata, secondary text |
| Phosphor | `#7BD88F` | The one accent: healthy values, active screen, the brand mark |
| Amber | `#E8B33D` | Data only, a rate slipping, a window still open |
| Red | `#E5534B` | Data only, alerts, variances, closed windows |

Amber and red never appear as surface color. If everything is calm,
the screen is phosphor and grey-green; color arriving means something
happened.

## Type pairing

- **Archivo** (500 to 800) for labels, screen names and micro-headers,
  always uppercase with wide tracking. Fallbacks: Helvetica Neue,
  Arial, sans-serif.
- **IBM Plex Mono** (400 to 600) for every number, ID, timestamp and
  input value. Tabular by birth; `font-variant-numeric: tabular-nums`
  is set globally as a second lock. Fallbacks: ui-monospace, SF Mono,
  Consolas.

Sizes run from 9.5px micro-labels to a 23px strip readout, on a
deliberately narrow ladder, a terminal has few text sizes and uses
them consistently, which is most of why it reads as one instrument.

## Signature layout move

The fixed instrument grid: a brand and controls bar, a scrolling
station wire under it, numbered screens (01 to 11), and inside each
screen, panels stacked full width and separated by hairlines. Station
totals live on a single ruled readout strip, a line of instruments,
not a row of cards. The office ranking carries a sparkline of daily
success inside the table itself, so trend is read in the same glance
as rank.

## Signature interaction

Keyboard-first, and values that flash. `/` focuses search from
anywhere. On the couriers screen, `j`/`k` walks the table and Enter
opens the DA file. Change the date range and the board recomputes on
the spot; any readout or ranking success figure that moved flashes
once, a 150ms phosphor wash, so the eye lands exactly on what the
new range changed. Nothing else animates, except the wire, and both
stop under `prefers-reduced-motion`.

## The brand mark

A signal mast, drawn in SVG strokes at 1.7px: two legs, one crossbar,
a solid phosphor dot for the lamp, and a single radiating arc. It is
the only illustration in the product, which is the point, a terminal
earns one mark, not a mascot.

## Deliberately avoided

Everything on the portfolio anti-list, and specifically for this
direction: the KPI stat-card row (banned outright here), cards of any
kind, border radius (zero, everywhere), pill badges (states are
bracketed mono text: `[OPEN, 12.5H LEFT]`), soft shadows, the
indigo-to-violet gradient, emoji as icons, unstyled native controls
(date inputs are dark-scheme and tinted; the file input is a labelled
button with the file name beside it), and dark-mode-as-costume,
the dark here is layered surfaces and data behavior, not a blue
accent on grey cards. It also avoids the cheap version of its own
direction: no green-on-black hacker cosplay, because the density is
real data, all of it on screen, all of it computed live.
