"""
FinCredTwin Plan Ranker
Deterministic 6-tier tuple comparator per problem_statement.md.

Official ranking hierarchy:
1. Complete the full request by desired_completion_date
2. Require no spending changes
3. Minimize the total amount paid
4. Start payment earlier
5. Use fewer payments
6. Use the lowest payment_option_id as the final tie-breaker

No LLM judgement or nested heuristics.
"""
import re
from datetime import date
from typing import List, Optional, Tuple

from scenario_generator import CandidatePlan


def rank_plans(
    candidates: List[CandidatePlan],
    desired_completion_date: date,
) -> Optional[CandidatePlan]:
    """
    Rank safe candidate plans using the official 6-tier hierarchy.
    
    Returns the winning plan, or None if no safe candidates exist.
    """
    safe_candidates = [c for c in candidates if c.is_safe]
    
    if not safe_candidates:
        return None
    
    # Sort by the 6-tier key (ascending — lower is better for all tiers)
    safe_candidates.sort(key=lambda c: _sort_key(c, desired_completion_date))
    
    return safe_candidates[0]


def _sort_key(plan: CandidatePlan, deadline: date) -> Tuple:
    """
    Generate the deterministic sort key for a candidate plan.
    
    Returns a tuple where lower values are better at each position.
    """
    # Tier 1: Complete by deadline (0 = yes, 1 = no)
    if plan.completion_date and plan.completion_date <= deadline:
        completes_on_time = 0
    else:
        completes_on_time = 1
    
    # Tier 2: No spending changes (0 = none, 1 = has changes)
    no_spending_changes = 0 if plan.spending_changes == "none" else 1
    
    # Tier 3: Total amount paid (lower is better)
    total_paid = round(plan.total_payable_amount, 2)
    
    # Tier 4: Start payment earlier (earlier date is better)
    start_date = plan.first_payment_date or date.max
    
    # Tier 5: Fewer payments (lower count is better)
    num_payments = plan.num_payments
    
    # Tier 6: Lowest payment_option_id (numeric extraction)
    option_id_num = _extract_option_id_number(plan.payment_option_id)
    
    return (
        completes_on_time,
        no_spending_changes,
        total_paid,
        start_date,
        num_payments,
        option_id_num,
    )


def _extract_option_id_number(option_id: Optional[str]) -> int:
    """
    Extract the numeric part from a payment_option_id string.
    e.g., 'payment_option_05' → 5
    
    Non-installment plans (full_payment, partial, wait) get a large number
    so they don't interfere with installment tie-breaking.
    """
    if not option_id:
        return 999999
    
    match = re.search(r"(\d+)$", option_id)
    if match:
        return int(match.group(1))
    return 999999
