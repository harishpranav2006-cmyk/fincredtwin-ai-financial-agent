# FinCredTwin — Phase 5A Targeted Root-Cause Investigation: Remaining Discrepancies

## 1. Context & Objective

Following Phase 4, the deterministic decision engine achieved:
- **Recommended Payment Method**: **100.0% (25/25)**
- **Affordability Status**: **92.0% (23/25)**
- **Payment Plan**: **92.0% (23/25)**
- **Earliest Date for Full Payment**: **88.0% (22/25)**
- **Spending Changes Needed**: **92.0% (23/25)**

Only three reference discrepancies remain across the entire reference dataset:
1. **`request_11` (`user_11`)**: Status `affordable_now` (Engine) vs `affordable_with_plan` (Ground Truth with `reduce_to:event_989:665950`).
2. **`request_21` (`user_21`)**: Status `affordable_now` (Engine) vs `affordable_with_plan` (Ground Truth with `stop:event_1815|reduce_to:event_1816:23.50`).
3. **`request_18` (`user_18`)**: Earliest date `2026-08-15` (Engine) vs `2026-09-15` (Ground Truth).

This investigation examines the exact 90-day day-by-day cashflow timelines to determine whether these discrepancies represent an official specification rule, variable spending recurrence, date-boundary handling, or a ground-truth-specific artifact that cannot be safely generalized.

---

## 2. Deep Dive Case 1: `request_11` (`user_11`)

### Request Context
- **User ID**: `user_11`
- **Request Date**: `2025-05-03`
- **Requested Amount**: `IDR 13,110,000` (Family travel)
- **Desired Completion Date**: `2025-06-12`
- **Allows Partial Payment**: `False`
- **Starting Available Balance**: `IDR 63,531,795.00`
- **Minimum Balance to Keep**: `IDR 34,140,600.00`
- **Expense Categories User is Willing to Reduce**: `{'entertainment', 'dining'}`
- **Expense Categories User is Willing to Stop**: `{'cloud_storage'}`
- **Expense Categories Protected**: `{'education', 'housing', 'utilities'}`

### Reconstructed Baseline 90-Day Timeline
The table below tracks opening balance, cash inflows, fixed expenses (housing, utilities, insurance, subscriptions), variable essential expenses (groceries, transport, healthcare), EMI/debt, closing balance, minimum balance, and headroom:

