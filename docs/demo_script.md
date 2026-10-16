# Demo script: final internship demo (6–7 minutes)

**Setup before the call:** run `run.bat`, open the app, put the Gemini key in `.env`, and click through every page
once so that the models are trained and cached. Keep a recorded video as a backup.

| Time | Page | Say / show |
|---|---|---|
| 0:00 | Overview | **Problem:** restaurant managers decide prices, menu, staff and purchases by gut feeling. **Goal:** an AI decision-support platform that turns POS data into concrete, money-valued actions. **User:** a branch or operations manager of a restaurant chain. |
| 0:45 | Overview | KPI tiles vs the previous period, weekly trend, heat-map. Point to the **alert**: "Tuesday, Yunusabad −68%: almost no sales from 15:00, so a likely outage." |
| 1:30 | Forecast | 14-day forecast with the 80% range, holidays marked. Toggle the **campaign what-if**. Open "How accurate is it?": the model vs two rules of thumb, and the much bigger gain on holiday and promo days. |
| 2:30 | Menu engineering | The matrix: Stars, Plowhorses, Puzzles, Dogs within each section. One example action per segment. |
| 3:15 | Pricing & upsell | Price recommendations only where the elasticity is reliable, otherwise a price test. Upsell script "With Medovik, suggest Cappuccino", valued in UZS per month. Combos. |
| 4:00 | Operations | Waiters needed per hour, savings vs a fixed schedule, the purchase list, waste simulation (−35%). |
| 4:45 | AI assistant | Click "Why did revenue drop on Tuesday?", then ask something in Russian or Uzbek. Click **Weekly manager briefing**. Open "What the assistant knows" to show it is grounded in computed facts. |
| 5:45 | Evaluation | Total estimated impact per month, plus the checks against ground truth (pairings, incidents, elasticities). |
| 6:15 | — | **PM side:** backlog and sprint board, risks, what's next (pilot on real POS data, Telegram briefing bot, hotel module). Questions. |

## Likely questions and short answers

- **Is the data real?** No. It is synthetic, with known planted effects, so we can prove the methods recover them. The next step is a pilot on a real POS export, and the upload page already accepts it.
- **Why gradient boosting and not deep learning?** One year of daily data is too small for deep models. Gradient boosting with good features is the standard strong baseline, and it beats the managers' rules on special days.
- **Can the LLM hallucinate numbers?** It only receives the computed fact sheet and is instructed to use only those numbers. The offline mode shows the same facts without a language model.
- **What does it cost to run?** It runs on a laptop. Gemini's free tier is enough for a few dozen questions a day.
