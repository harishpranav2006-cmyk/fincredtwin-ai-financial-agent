"""
FinCredTwin Forecast Engine
Deterministic 90-day cash flow simulation.

Core invariant: B(t) >= minimum_balance_to_keep for all t in [0, 90].

Safe amount and earliest date are ALWAYS verified by full simulation.
The closed-form optimization is used as a starting point, but simulation wins
if they disagree.
"""
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from config import FORECAST_DAYS
from financial_state import FinancialDigitalTwin
from data_loader import FinancialEvent
from cycle_detector import ProjectedEvent


def convert_to_home_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
    settlement_date: date,
    fx_rates: Dict[tuple, float],
    fx_rate_dates: List[date],
) -> float:
    """
    Convert amount from one currency to another using fixed dated rates.
    
    Lookup: (rate_date, from_currency, to_currency) → rate
    If exact date not found, use closest prior rate date.
    """
    if from_currency == to_currency:
        return amount
    
    # Try exact date match
    key = (settlement_date, from_currency, to_currency)
    if key in fx_rates:
        return amount * fx_rates[key]
    
    # Try reverse direction
    reverse_key = (settlement_date, to_currency, from_currency)
    if reverse_key in fx_rates:
        return amount / fx_rates[reverse_key]
    
    # Fallback: closest prior date
    for rd in reversed(fx_rate_dates):
        if rd <= settlement_date:
            key = (rd, from_currency, to_currency)
            if key in fx_rates:
                return amount * fx_rates[key]
            reverse_key = (rd, to_currency, from_currency)
            if reverse_key in fx_rates:
                return amount / fx_rates[reverse_key]
    
    # Last resort: try any date
    for rd in fx_rate_dates:
        key = (rd, from_currency, to_currency)
        if key in fx_rates:
            return amount * fx_rates[key]
        reverse_key = (rd, to_currency, from_currency)
        if reverse_key in fx_rates:
            return amount / fx_rates[reverse_key]
    
    # If no rate found, return amount unchanged (same-currency assumed)
    return amount


def build_daily_cashflow(
    twin: FinancialDigitalTwin,
    candidate_payments: Optional[Dict[date, float]] = None,
    spending_changes: Optional[Dict[str, object]] = None,
) -> List[float]:
    """
    Build the 91-point daily balance array for the forecast period.
    
    B(0) = current_available_balance - sum(pending_debits) - candidate_payment(day_0)
    B(t) = B(t-1) + income(t) - fixed_expenses(t) - flex_expenses(t) - debt(t) - candidate_payment(t)
    
    Args:
        twin: The financial digital twin
        candidate_payments: Dict mapping date → payment amount (in home currency)
        spending_changes: Dict with 'stop' and 'reduce' keys for expense modifications
    
    Returns:
        List of 91 floats representing closing balance for days 0..90
    """
    if candidate_payments is None:
        candidate_payments = {}
    if spending_changes is None:
        spending_changes = {}
    
    # Parse spending changes into lookup structures
    stopped_event_ids = set()
    reduced_events = {}  # event_id → new_amount
    
    if spending_changes:
        for change in spending_changes.get("changes", []):
            if change["type"] == "stop":
                stopped_event_ids.add(change["event_id"])
            elif change["type"] == "reduce_to":
                reduced_events[change["event_id"]] = change["new_amount"]
    
    request_date = twin.request_date
    home_currency = twin.home_currency
    min_bal = twin.minimum_balance_to_keep
    
    # ── Build day-indexed cash flow map ──
    # Map: day_offset → list of (amount, direction, source)
    day_flows: Dict[int, List[Tuple[float, str, str]]] = defaultdict(list)
    
    # 1. Pending debits: deduct immediately on day 0
    pending_debit_total = 0.0
    for e in twin.pending_debits:
        if e.amount is not None:
            amt = convert_to_home_currency(
                e.amount, e.currency, home_currency,
                e.settlement_date, twin.fx_rates, twin.fx_rate_dates
            )
            pending_debit_total += amt
    
    # 2. Scheduled events in the forecast window
    for e in twin.scheduled_events:
        day_offset = (e.settlement_date - request_date).days
        if 0 <= day_offset <= FORECAST_DAYS and e.amount is not None:
            amt = convert_to_home_currency(
                e.amount, e.currency, home_currency,
                e.settlement_date, twin.fx_rates, twin.fx_rate_dates
            )
            day_flows[day_offset].append((amt, e.direction, f"scheduled:{e.event_id}"))
    
    # 3. Projected recurring events
    for pe in twin.projected_events:
        day_offset = (pe.projected_date - request_date).days
        if 0 <= day_offset <= FORECAST_DAYS:
            amt = pe.amount
            
            # Apply spending changes to projected events
            source_pattern = pe.source_pattern
            if source_pattern:
                # Check if any source event is stopped
                pattern_stopped = any(
                    eid in stopped_event_ids 
                    for eid in source_pattern.event_ids
                )
                if pattern_stopped and pe.direction == "debit":
                    continue  # Skip this expense
                
                # Check if any source event is reduced
                for eid in source_pattern.event_ids:
                    if eid in reduced_events:
                        amt = reduced_events[eid]
                        break
            
            # Convert currency for projected events
            curr = getattr(pe, 'currency', home_currency)
            amt = convert_to_home_currency(
                amt, curr, home_currency,
                pe.projected_date, twin.fx_rates, twin.fx_rate_dates
            )
            day_flows[day_offset].append((amt, pe.direction, f"projected:{pe.category}"))
    
    # 4. Candidate payments
    for pay_date, pay_amount in candidate_payments.items():
        day_offset = (pay_date - request_date).days
        if 0 <= day_offset <= FORECAST_DAYS:
            day_flows[day_offset].append((pay_amount, "debit", "candidate_payment"))
    
    # ── Compute daily balances ──
    balances = [0.0] * (FORECAST_DAYS + 1)
    
    # Day 0: starting balance minus pending debits
    balances[0] = twin.current_available_balance - pending_debit_total
    
    # Apply day 0 flows
    for amt, direction, source in day_flows.get(0, []):
        if direction == "debit":
            balances[0] -= amt
        elif direction == "credit":
            balances[0] += amt
    
    # Days 1..90
    for t in range(1, FORECAST_DAYS + 1):
        balances[t] = balances[t - 1]
        for amt, direction, source in day_flows.get(t, []):
            if direction == "debit":
                balances[t] -= amt
            elif direction == "credit":
                balances[t] += amt
    
    return balances


