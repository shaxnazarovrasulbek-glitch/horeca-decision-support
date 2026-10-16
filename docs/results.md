# Evaluation results

Data: generated, seed 42, 2025-10-16 to 2026-10-15

## Forecast accuracy (rolling-origin back-test, 8 origins x 14 days)

**revenue** - improvement vs best rule of thumb: +7.4%

                         method   WAPE   MAPE    bias
   AI model (gradient boosting) 0.1318 0.1425 -0.0300
         Same weekday last week 0.1615 0.1759 -0.0214
Average of last 4 same weekdays 0.1423 0.1485 -0.0684

                     days   n  AI model  Same weekday last week  Average of last 4 same weekdays
              normal days 192    0.1370                  0.1614                           0.1369
holiday / promo / Ramadan  32    0.1057                  0.1620                           0.1695

**covers** - improvement vs best rule of thumb: +5.1%

                         method   WAPE   MAPE    bias
   AI model (gradient boosting) 0.1241 0.1366 -0.0266
         Same weekday last week 0.1557 0.1710 -0.0109
Average of last 4 same weekdays 0.1308 0.1393 -0.0505

                     days   n  AI model  Same weekday last week  Average of last 4 same weekdays
              normal days 192    0.1295                  0.1568                           0.1273
holiday / promo / Ramadan  32    0.0968                  0.1499                           0.1484

## Pricing
Confident price changes: 23, expected margin gain 24,930,819 UZS / month; price tests proposed: 16

## Upsell (top 5, 10% acceptance)
                                      script  confidence  lift  extra_cm_month
       With Medovik Cake, suggest Cappuccino       0.460 2.013     1354430.000
  With Tashkent Plov, suggest Achichuk Salad       0.713 1.687     1059380.000
      With Napoleon Cake, suggest Cappuccino       0.442 1.936     1030260.000
With Chicken Wrap, suggest Homemade Lemonade       0.490 1.844     1014346.667
     With Chicken Wrap, suggest French Fries       0.471 1.904      772650.000

## Staffing (next 7 days vs fixed schedule)
   branch    role  fixed_headcount  planned_hours  fixed_hours  hours_saved  understaffed_hours_fixed  overstaffed_hours_fixed  cost_saved
Chilanzar waiters                3            239          294           55                        12                       53   1210000.0
Chilanzar   cooks                2            171          196           25                        12                       37    550000.0
Yunusabad waiters                3            200          294           94                        10                       74   2068000.0
Yunusabad   cooks                2            145          196           51                        10                       61   1122000.0

## Perishable waste simulation (4 weeks)
                  method   waste_cost  shortage_cost  purchased_cost   used_cost  waste_pct_of_purchases  shortage_pct_of_use
AI forecast + 10% safety 34727080.432     9501985.38    2.719256e+08 246700520.0                   0.128                0.039
 Naive (last week + 15%) 53641189.000    12449053.00    2.878927e+08 246700520.0                   0.186                0.050

Waste reduction: 35.3%