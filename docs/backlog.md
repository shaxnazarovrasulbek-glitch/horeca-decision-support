# Product backlog: final internship sprint (16–22 Oct 2026)

Status as of the start of the sprint. Update the status column as work progresses.

## Epics

| ID | Epic | Goal |
|---|---|---|
| E1 | Data foundation | Realistic POS data plus upload of real exports |
| E2 | Demand forecasting | Know how busy each branch will be, by day and hour |
| E3 | Revenue levers | Menu, price and upsell decisions with money impact |
| E4 | Operations | Staff and purchasing driven by the forecast |
| E5 | AI assistant | Plain-language answers and a weekly briefing |
| E6 | Evaluation and delivery | Measured results, documentation, demo, report |

## User stories

| ID | As a manager I want… | Acceptance criteria | Epic | Status |
|---|---|---|---|---|
| US-01 | demo data for two branches | 1 year of order lines; holidays, Ramadan, weather, promos, price changes, pairings, incidents | E1 | Done |
| US-02 | to upload my own POS CSV | required/optional columns validated; clear error messages | E1 | Done |
| US-03 | KPIs vs the previous period | revenue, orders, guests, avg check, food cost, margin, with deltas | E1 | Done |
| US-04 | alerts for unusual days with a likely cause | planted outage detected, with its hours | E1 | Done |
| US-05 | a 7–14-day revenue / guest forecast | per branch, 80% range, holidays marked | E2 | Done |
| US-06 | to know if the forecast is better than my rule of thumb | rolling-origin back-test vs 2 baselines | E2 | Done |
| US-07 | a what-if for a marketing campaign | toggle changes the forecast | E2 | Done |
| US-08 | to know which dishes to keep, fix, promote or remove | Kasavana–Smith per section, action per dish | E3 | Done |
| US-09 | price recommendations I can trust | elasticity with confidence; tests proposed when uncertain | E3 | Done |
| US-10 | upsell scripts and combos valued in UZS | rules with lift; monthly value by acceptance rate | E3 | Done |
| US-11 | a staff schedule from the forecast | waiters and cooks per hour; savings vs a fixed schedule | E4 | Done |
| US-12 | a purchase list for next week | forecast × recipes + safety stock | E4 | Done |
| US-13 | proof that forecast-based ordering reduces waste | 4-week simulation vs a naive rule | E4 | Done |
| US-14 | to ask questions in EN / RU / UZ | Gemini answers from computed facts; offline fallback | E5 | Done |
| US-15 | a one-click weekly briefing | performance, alerts, top actions with UZS impact | E5 | Done |
| US-16 | all results in one place for the report | Evaluation page and `scripts/evaluate.py` | E6 | Done |
| US-17 | the code on GitHub with documentation | README, architecture, tests, run scripts | E6 | In progress |
| US-18 | a recorded demo video (5–7 min) | recorded before 22 Oct | E6 | To do |
| US-19 | the internship report and signed feedback form | uploaded to Learn by 25 Oct | E6 | To do |

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Gemini free quota exhausted during the demo | Assistant stops | Automatic offline fallback; model is configurable |
| No real POS data before the defense | Weaker external validity | Ground-truth checks on synthetic data; pilot planned; upload ready |
| Live demo fails (network, laptop) | Bad impression | Recorded backup video; app runs fully offline |
| Little time left (6 days) | Scope cut | Scope frozen to the stories above; "next steps" documented |

## Next (after the internship)

- Pilot with a real restaurant POS export (iiko / R-Keeper / Poster)
- Telegram bot that sends the daily briefing
- Weather API for the forecast; hotel (rooms + F&B) module