| Day | Date | Opening Balance | Income | Fixed Expenses | Variable Expenses | EMI | Closing Balance | Minimum Balance | Headroom |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 0 | 2025-05-03 | 63,531,795.00 | 0.00 | 0.00 | 0.00 | 0.00 | 63,531,795.00 | 34,140,600.00 | 29,391,195.00 |
| 1 | 2025-05-04 | 63,531,795.00 | 0.00 | 0.00 | 0.00 | 0.00 | 63,531,795.00 | 34,140,600.00 | 29,391,195.00 |
| 2 | 2025-05-05 | 63,531,795.00 | 0.00 | 2,954,500.00 | 0.00 | 0.00 | 60,577,295.00 | 34,140,600.00 | 26,436,695.00 |
| 5 | 2025-05-08 | 60,577,295.00 | 0.00 | 2,796,165.18 | 1,400,963.33 | 0.00 | 56,380,166.49 | 34,140,600.00 | 22,239,566.49 |
| 6 | 2025-05-09 | 56,380,166.49 | 0.00 | 1,881,000.00 | 0.00 | 0.00 | 54,499,166.49 | 34,140,600.00 | 20,358,566.49 |
| 7 | 2025-05-10 | 54,499,166.49 | 0.00 | 0.00 | 2,544,100.00 | 0.00 | 51,955,066.49 | 34,140,600.00 | 17,814,466.49 |
| 8 | 2025-05-11 | 51,955,066.49 | 0.00 | 0.00 | 1,185,524.72 | 0.00 | 50,769,541.77 | 34,140,600.00 | 16,628,941.77 |
| 9 | 2025-05-12 | 50,769,541.77 | 0.00 | 0.00 | 2,826,901.92 | 0.00 | 47,942,639.85 | 34,140,600.00 | 13,802,039.85 |
| 11 | 2025-05-14 | 47,942,639.85 | 0.00 | 168,150.00 | 0.00 | 0.00 | 47,774,489.85 | 34,140,600.00 | **13,633,889.85** |
| 12 | 2025-05-15 | 47,774,489.85 | 38,760,000.00 | 0.00 | 0.00 | 0.00 | 86,534,489.85 | 34,140,600.00 | 52,393,889.85 |
| 13 | 2025-05-16 | 86,534,489.85 | 0.00 | 0.00 | 1,674,887.61 | 0.00 | 84,859,602.24 | 34,140,600.00 | 50,719,002.24 |
| 15 | 2025-05-18 | 84,859,602.24 | 0.00 | 0.00 | 1,400,963.33 | 0.00 | 83,458,638.91 | 34,140,600.00 | 49,318,038.91 |
| 36 | 2025-06-08 | 76,516,687.53 | 0.00 | 2,796,165.18 | 1,185,524.72 | 0.00 | 72,534,997.63 | 34,140,600.00 | 38,394,397.63 |
| 38 | 2025-06-10 | 70,653,997.63 | 0.00 | 0.00 | 2,544,100.00 | 0.00 | 68,109,897.63 | 34,140,600.00 | 33,969,297.63 |
| 43 | 2025-06-15 | 65,114,845.71 | 38,760,000.00 | 0.00 | 0.00 | 0.00 | 103,874,845.71 | 34,140,600.00 | 69,734,245.71 |
| 73 | 2025-07-15 | 82,455,201.57 | 38,760,000.00 | 0.00 | 0.00 | 0.00 | 121,215,201.57 | 34,140,600.00 | 87,074,601.57 |

### Why Engine Recommends Full Payment (`affordable_now`)
On Day 11 (2025-05-14), closing balance before the next salary arrives is IDR 47,774,489.85. The headroom above the minimum balance (IDR 34,140,600.00) is **IDR 13,633,889.85**.
Since the requested purchase amount is **IDR 13,110,000.00**, paying immediately leaves `IDR 13,633,889.85 - 13,110,000.00 = IDR 523,889.85` of buffer above minimum balance. The engine therefore evaluates that the purchase is safe today without needing spending changes (`affordable_now`, `spending=none`).

### Why Ground Truth Requires `reduce_to:event_989:665950`
In `dataset/financial_events.csv`, `user_11` has a historical transaction:
- **`event_id`**: `event_989`
- **Description**: `"Weekend food delivery"`
- **Category**: `dining`
- **Settlement Date**: `2025-04-23`
- **Amount**: `IDR 1,163,530.49`
- **Flexibility**: `reducible`
- **Minimum Allowed Amount**: `IDR 665,950.00`

User 11 settled dining expenses on an exact 21-day cadence across 9 historical events (every 3 weeks). Stepping forward 21 days from 2025-04-23 places the next dining event on **2025-05-14** (Day 11, the day before salary).
If the unreduced dining expense is projected on Day 11:
$$\text{Day 11 Balance} = \text{IDR } 47,774,489.85 - \text{IDR } 1,163,530.49 = \text{IDR } 46,610,959.36$$
$$\text{Post-Purchase Balance} = \text{IDR } 46,610,959.36 - \text{IDR } 13,110,000.00 = \text{IDR } 33,500,959.36$$
$$\text{Deficit Below Minimum Balance} = \text{IDR } 34,140,600.00 - \text{IDR } 33,500,959.36 = \text{IDR } 639,640.64$$

Under the ground truth model, paying in full without modifying `event_989` violates the minimum balance.
By applying `reduce_to:event_989:665950`:
$$\text{Savings} = \text{IDR } 1,163,530.49 - \text{IDR } 665,950.00 = \text{IDR } 497,580.49$$
This reduces the dining expense, keeping the balance safely above minimum balance on Day 11.
Thus, ground truth outputs `affordable_with_plan` with `reduce_to:event_989:665950`.

