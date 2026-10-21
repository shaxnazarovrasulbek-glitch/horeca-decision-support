# Real-world validation plan

This plan answers the three growth points from the PM mentor review (21 Oct 2026):

1. Use a pilot with real restaurant sales data to check that the results translate into real operational and financial impact.
2. Assess the recommendations with the intended users (branch and operations managers) and collect structured feedback.
3. Check how the solution scales to more restaurants, larger datasets and broader operations.

## 1. Pilot with real data (6 weeks)

| Item | Plan |
|---|---|
| Partner | One restaurant chain in Tashkent with at least 2 branches and a POS system (iiko, R-Keeper or Poster) |
| Data | 12 months of POS order lines (CSV export), menu with prices and food cost, recipes for the top 30 dishes, staff schedule. No guest personal data is needed. |
| Design | **Weeks 1–2: baseline.** Both branches work as usual; the platform only forecasts (shadow mode) so we can measure accuracy. **Weeks 3–6: A/B.** Branch A uses the platform for staffing, purchasing, upsell scripts and price tests; branch B works as usual. Swap the branches for 2 more weeks if the partner agrees. |
| Weekly rhythm | Monday: the manager gets the weekly briefing and the purchase list. Friday: a 15-minute review call (results, feedback, issues). |
| Owner | Rasulbek Shaxnazarov (project manager and analyst); the branch manager is the business owner of the decisions. |

### KPIs and success criteria

The targets are lower than the results on synthetic data on purpose, because real data is noisier.

| KPI | How it is measured | Success target |
|---|---|---|
| Forecast error (WAPE, daily revenue and guests) | Forecast vs actual, weeks 1–6 | ≤ 15% and better than the manager's own rule |
| Perishable waste | Write-offs in UZS, A vs B and vs baseline | −15% |
| Staff-hours | Scheduled hours vs baseline, with no more understaffed peak hours | −5% |
| Margin from upsell and price actions | Attach rate of the scripted items; margin of tested dishes | Positive and measurable per week |
| Manager usefulness score | 👍 / 👎 on every recommendation in the app | ≥ 70% rated useful |
| Adoption | Share of weekly recommendations the manager actually applied | ≥ 50% |

**Decision gate after week 6:** go to more restaurants if at least 4 of the 6 targets are met and the manager wants to keep using the platform. Otherwise, fix the weak module first and repeat the pilot.

## 2. Structured feedback from managers

| Method | When | What we learn |
|---|---|---|
| **In-app rating:** 👍 / 👎 plus a comment on each recommendation, with the user's role. Saved to `data/feedback_log.csv` and summarised on the Evaluation page. | Every day | Which modules are useful, and why not |
| **Weekly 15-minute interview** (3 questions): Which recommendation did you apply? What happened? What was missing or wrong? | Every Friday | Context behind the ratings, new requirements |
| **End-of-pilot survey** (1–5 scale): (1) The recommendations helped me decide faster. (2) They were correct for my branch. (3) The money values (UZS) were believable. (4) The app is easy to use. (5) I trust the AI assistant's answers. (6) I will keep using it. Plus 2 open questions: the most useful feature, and the biggest problem. | Week 6 | Usefulness, ease of use, trust, intention to use |

Participants: 2 branch managers, 1 operations manager, the owner or director, and 1–2 shift leads (5–6 people).

## 3. Scale

* **Measured now:** `scripts/scale_test.py` runs the full analysis for 2, 5 and 10 branches (see [scale_test.md](scale_test.md)). The time grows about linearly with the data. The forecast stays accurate because one model is shared by all branches.
* **For 10+ restaurants:**
  * Run training, back-tests and simulations as a nightly batch job.
  * Store the results in PostgreSQL, so the dashboard only reads.
  * Load POS data incrementally through the POS API instead of a CSV.
* **AI cost stays small:** the assistant receives a fact sheet of about 1.5k tokens, built from aggregates rather than raw orders. With Gemini 2.5 Flash on the paid tier, that is about USD 0.001 per question.

## Risks

| Risk | Mitigation |
|---|---|
| The partner cannot share data | Sign an NDA; data stays on the partner's laptop or server; no guest personal data is used |
| The manager does not follow the recommendations | Start with 2–3 actions per week. Track adoption, and ask why in the weekly interview. |
| Other factors change during the pilot (a new competitor, a holiday) | Run the A/B branches at the same time; swap the branches if possible; mark events in the calendar |
| Free AI quota or data policy | Use the paid Gemini tier for real data (prompts are not used to improve Google's products) or a local model; offline answers always work |
