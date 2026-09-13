# Request 19 — Complete Trace & Root Cause Analysis

## Request

| Field | Value |
|---|---|
| request_id | request_19 |
| user_id | user_19 |
| request_date | 2024-09-04 |
| request_type | purchase |
| requested_amount | 39,660.00 INR |
| desired_completion_date | 2024-10-04 |
| allows_partial_payment | True |
| request_text | "Can I buy the laptop now without making next month's bills tight? I need to decide by 4 October 2024. I've been quoted INR 39,660 for the laptop." |

## User Profile (user_19)

| Field | Value |
|---|---|
| home_currency | INR |
| current_available_balance | 199,545.00 |
| minimum_balance_to_keep | 92,800.00 |
| financial_priorities | healthcare, family_support |
| protected categories | family_support, groceries, rent, healthcare |
| willing to reduce | shopping |
| willing to stop | cloud_storage |
| payment_methods | partial_payment, installments |
| max_installment_months | 2 |

IMPORTANT: full_payment is NOT in the user's payment methods. Only partial_payment and installments.

## Messages and Images

- Messages: None (0 messages for user_19)
- Images: image_04 -> event_1700 (grocery order, amount = 2,854.00 INR, filled from image cache)

## Exchange Rates

All events are in INR (home currency). No FX conversion required.

## Pending Events

None. No pending debits or credits.

## Recurring Patterns Detected

### Monthly Fixed
| Category | DOM | Amount | Description |
|---|---|---|---|
| salary (credit) | 15 | 131,000.00 | Payroll credit |
| rent | 4 | 36,100.00 | Residential rent payment |
| utilities | 8 | 6,129.19 | Municipal utilities |
| healthcare | 12 | 8,645.36 | Clinic payment |
| debt_repayment | 13 | 11,850.00 | Loan repayment |
| cloud_storage | 14 | 395.00 | Online backup subscription |
| shopping | 14 | 5,431.12 | Clothing and household items |
| family_support | 15 | 12,650.00 | Childcare contribution |

### Variable Recurring (Non-Monthly)
| Category | Freq | Typical Amt | Description |
|---|---|---|---|
| groceries | 7 days | 4,741.54 (median of 26) | Weekly grocery |
| transport | 14 days | 3,054.24 (median) | Fuel refill |

## Projected Events Day 0-10 (Sep 4 - Sep 14): Pre-Salary Trough

| Day | Date | Category | Amount | Running Headroom |
|---|---|---|---|---|
| 0 | Sep 4 | rent | 36,100.00 | 70,645.00 |
| 4 | Sep 8 | utilities | 6,129.19 | 64,515.81 |
| 6 | Sep 10 | groceries | 4,741.54 | 59,774.27 |
| 8 | Sep 12 | healthcare | 8,645.36 | 51,128.91 |
| 8 | Sep 12 | transport | 3,054.24 | 48,074.67 |
| 9 | Sep 13 | debt_repayment | 11,850.00 | 36,224.67 |
| 10 | Sep 14 | cloud_storage | 395.00 | 35,829.67 |
| 10 | Sep 14 | shopping | 5,431.12 | **30,398.55** |

### Day 11 (Sep 15): Salary Arrival
| Day | Date | Category | Amount | Running Headroom |
|---|---|---|---|---|
| 11 | Sep 15 | salary (credit) | +131,000.00 | 161,398.55 |
| 11 | Sep 15 | family_support | 12,650.00 | **148,748.55** |

## Safe Amount Computation

### Engine Calculation
```
Starting balance:              199,545.00
Minimum balance:                92,800.00
Total headroom:                106,745.00

Projected debits Day 0-10:
  rent:              36,100.00
  utilities:          6,129.19
  groceries:          4,741.54
  healthcare:         8,645.36
  transport:          3,054.24
  debt_repayment:    11,850.00
  cloud_storage:        395.00
  shopping:           5,431.12
  Total:             76,346.45

Min headroom = 106,745.00 - 76,346.45 = 30,398.55
```

### Binary Search Verification
```
Exact max safe amount: 30,398.5543 (converged to <0.001 tolerance)
Rounded to 2 dp:       30,398.55
```

Both closed-form and simulation agree: **30,398.55 is the correct amount_safe_to_pay**.

### Reference Value: 28,820.00

| Metric | Engine | Reference | Delta |
|---|---|---|---|
| amount_safe_to_pay | 30,398.55 | 28,820.00 | **1,578.55** |

## Root Cause Investigation

### Hypothesis Testing

| # | Hypothesis | Result |
|---|---|---|
| 1 | Rounding difference | REJECTED: delta = 1,578.55, far too large |
| 2 | Missing FX conversion | REJECTED: All events INR, no FX needed |
| 3 | Missing pending event | REJECTED: 0 pending events |
| 4 | Missing message fact | REJECTED: 0 messages for user_19 |
| 5 | Different grocery median | REJECTED: 4,741.54 with/without image event |
| 6 | Different grocery frequency | REJECTED: Only 1 grocery projected Day 0-10 |
| 7 | Extra projected expense | PLAUSIBLE: See analysis |
| 8 | Different typical amount | PLAUSIBLE: See analysis |

### Analysis of 1,578.55

The difference does not match any single event amount, event pair, or recognizable formula:
- Transport (3,054.24) — too large
- Cloud (395.00) — too small
- Shopping median vs last (various) — no match
- Grocery mean vs median (132.72) — wrong order of magnitude
- No scheduled or pending events exist
- No messages provide additional context

### Simulation Verification

With 28,820 payment: Day 10 (Sep 14) headroom = 1,578.55 (above minimum — safe)
With 30,398.55 payment: Day 10 (Sep 14) headroom = 0.00 (exactly at minimum — safe)

Both are valid under the constraint B(t) >= minimum_balance_to_keep.

### Root Cause Classification

**Category: I — Ambiguous/Unsupported Reference Behavior**

The engine's calculation of 30,398.55 is mathematically verified:
1. Closed-form computation matches simulation
2. Binary search confirms to 0.001 precision
3. All events are accounted for (no pending, no messages, no FX)
4. The balance never drops below minimum_balance_to_keep

The reference's 28,820 requires ~1,578.55 in additional projected debits between Day 0 and Day 10 that our engine does not project. Without access to the reference implementation, the exact source cannot be determined.

**No general rule can be derived** because:
1. The difference doesn't match any known event amount
2. No messages or images provide additional context
3. The user profile has no unusual configuration
4. Our engine's math is provably correct under stated rules

**Decision: Leave the engine unchanged.** Adjusting for this case would require either:
- Special-casing request_19 (violates RULE 1)
- Adding an arbitrary safety buffer (violates RULE 1)
- Changing the grocery/transport projection model (risks regressions on 250 requests)

## Payment Plan Comparison

| Field | Engine | Reference |
|---|---|---|
| affordability_status | affordable_with_plan | affordable_with_plan |
| recommended_payment_method | partial_payment | partial_payment |
| payment_plan | 2024-09-04:30398.55 then 2024-09-15:9261.45 | 2024-09-04:28820 then 2024-09-15:10840 |
| earliest_date | 2024-09-15 | 2024-09-15 |
| spending_changes | none | none |

Both plans sum to exactly 39,660.00. The only difference is the split between first and second payments, driven by the amount_safe_to_pay calculation.