---

## 3. Deep Dive Case 2: `request_21` (`user_21`)

### Request Context
- **User ID**: `user_21`
- **Request Date**: `2026-04-03`
- **Requested Amount**: `USD 1,574.40` (Course fee)
- **Desired Completion Date**: `2026-04-14`
- **Allows Partial Payment**: `False`
- **Starting Available Balance**: `USD 3,911.35`
- **Minimum Balance to Keep**: `USD 1,800.00`
- **Expense Categories User is Willing to Reduce**: `{'dining', 'streaming', 'shopping'}`
- **Expense Categories User is Willing to Stop**: `{'cloud_storage', 'streaming'}`

### Reconstructed Baseline 90-Day Timeline

| Day | Date | Opening Balance | Income | Fixed Expenses | Variable Expenses | EMI | Closing Balance | Minimum Balance | Headroom |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 0 | 2026-04-03 | 3,858.35 | 0.00 | 0.00 | 0.00 | 0.00 | 3,858.35 | 1,800.00 | 2,058.35 |
| 1 | 2026-04-04 | 3,858.35 | 0.00 | 0.00 | 0.00 | 0.00 | 3,858.35 | 1,800.00 | 2,058.35 |
| 3 | 2026-04-06 | 3,858.35 | 0.00 | 124.08 | 81.85 | 0.00 | 3,652.42 | 1,800.00 | 1,852.42 |
| 6 | 2026-04-09 | 3,652.42 | 0.00 | 47.00 | 0.00 | 0.00 | 3,605.42 | 1,800.00 | 1,805.42 |
| 9 | 2026-04-12 | 3,605.42 | 0.00 | 11.00 | 126.38 | 0.00 | 3,468.04 | 1,800.00 | **1,668.04** |
| 12 | 2026-04-15 | 3,468.04 | 2,256.00 | 0.00 | 0.00 | 0.00 | 5,724.04 | 1,800.00 | 3,924.04 |
| 23 | 2026-04-26 | 5,603.23 | 0.00 | 0.00 | 81.85 | 0.00 | 5,521.38 | 1,800.00 | 3,721.38 |
| 29 | 2026-05-02 | 5,521.38 | 0.00 | 718.80 | 0.00 | 0.00 | 4,802.58 | 1,800.00 | 3,002.58 |
| 42 | 2026-05-15 | 4,373.31 | 2,256.00 | 0.00 | 0.00 | 0.00 | 6,629.31 | 1,800.00 | 4,829.31 |

*(Note: Day 0 Opening Balance is 3,858.35 after reserving USD 53.00 for pending fuel authorization `event_1857`).*

### Why Engine Recommends Full Payment (`affordable_now`)
On Day 9 (2026-04-12), the pre-salary balance dips to USD 3,468.04, leaving headroom of `3,468.04 - 1,800.00 = USD 1,668.04`.
The course fee is USD 1,574.40. Since `1,668.04 > 1,574.40`, the engine computes that paying USD 1,574.40 leaves a cushion of `1,668.04 - 1,574.40 = USD 93.64` above the minimum balance.

### Why Ground Truth Requires Spending Changes
In ground truth:
- **`amount_safe_to_pay`**: `USD 1,543.35`
- **Shortfall**: `1,574.40 - 1,543.35 = USD 31.05`
- **Spending Changes**: `stop:event_1815|reduce_to:event_1816:23.50`
  - `event_1815` (`cloud_storage`): `11.00 USD` (flexibility: `stoppable`) $\rightarrow$ Saved: `USD 11.00`
  - `event_1816` (`streaming`): `47.00 USD` (reduced to `23.50 USD`) $\rightarrow$ Saved: `USD 23.50`
  - **Total Savings**: `11.00 + 23.50 = USD 34.50`
  - Net Headroom after changes: `1,543.35 + 34.50 = USD 1,577.85 >= 1,574.40`.

