"""
FinCredTwin Safety Firewall
Final validation layer before committing any output row.

No recommendation reaches output.csv without passing through this firewall.
"""
from datetime import date
from typing import Dict, Optional, Tuple

from config import AFFORDABILITY_STATUSES, PAYMENT_METHODS
from scenario_generator import CandidatePlan
from financial_state import FinancialDigitalTwin


def validate_output_row(
    plan: Optional[CandidatePlan],
    twin: FinancialDigitalTwin,
) -> Tuple[Dict[str, str], bool, str]:
    """
    Validate and produce the final output row.
    
    Returns:
        (output_dict, is_valid, validation_message)
    """
    if plan is None or not plan.is_safe:
        # Fallback: not_recommended
        return _make_not_recommended(twin), True, "no safe plan found"
    
    errors = []
    
    # ── Schema Validation ──
    
    # 1. affordability_status must be valid enum
    if plan.affordability_status not in AFFORDABILITY_STATUSES:
        errors.append(f"invalid affordability_status: {plan.affordability_status}")
    
    # 2. recommended_payment_method must be valid enum
    if plan.method not in PAYMENT_METHODS:
        errors.append(f"invalid payment_method: {plan.method}")
    
    # ── Preference Validation ──
    
    # 3. Method must be in user's considered list (except not_recommended)
    if plan.method == "full_payment" and "full_payment" not in twin.payment_methods_user_will_consider:
        errors.append("full_payment not in user preferences")
    if plan.method == "partial_payment" and "partial_payment" not in twin.payment_methods_user_will_consider:
        errors.append("partial_payment not in user preferences")
    if plan.method == "installments" and "installments" not in twin.payment_methods_user_will_consider:
        errors.append("installments not in user preferences")
    if plan.method == "wait" and "full_payment" not in twin.payment_methods_user_will_consider:
        errors.append("wait requires full_payment in user preferences")
    
    # ── Bounds Check ──
    
    # 4. 0 <= amount_safe_to_pay <= requested_amount
    safe_amt = plan.amount_safe_to_pay
    if safe_amt < 0 or safe_amt > twin.requested_amount + 0.01:
        errors.append(f"amount_safe_to_pay {safe_amt} out of bounds [0, {twin.requested_amount}]")
    
    # ── Partial Payment Validation ──
    if plan.method == "partial_payment":
        if not twin.allows_partial_payment:
            errors.append("partial_payment but request does not allow it")
        if safe_amt <= 0 or safe_amt >= twin.requested_amount:
            errors.append(f"partial_payment requires 0 < safe_amt < requested_amount, got {safe_amt}")
        if plan.earliest_date_for_full_payment:
            try:
                edate = date.fromisoformat(plan.earliest_date_for_full_payment)
                if edate > twin.desired_completion_date:
                    errors.append("partial_payment earliest_date exceeds deadline")
            except ValueError:
                errors.append("invalid earliest_date_for_full_payment format")
    
    # ── affordable_now consistency ──
    if plan.affordability_status == "affordable_now":
        if plan.earliest_date_for_full_payment != twin.request_date.strftime("%Y-%m-%d"):
            errors.append(
                f"affordable_now requires earliest_date == request_date, "
                f"got {plan.earliest_date_for_full_payment}"
            )
    
    # ── not_affordable consistency ──
    if plan.affordability_status == "not_affordable":
        if plan.method != "not_recommended":
            errors.append("not_affordable must use not_recommended method")
    
    if errors:
        # Fallback to safe default
        return _make_not_recommended(twin), False, "; ".join(errors)
    
    # ── Build valid output row ──
    output = {
        "request_id": twin.request_id,
        "amount_safe_to_pay": _fmt_output_amount(safe_amt),
        "affordability_status": plan.affordability_status,
        "recommended_payment_method": plan.method,
        "payment_plan": plan.payment_plan_str,
        "earliest_date_for_full_payment": plan.earliest_date_for_full_payment,
        "spending_changes_needed": plan.spending_changes,
        "decision_explanation": "",  # Populated by explainer
    }
    
    return output, True, "valid"


def _make_not_recommended(twin: FinancialDigitalTwin) -> Dict[str, str]:
    """Create the safe fallback output row."""
    return {
        "request_id": twin.request_id,
        "amount_safe_to_pay": _fmt_output_amount(twin.amount_safe_to_pay),
        "affordability_status": "not_affordable",
        "recommended_payment_method": "not_recommended",
        "payment_plan": "none",
        "earliest_date_for_full_payment": "",
        "spending_changes_needed": "none",
        "decision_explanation": "",
    }


def _fmt_output_amount(amount: float) -> str:
    """Format amount for output — integer if whole number, else exactly 2 decimal places.
    
    IMPORTANT: Do NOT use rstrip("0") on decimal financial amounts.
    620.40 must remain '620.40', not '620.4'.
    996.60 must remain '996.60', not '996.6'.
    1574.40 must remain '1574.40', not '1574.4'.
    """
    amt_2dp = round(amount, 2)
    if abs(amt_2dp - round(amt_2dp)) < 1e-6:
        return str(int(round(amt_2dp)))
    return f"{amt_2dp:.2f}"

