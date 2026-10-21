# Scale test

Machine: Linux x86_64, Python 3.13.16. Generated data, one process per size; all steps the app runs on its first start.

| Branches | Orders | Order lines | Total time | Data | KPIs + alerts | Forecast | Back-test | Menu + pricing + basket | Operations | Waste sim | Peak memory | Forecast WAPE (best rule) | AI context |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | 85,878 | 533,712 | **11.8 s** | 1.0 s | 0.4 s | 1.4 s | 5.8 s | 0.6 s | 0.1 s | 2.5 s | 505 MB | 13.2% (14.2%) | ~1,327 tokens |
| 5 | 234,941 | 1,455,850 | **23.9 s** | 2.7 s | 0.8 s | 3.0 s | 11.6 s | 1.3 s | 0.1 s | 4.0 s | 997 MB | 11.0% (13.1%) | ~1,742 tokens |
| 10 | 465,273 | 2,886,005 | **44.5 s** | 5.5 s | 1.4 s | 5.1 s | 21.5 s | 2.2 s | 0.3 s | 7.4 s | 1823 MB | 10.6% (13.2%) | ~2,261 tokens |

**Reading:** 5.4x more data took 3.8x more time, so the cost grows about linearly. After the first run the app caches every step, so pages open in about a second. The forecast model is shared by all branches (one global model), so it stays accurate when branches are added, and the AI fact sheet stays small because it holds aggregates, not raw orders.

**Limits and next steps for a real chain:** run the heavy steps (training, back-test, simulation) as a nightly batch job and store the results in a database (PostgreSQL), so the dashboard only reads; read POS data incrementally instead of one CSV; one app instance per region if needed.