Ground truth evaluated `amount_safe_to_pay` as **USD 1,543.35** (exactly USD 124.69 less than the engine's 1,668.04). Because the unadjusted headroom (1,543.35) was USD 31.05 short of the course fee, and the deadline was April 14 (before salary on April 15), the request could only be satisfied by activating spending changes before deadline (`affordable_with_plan`).

---

## 4. Deep Dive Case 3: `request_18` (`user_18`)

### Request Context
- **User ID**: `user_18`
- **Request Date**: `2026-07-07`
- **Requested Amount**: `EUR 3,246.10` (Annual membership)
- **Desired Completion Date**: `2026-09-15`
- **Starting Available Balance**: `EUR 2,486.00`
- **Minimum Balance to Keep**: `EUR 1,400.00`

### Reconstructed Timeline Around Salary Dates (August 15 & September 15)

| Day | Date | Opening Balance | Income | Fixed Expenses | Variable Expenses | EMI | Closing Balance | Minimum Balance | Headroom |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 35 | 2026-08-11 | 3,525.26 | 0.00 | 0.00 | 191.77 | 0.00 | 3,333.49 | 1,400.00 | 1,933.49 |
| **39** | **2026-08-15** | **3,333.49** | **2,310.00** | **0.00** | **0.00** | **0.00** | **5,643.49** | **1,400.00** | **4,243.49** |
| 44 | 2026-08-20 | 5,643.49 | 0.00 | 0.00 | 95.32 | 0.00 | 5,548.17 | 1,400.00 | 4,148.17 |
| 49 | 2026-08-25 | 5,548.17 | 0.00 | 0.00 | 43.81 | 0.00 | 5,504.36 | 1,400.00 | 4,104.36 |
| 54 | 2026-08-30 | 5,504.36 | 0.00 | 0.00 | 95.32 | 0.00 | 5,409.03 | 1,400.00 | 4,009.03 |
| 59 | 2026-09-04 | 5,409.03 | 0.00 | 167.00 | 0.00 | 0.00 | 5,242.03 | 1,400.00 | 3,842.03 |
| 62 | 2026-09-07 | 5,242.03 | 0.00 | 107.43 | 0.00 | 0.00 | 5,134.60 | 1,400.00 | 3,734.60 |
| 63 | 2026-09-08 | 5,134.60 | 0.00 | 68.00 | 43.81 | 0.00 | 5,022.79 | 1,400.00 | 3,622.79 |
| 64 | 2026-09-09 | 5,022.79 | 0.00 | 0.00 | 95.32 | 0.00 | 4,927.47 | 1,400.00 | 3,527.47 |
| 65 | 2026-09-10 | 4,927.47 | 0.00 | 68.00 | 0.00 | 0.00 | 4,859.47 | 1,400.00 | 3,459.47 |
| 66 | 2026-09-11 | 4,859.47 | 0.00 | 0.00 | 147.96 | 0.00 | 4,711.51 | 1,400.00 | 3,311.51 |
| **70** | **2026-09-15** | **4,711.51** | **2,310.00** | **0.00** | **0.00** | **0.00** | **7,021.51** | **1,400.00** | **5,621.51** |

### Mathematical Simulation of Paying on 2026-08-15
If the user pays EUR 3,246.10 on 2026-08-15 (Day 39):
1. **Day 39 Closing Balance**: `5,643.49 - 3,246.10 = EUR 2,397.39`
2. **Subsequent Expenses (Aug 16 – Sep 14)**: Totaling `EUR 931.97` across groceries, transport, utilities, streaming, insurance, and clinic payment.
3. **Lowest Closing Balance (Day 66 / Sep 11)**: `4,711.51 - 3,246.10 = EUR 1,465.41`
4. **Headroom Above Minimum Balance**: `1,465.41 - 1,400.00 = EUR 65.41`.

Because EUR 1,465.41 $\ge$ EUR 1,400.00, our engine evaluated that paying on **2026-08-15** was technically viable ($B(t) \ge B_{\text{min}}$).

### Why Ground Truth Selects `2026-09-15`
User 18 has historical settled dining expenses every 14 days (averaging EUR 85–102 per transaction: `2026-06-03: 62.87`, `2026-06-17: 82.67`, `2026-07-01: 101.88`).
Between August 15 and September 15 (a 31-day window), two dining cycles (~EUR 170) occur.
If even **one** regular dining expense of EUR 85 occurs between Aug 15 and Sep 15:
$$\text{Closing Balance} = \text{EUR } 1,465.41 - \text{EUR } 85.00 = \text{EUR } 1,380.41 < \text{EUR } 1,400.00$$

The EUR 65.41 cushion is completely wiped out by standard variable living expenses. Therefore, paying on August 15 violates the minimum balance requirement, and the first conservative safe payment date is **2026-09-15**.

---

## 5. Cross-Case Analysis & Hypothesis Evaluation

Across all three cases, the underlying divergence stems from **how recurring variable spending (specifically dining and non-monthly cycles) is handled**.

| Hypothesis | Description | Evaluation Against Evidence |
| :--- | :--- | :--- |
| **Hypothesis A**: Variable expense recurrence is excluded too aggressively. | Dining has regular intervals (14d, 21d) in `user_11`, `user_18`, and `user_21`. Projecting it explains all 3 reference discrepancies. | **Supported in these 3 rows**, but **fails catastrophically on other reference rows** (see below). |
| **Hypothesis B**: All categories with low variance should be projected regardless of interval. | If interval variance is low, project regardless of category. | **Falsified**: In `user_06`, dining has zero variance (7d, 7d, 7d, 7d). Projecting it causes `request_06` to falsely fail affordability. |
| **Hypothesis C**: Ground truth only projects variable expenses when headroom is tight. | Dynamic inclusion based on cash cushion. | **Falsified**: An AI agent cannot selectively toggle forecasting rules based on the outcome without violating causality. |
| **Hypothesis D**: The 90-day simulation horizon should clamp at request deadline. | Clamping the horizon at `desired_completion_date`. | **Falsified**: Section 6.3 and Section 176 explicitly state the simulation must cover the full 90-day forecast. |

### The Counter-Evidence: Why Projecting All Variable Recurrence Fails Globally
When `DISCRETIONARY_VARIABLE` is eliminated and all detected recurring cycles (including 7d, 14d, 21d dining) are projected:
- `request_06` drops from `affordable_with_plan` to `affordable_later` (Method drops from `full_payment` to `wait`).
- `request_08` drops from `affordable_later` to `not_affordable` (Day 89/90 balance collapses into negative insolvency).
- `request_13` drops from `affordable_later` to `not_affordable`.
- Overall payment method accuracy drops from **100% (25/25)** down to **84% (21/25)**.
- Affordability status accuracy drops from **92% (23/25)** down to **80% (20/25)**.

---

## 6. Engineering Recommendation & Decision

### Can a Deterministic Rule Be Safely Generalized?
**NO.**
The reference dataset contains an internal tension regarding discretionary variable expenses:
- In `request_11`, `request_18`, and `request_21`, ground truth expects dining and short-interval variable spending to be reserved against the balance headroom.
- In `request_06`, `request_08`, `request_12`, and `request_13`, projecting those exact same categories causes artificial insolvency and causes valid requests to be rejected.

Any rule that hardcodes or selectively treats dining differently for certain users would constitute blatant sample overfitting and would degrade generalization on unseen test evaluation requests.

### Formal Declaration
> **"The remaining discrepancies on request_11, request_21, and request_18 cannot be safely generalized from available evidence without violating the published rules or degrading overall decision accuracy on unseen requests."**

The deterministic pipeline should remain fixed at its current optimal configuration:
- **Payment Method**: **100.0%**
- **Affordability Status**: **92.0%**
- **Payment Plan**: **92.0%**
- **Earliest Date**: **88.0%**
- **Spending Changes**: **92.0%**
- **Overall Field Compliance**: **80.0%**
