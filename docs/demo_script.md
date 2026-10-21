# Demo script: final internship demo (about 6 minutes, live)

**Setup before the call:**

- Open the online app (https://horeca-dss.streamlit.app) or start it with `run.bat`.
- Click through every page once. The first opening of Forecast and Evaluation trains and back-tests the models; after that, every page opens in about a second.
- Set the sidebar role to "Branch manager".
- Keep the recorded video ready as a backup.

| Time | Page | Say / show |
|---|---|---|
| 0:00 | Overview | Who I am and what I will show: the live app, the results, and the changes after the PM mentor review. |
| 0:30 | Overview | **Problem:** restaurant managers decide on staff, purchases, menu and prices by gut feeling. **User:** a branch or operations manager. **Goal:** turn POS data into concrete actions with a value in UZS. |
| 1:00 | Overview | KPI tiles vs the previous period. **Alert:** "Tue 06 Oct, Yunusabad −68%: almost no sales from 15:00, so a likely outage." The 👍 / 👎 under each recommendation. |
| 1:40 | Forecast | 14-day forecast with an 80% range. Switch on the **campaign what-if**. Accuracy vs managers' rules: 13% vs 14%, and 11% vs 17% on holidays, promotions and Ramadan. |
| 2:20 | Menu engineering | Stars / Plowhorses / Puzzles / Dogs, with one action per dish. |
| 2:45 | Pricing & upsell | Price changes only when the data is reliable, otherwise a 2-week price test. Upsell: "With Medovik, suggest Cappuccino", valued in UZS per month. |
| 3:15 | Operations | Waiters and cooks per hour: −225 staff-hours vs a fixed schedule. Purchase list. Waste simulation: −35%. |
| 3:45 | AI assistant | Click "Why did revenue drop on Tuesday?". Show the response time, "What the assistant knows", and rate the answer 👍. |
| 4:30 | Evaluation 4–6 | **Answers to the mentor review:** (1) manager feedback summary; (2) scale test: 2 → 10 branches, 2.9 M order lines in 45 s; (3) the 6-week A/B pilot plan with KPIs, targets and a go / no-go gate. |
| 5:30 | README | PM side: a backlog of 23 user stories, risks, 25 tests, the docs and the online link. Next steps: pilot, internship report, thesis. Then questions. |

## Likely questions and short answers

- **Is the data real?** No. It is synthetic data with known, planted effects, so we can prove that the methods recover them. The next step is the [validation plan](validation_plan.md): a 6-week pilot with a real POS export. The upload page already accepts one.
- **Which LLM, and why?** Gemini 2.5 Flash. It has a free tier, it is fast and cheap, and it handles English, Russian and Uzbek well. It is a simple REST API, so the model is only one setting. There are 2 backup models and offline rules.
- **How fast does it answer?** A few seconds. The app shows the time under every answer. Thinking is switched off, because the model only explains numbers that are already computed.
- **Can the LLM hallucinate numbers?** It receives only the computed fact sheet and is told to use only those numbers. The "What the assistant knows" panel shows exactly what was sent, and managers rate every answer.
- **Data privacy and cost?** Only aggregates are sent; there are no guest personal data. On the free tier Google may use prompts to improve its products, so real data needs the paid tier (about $0.001 per question) or a local model.
- **Does it scale?** See [scale_test.md](scale_test.md). For 10+ restaurants, the heavy steps move to a nightly job, with the results stored in a database.
