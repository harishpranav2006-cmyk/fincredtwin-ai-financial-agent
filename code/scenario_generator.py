"""
FinCredTwin Scenario Generator
Generates candidate payment plans for all 5 methods.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional

from config import FORECAST_DAYS
from financial_state import FinancialDigitalTwin
from data_loader import PaymentOption
from forecast_engine import simulate_plan


@dataclass
class CandidatePlan:
    """A candidate payment plan to be evaluated."""
    method: str  # full_payment, partial_payment, installments, wait, not_recommended
    affordability_status: str
    payment_plan_str: str  # Formatted plan string or 'none'
    payments: Dict[date, float] = field(default_factory=dict)
    total_payable_amount: float = 0.0
    first_payment_date: Optional[date] = None
    completion_date: Optional[date] = None
    num_payments: int = 0
    spending_changes: str = "none"
    spending_changes_detail: Optional[Dict] = None
    payment_option_id: Optional[str] = None
    is_safe: bool = False
    earliest_date_for_full_payment: str = ""
    amount_safe_to_pay: float = 0.0


def generate_candidates(twin: FinancialDigitalTwin) -> List[CandidatePlan]:
    """
    Generate all candidate plans for a request.
    
    Order: full_payment, partial_payment, installments, wait
    Each candidate is tested against the 90-day simulator.
    """
    candidates = []
    
    # ── 1. Full Payment Today ──
    if "full_payment" in twin.payment_methods_user_will_consider:
        plan = _make_full_payment(twin)
        candidates.append(plan)
    
    # ── 2. Partial Payment ──
    if (twin.allows_partial_payment 
        and "partial_payment" in twin.payment_methods_user_will_consider
        and 0 < twin.amount_safe_to_pay < twin.requested_amount
        and twin.earliest_date_for_full_payment):
        plan = _make_partial_payment(twin)
        if plan:
            candidates.append(plan)
    
    # ── 3. Installments ──
    if "installments" in twin.payment_methods_user_will_consider:
        for option in twin.payment_options:
            if option.payment_method == "installments":
                plan = _make_installment_plan(twin, option)
                if plan:
                    candidates.append(plan)
    
    # ── 4. Wait ──
    if ("full_payment" in twin.payment_methods_user_will_consider
        and twin.earliest_date_for_full_payment
        and twin.earliest_date_for_full_payment != twin.request_date.strftime("%Y-%m-%d")):
        plan = _make_wait_plan(twin)
        if plan:
            candidates.append(plan)
    
    # ── 5. Spending change variants ──
    # Try adding spending changes to plans that are not safe without them
    spending_candidates = _generate_spending_change_candidates(twin, candidates)
    candidates.extend(spending_candidates)
    
    return candidates


def _make_full_payment(twin: FinancialDigitalTwin) -> CandidatePlan:
    """Create a full_payment candidate."""
    payments = {twin.request_date: twin.requested_amount}
    is_safe = simulate_plan(twin, payments)
    
    plan_str = f"{twin.request_date.strftime('%Y-%m-%d')}:{_fmt_amount(twin.requested_amount)}"
    
    return CandidatePlan(
        method="full_payment",
        affordability_status="affordable_now" if is_safe else "not_affordable",
        payment_plan_str=plan_str if is_safe else "none",
        payments=payments,
        total_payable_amount=twin.requested_amount,
        first_payment_date=twin.request_date,
        completion_date=twin.request_date,
        num_payments=1,
        is_safe=is_safe,
        earliest_date_for_full_payment=twin.earliest_date_for_full_payment,
        amount_safe_to_pay=twin.amount_safe_to_pay,
    )


def _make_partial_payment(twin: FinancialDigitalTwin) -> Optional[CandidatePlan]:
    """
    Create a partial_payment candidate.
    
    Prerequisites (all must hold):
    1. allows_partial_payment == True
    2. 'partial_payment' in payment_methods_user_will_consider
    3. 0 < amount_safe_to_pay < requested_amount
    4. earliest_date_for_full_payment is valid AND <= desired_completion_date
    5. Two payments sum to requested_amount
    """
    safe_amt = twin.amount_safe_to_pay
    remainder = twin.requested_amount - safe_amt
    
    try:
        earliest_date = date.fromisoformat(twin.earliest_date_for_full_payment)
    except (ValueError, TypeError):
        return None
    
    if earliest_date > twin.desired_completion_date:
        return None
    
    payments = {
        twin.request_date: safe_amt,
        earliest_date: remainder,
    }
    
    is_safe = simulate_plan(twin, payments)
    
    if not is_safe:
        return None
    
    plan_str = (
        f"{twin.request_date.strftime('%Y-%m-%d')}:{_fmt_amount(safe_amt)}"
        f"|{earliest_date.strftime('%Y-%m-%d')}:{_fmt_amount(remainder)}"
    )
    
    return CandidatePlan(
        method="partial_payment",
        affordability_status="affordable_with_plan",
        payment_plan_str=plan_str,
        payments=payments,
        total_payable_amount=twin.requested_amount,
        first_payment_date=twin.request_date,
        completion_date=earliest_date,
        num_payments=2,
        is_safe=True,
        earliest_date_for_full_payment=twin.earliest_date_for_full_payment,
        amount_safe_to_pay=safe_amt,
    )


def _make_installment_plan(
    twin: FinancialDigitalTwin,
    option: PaymentOption,
) -> Optional[CandidatePlan]:
    """
    Create an installment candidate from a payment option.
    
    Validates:
    - max_installment_months constraint
    - All payments within forecast window
    - Simulated safety
    """
    # Check max_installment_months
    if twin.max_installment_months is not None:
        # Estimate months from number_of_payments and frequency
        freq = option.payment_frequency_days or 30
        total_days = freq * (option.number_of_payments - 1)
        total_months = total_days / 30.0
        if total_months > twin.max_installment_months:
            return None
    
    # Build payment schedule
    payments = {}
    payment_dates = []
    freq = option.payment_frequency_days or 30
    
    for i in range(option.number_of_payments):
        pay_date = option.first_payment_date + timedelta(days=i * freq)
        payments[pay_date] = option.payment_amount
        payment_dates.append(pay_date)
    
    # Simulate safety
    is_safe = simulate_plan(twin, payments)
    
    if not is_safe:
        return None
    
    # Build plan string
    plan_parts = [
        f"{d.strftime('%Y-%m-%d')}:{_fmt_amount(option.payment_amount)}"
        for d in payment_dates
    ]
    plan_str = "|".join(plan_parts)
    
    completion_date = payment_dates[-1] if payment_dates else twin.request_date
    
    return CandidatePlan(
        method="installments",
        affordability_status="affordable_with_plan",
        payment_plan_str=plan_str,
        payments=payments,
        total_payable_amount=option.total_payable_amount,
        first_payment_date=option.first_payment_date,
        completion_date=completion_date,
        num_payments=option.number_of_payments,
        is_safe=True,
        payment_option_id=option.payment_option_id,
        earliest_date_for_full_payment=twin.earliest_date_for_full_payment,
        amount_safe_to_pay=twin.amount_safe_to_pay,
    )


def _make_wait_plan(twin: FinancialDigitalTwin) -> Optional[CandidatePlan]:
    """Create a wait candidate — pay full amount on earliest safe date."""
    try:
        earliest_date = date.fromisoformat(twin.earliest_date_for_full_payment)
    except (ValueError, TypeError):
        return None
    
    if earliest_date <= twin.request_date:
        return None  # If safe today, full_payment handles it
    
    payments = {earliest_date: twin.requested_amount}
    is_safe = simulate_plan(twin, payments)
    
    if not is_safe:
        return None
    
    plan_str = f"{earliest_date.strftime('%Y-%m-%d')}:{_fmt_amount(twin.requested_amount)}"
    
    return CandidatePlan(
        method="wait",
        affordability_status="affordable_later",
        payment_plan_str=plan_str,
        payments=payments,
        total_payable_amount=twin.requested_amount,
        first_payment_date=earliest_date,
        completion_date=earliest_date,
        num_payments=1,
        is_safe=True,
        earliest_date_for_full_payment=twin.earliest_date_for_full_payment,
        amount_safe_to_pay=twin.amount_safe_to_pay,
    )


def _generate_spending_change_candidates(
    twin: FinancialDigitalTwin,
    existing_candidates: List[CandidatePlan],
) -> List[CandidatePlan]:
    """
    Generate variants of unsafe plans with spending changes applied.
    
    Tries up to 3 spending changes (stop/reduce) on flexible expenses.
    """
    # Only try spending changes if no safe plan exists without them
    has_safe_completing = any(
        c.is_safe and c.completion_date and c.completion_date <= twin.desired_completion_date
        for c in existing_candidates
    )
    
    if has_safe_completing:
        return []  # No need for spending changes
    
    # Build eligible spending changes
    eligible_changes = _get_eligible_changes(twin)
    if not eligible_changes:
        return []
    
    # Sort by maximum cash freed (largest savings first)
    eligible_changes.sort(key=lambda c: c["savings"], reverse=True)
    
    # Try combinations of up to 3 changes
    new_candidates = []
    
    for num_changes in range(1, min(4, len(eligible_changes) + 1)):
        selected = eligible_changes[:num_changes]
        
        # Build spending changes dict
        changes_list = []
        change_strs = []
        
        for change in selected:
            changes_list.append(change)
            if change["type"] == "stop":
                change_strs.append(f"stop:{change['event_id']}")
            elif change["type"] == "reduce_to":
                change_strs.append(f"reduce_to:{change['event_id']}:{_fmt_amount(change['new_amount'])}")
        
        spending_changes = {"changes": changes_list}
        spending_str = "|".join(change_strs)
        
        # Try full_payment with spending changes
        if "full_payment" in twin.payment_methods_user_will_consider:
            payments = {twin.request_date: twin.requested_amount}
            is_safe = simulate_plan(twin, payments, spending_changes)
            if is_safe:
                plan_str = f"{twin.request_date.strftime('%Y-%m-%d')}:{_fmt_amount(twin.requested_amount)}"
                new_candidates.append(CandidatePlan(
                    method="full_payment",
                    affordability_status="affordable_with_plan",
                    payment_plan_str=plan_str,
                    payments=payments,
                    total_payable_amount=twin.requested_amount,
                    first_payment_date=twin.request_date,
                    completion_date=twin.request_date,
                    num_payments=1,
                    spending_changes=spending_str,
                    spending_changes_detail=spending_changes,
                    is_safe=True,
                    earliest_date_for_full_payment=twin.earliest_date_for_full_payment,
                    amount_safe_to_pay=twin.amount_safe_to_pay,
                ))
                break  # Found a safe plan with fewest changes
        
        # Try installments with spending changes
        if "installments" in twin.payment_methods_user_will_consider:
            for option in twin.payment_options:
                if option.payment_method != "installments":
                    continue
                # Check max_installment_months
                if twin.max_installment_months is not None:
                    freq = option.payment_frequency_days or 30
                    total_days = freq * (option.number_of_payments - 1)
                    if total_days / 30.0 > twin.max_installment_months:
                        continue
                
                inst_payments = {}
                payment_dates = []
                freq = option.payment_frequency_days or 30
                for i in range(option.number_of_payments):
                    pay_date = option.first_payment_date + timedelta(days=i * freq)
                    inst_payments[pay_date] = option.payment_amount
                    payment_dates.append(pay_date)
                
                is_safe = simulate_plan(twin, inst_payments, spending_changes)
                if is_safe:
                    plan_parts = [
                        f"{d.strftime('%Y-%m-%d')}:{_fmt_amount(option.payment_amount)}"
                        for d in payment_dates
                    ]
                    new_candidates.append(CandidatePlan(
                        method="installments",
                        affordability_status="affordable_with_plan",
                        payment_plan_str="|".join(plan_parts),
                        payments=inst_payments,
                        total_payable_amount=option.total_payable_amount,
                        first_payment_date=option.first_payment_date,
                        completion_date=payment_dates[-1],
                        num_payments=option.number_of_payments,
                        spending_changes=spending_str,
                        spending_changes_detail=spending_changes,
                        is_safe=True,
                        payment_option_id=option.payment_option_id,
                        earliest_date_for_full_payment=twin.earliest_date_for_full_payment,
                        amount_safe_to_pay=twin.amount_safe_to_pay,
                    ))
    
    return new_candidates


def _get_eligible_changes(twin: FinancialDigitalTwin) -> List[Dict]:
    """
    Identify eligible spending changes.
    
    Rules:
    - Protected categories: NEVER change
    - Only categories user is willing to reduce/stop
    - Flexibility flag must match
    - reduce_to cannot go below minimum_allowed_amount
    - Max 3 changes, stop and reduce on same event are mutually exclusive
    """
    changes = []
    
    for event in twin.flexible_expenses:
        if event.amount is None:
            continue
        
        # Already checked in financial_state.py, but double-check
        if event.category in twin.expense_categories_to_protect:
            continue
        
        can_stop = (
            event.category in twin.expense_categories_user_is_willing_to_stop
            and event.flexibility in ("stoppable", "reducible_or_stoppable")
        )
        can_reduce = (
            event.category in twin.expense_categories_user_is_willing_to_reduce
            and event.flexibility in ("reducible", "reducible_or_stoppable")
        )
        
        if can_stop:
            changes.append({
                "type": "stop",
                "event_id": event.event_id,
                "savings": event.amount,  # Full amount saved per occurrence
            })
        elif can_reduce:
            floor = event.minimum_allowed_amount or 0.0
            savings = event.amount - floor
            if savings > 0:
                changes.append({
                    "type": "reduce_to",
                    "event_id": event.event_id,
                    "new_amount": floor,
                    "savings": savings,
                })
    
    return changes


def _fmt_amount(amount: float) -> str:
    """Format amount for plan strings — integer if whole number, else exactly 2 decimal places."""
    amt_2dp = round(amount, 2)
    if abs(amt_2dp - round(amt_2dp)) < 1e-6:
        return str(int(round(amt_2dp)))
    return f"{amt_2dp:.2f}"