def compute_safe_amount(twin: FinancialDigitalTwin) -> float:
    """
    Compute amount_safe_to_pay using the baseline simulation.
    
    1. Simulate baseline (zero purchase, zero spending changes)
    2. Find minimum headroom across all 91 days
    3. Cap at requested_amount
    4. VERIFY: simulate with the computed amount to confirm safety
    
    If closed-form and simulation disagree, simulation wins.
    """
    # Step 1: Baseline simulation (no candidate payment)
    baseline = build_daily_cashflow(twin)
    
    # Step 2: Minimum headroom
    min_balance = twin.minimum_balance_to_keep
    min_headroom = min(b - min_balance for b in baseline)
    
    # Step 3: Closed-form safe amount
    safe_amount = max(0.0, min_headroom)
    safe_amount = min(safe_amount, twin.requested_amount)
    
    # Step 4: VERIFY by simulation
    if safe_amount > 0:
        test_payments = {twin.request_date: safe_amount}
        verified_balances = build_daily_cashflow(twin, candidate_payments=test_payments)
        if any(b < min_balance - 0.01 for b in verified_balances):
            # Simulation disagrees — binary search for actual safe amount
            safe_amount = _binary_search_safe_amount(twin, 0.0, safe_amount)
    
    return round(safe_amount, 2)


def _binary_search_safe_amount(
    twin: FinancialDigitalTwin,
    lo: float,
    hi: float,
    tolerance: float = 0.01,
) -> float:
    """Binary search for the maximum safe payment amount, verified by simulation."""
    min_balance = twin.minimum_balance_to_keep
    
    for _ in range(50):  # max iterations
        if hi - lo < tolerance:
            break
        mid = (lo + hi) / 2
        test_payments = {twin.request_date: mid}
        balances = build_daily_cashflow(twin, candidate_payments=test_payments)
        if all(b >= min_balance - 0.005 for b in balances):
            lo = mid  # mid is safe, try higher
        else:
            hi = mid  # mid is unsafe, try lower
    
    return round(lo, 2)


def compute_earliest_date(twin: FinancialDigitalTwin) -> str:
    """
    Compute earliest_date_for_full_payment.
    
    For each candidate date from request_date to request_date + 90:
    - Simulate the full requested_amount payment on that date
    - The date is valid ONLY if the complete simulation remains above
      minimum_balance_to_keep for ALL days from that date through day 90
    
    Returns YYYY-MM-DD string or empty string if never safe.
    Must equal request_date for affordable_now.
    """
    min_balance = twin.minimum_balance_to_keep
    
    for day_offset in range(0, FORECAST_DAYS + 1):
        candidate_date = twin.request_date + timedelta(days=day_offset)
        
        # Simulate full payment on candidate_date
        test_payments = {candidate_date: twin.requested_amount}
        balances = build_daily_cashflow(twin, candidate_payments=test_payments)
        
        # Check ALL days from 0 through 90 (the full horizon)
        if all(b >= min_balance - 0.01 for b in balances):
            return candidate_date.strftime("%Y-%m-%d")
    
    return ""


def simulate_plan(
    twin: FinancialDigitalTwin,
    payments: Dict[date, float],
    spending_changes: Optional[Dict[str, object]] = None,
) -> bool:
    """
    Simulate a complete payment plan and verify safety.
    
    Returns True if balance >= minimum_balance_to_keep for all t in [0, 90].
    """
    balances = build_daily_cashflow(twin, payments, spending_changes)
    min_balance = twin.minimum_balance_to_keep
    return all(b >= min_balance - 0.01 for b in balances)
