"""
FinCredTwin Explanation Generator
Template-based explanations matching sample output style.
"""
from scenario_generator import CandidatePlan
from financial_state import FinancialDigitalTwin


def generate_explanation(
    plan: CandidatePlan,
    twin: FinancialDigitalTwin,
) -> str:
    """
    Generate a concise, grounded explanation for the recommendation.
    Matches the tone and style from sample_requests.csv.
    """
    curr = twin.home_currency
    amt = _fmt(twin.requested_amount, curr)
    min_bal = _fmt(twin.minimum_balance_to_keep, curr)
    
    if plan.method == "full_payment" and plan.affordability_status == "affordable_now":
        if plan.spending_changes != "none":
            change_desc = _describe_spending_changes(plan, twin)
            return f"{change_desc}, then pay {curr} {amt} today. This leaves at least {curr} {min_bal} available."
        return f"Pay {curr} {amt} today. This leaves at least {curr} {min_bal} available over the next 90 days."
    
    if plan.method == "full_payment" and plan.spending_changes != "none":
        change_desc = _describe_spending_changes(plan, twin)
        return f"{change_desc}, then pay {curr} {amt} today. This leaves at least {curr} {min_bal} available."
    
    if plan.method == "partial_payment":
        safe = _fmt(plan.amount_safe_to_pay, curr)
        remainder = _fmt(twin.requested_amount - plan.amount_safe_to_pay, curr)
        second_date = _format_date_str(plan.earliest_date_for_full_payment)
        return (
            f"Pay {curr} {safe} today and the remaining {curr} {remainder} on "
            f"{second_date}. This completes the full request "
            f"and keeps the {curr} {min_bal} minimum protected."
        )
    
    if plan.method == "installments":
        n = plan.num_payments
        per_payment = _fmt(list(plan.payments.values())[0] if plan.payments else 0, curr)
        first_date = _format_date_str(plan.first_payment_date) if plan.first_payment_date else ""
        
        if plan.spending_changes != "none":
            change_desc = _describe_spending_changes(plan, twin)
            return (
                f"{change_desc}. Use {n} installments of {curr} {per_payment}, "
                f"starting {first_date}. This leaves at least {curr} {min_bal} available."
            )
        return (
            f"Use {n} installments of {curr} {per_payment}, starting {first_date}. "
            f"This leaves at least {curr} {min_bal} available."
        )
    
    if plan.method == "wait":
        wait_date = _format_date_str(plan.earliest_date_for_full_payment)
        return (
            f"Pay {curr} {amt} in full on {wait_date}. "
            f"Paying earlier would take the balance below the {curr} {min_bal} minimum."
        )
    
    if plan.method == "not_recommended":
        if plan.amount_safe_to_pay > 0 and plan.earliest_date_for_full_payment == "":
            safe = _fmt(plan.amount_safe_to_pay, curr)
            return (
                f"Do not proceed with the {curr} {amt} request. Although {curr} {safe} is available today, "
                f"the full amount cannot be completed safely within 90 days."
            )
        deadline = _format_date_str(twin.desired_completion_date)
        return (
            f"Do not make this payment by {deadline}. "
            f"None of the available options keeps the {curr} {min_bal} minimum protected."
        )
    
    return f"Recommendation for {curr} {amt}: {plan.method}."


def _format_date_str(d) -> str:
    """Format date as 'd Month YYYY' without platform-specific strftime flags."""
    if d is None or d == "":
        return ""
    if isinstance(d, str):
        try:
            from datetime import date as dt_date
            d = dt_date.fromisoformat(d)
        except (ValueError, TypeError):
            return str(d)
    months = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    return f"{d.day} {months[d.month]} {d.year}"


def _fmt(amount: float, currency: str) -> str:
    """Format amount with thousands separators matching sample style."""
    amt_2dp = round(amount, 2)
    if abs(amt_2dp - round(amt_2dp)) < 1e-6:
        return f"{int(round(amt_2dp)):,}"
    return f"{amt_2dp:,.2f}"



def _describe_spending_changes(plan: CandidatePlan, twin: FinancialDigitalTwin) -> str:
    """Describe spending changes in natural language."""
    if plan.spending_changes == "none":
        return ""
    
    parts = plan.spending_changes.split("|")
    descriptions = []
    
    for part in parts:
        if part.startswith("stop:"):
            event_id = part.split(":")[1]
            desc = _find_event_desc(event_id, twin)
            descriptions.append(f"Stop the {desc}")
        elif part.startswith("reduce_to:"):
            tokens = part.split(":")
            event_id = tokens[1]
            new_amt = tokens[2]
            desc = _find_event_desc(event_id, twin)
            descriptions.append(f"Reduce the {desc} to {twin.home_currency} {new_amt}")
    
    return " and ".join(descriptions) if descriptions else ""


def _find_event_desc(event_id: str, twin: FinancialDigitalTwin) -> str:
    """Find a human-readable description for an event."""
    for e in twin.flexible_expenses:
        if e.event_id == event_id:
            return e.description.lower()
    return event_id
