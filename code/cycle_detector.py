"""
FinCredTwin Cycle Detector
Detects recurring financial events and projects future occurrences 
into the 90-day forecast window.

Official rules:
- "Detect recurrence only when history supports it."
- "Forecast essential variable spending conservatively."
- "Count confirmed salary on its settlement date."
- "Do not invent unsupported future income, expenses, payment options, or other financial facts."
"""
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from calendar import monthrange
import re
from typing import Dict, List, Optional, Set, Tuple
from statistics import mean, median

from data_loader import FinancialEvent


@dataclass
class RecurringPattern:
    """A detected recurring financial pattern."""
    user_id: str
    category: str
    description: str
    direction: str
    frequency_days: int  # Detected interval in days (30 for monthly)
    typical_amount: float  # Modal or median amount
    last_occurrence: date  # Most recent historical settlement date
    historical_count: int  # How many times observed
    event_ids: List[str]  # Source event IDs
    flexibility: str = "fixed"  # 'fixed' or flexibility from events
    minimum_allowed_amount: Optional[float] = None
    is_calendar_monthly: bool = False
    day_of_month: int = 1
    currency: str = "USD"
    stream: str = "primary_payroll"


@dataclass
class ProjectedEvent:
    """A future event projected from a recurring pattern."""
    projected_date: date
    amount: float
    direction: str  # 'debit' or 'credit'
    category: str
    description: str
    source_pattern: Optional[RecurringPattern] = None
    is_salary: bool = False
    currency: str = "USD"


def add_calendar_months(start_date: date, day_of_month: int, n_months: int = 1) -> date:
    """
    Advance date by n calendar months to a specific target day of month.
    Handles month-end boundaries (e.g. Feb 28 in non-leap years, 30 vs 31).
    """
    year = start_date.year
    month = start_date.month + n_months
    while month > 12:
        month -= 12
        year += 1
    max_days = monthrange(year, month)[1]
    return date(year, month, min(day_of_month, max_days))


# One-off credits / bonuses / arrears that do NOT represent recurring base salary
EXCLUDE_SALARY_DESCS: Set[str] = {
    "quarterly performance bonus",
    "promotion arrears payment",
    "performance commission",
    "account commission payment",
    "monthly sales commission",
}

# Employment termination descriptions: future salary must terminate
TERMINAL_SALARY_DESCS: Set[str] = {
    "final employer payroll",
    "previous employer payroll",
}

# Secondary gig/freelance descriptions
GIG_SALARY_DESCS: Set[str] = {
    "driver platform payout",
    "delivery platform payout",
    "task marketplace payout",
    "weekly app earnings",
    "freelance milestone payment",
}

# Discretionary variable spending categories: only project if calendar monthly
DISCRETIONARY_VARIABLE: Set[str] = {
    "dining", "shopping", "entertainment"
}


def salary_stream_key(desc: str) -> str:
    """Classify salary event into distinct independent income streams."""
    d = desc.lower().strip()
    if "second household income" in d:
        return "second_household_income"
    if any(g in d for g in ("delivery platform", "driver platform", "task marketplace", "weekly app")):
        return "gig_earnings"
    if any(f in d for f in ("freelance", "consulting", "retainer", "website project", "content contract", "design contract")):
        return "freelance_invoice"
    return "primary_payroll"


def obligation_stream_key(category: str, desc: str) -> str:
    """Classify fixed recurring obligations (e.g. loans, insurance) into distinct streams by description."""
    if category in ("debt_repayment", "loan", "mortgage", "insurance"):
        d = desc.lower().strip()
        d_clean = re.sub(r'[^a-z0-9]+', '_', d).strip('_')
        return d_clean or "main"
    return "main"


def detect_cycles(
    historical_events: List[FinancialEvent],
    user_id: str,
    active_credits: Optional[List[FinancialEvent]] = None,
) -> List[RecurringPattern]:
    """
    Detect recurring patterns from historical settled events.
    
    Distinguishes independent salary streams to avoid spurious bi-weekly cycles.
    Separates fixed recurring bills from variable spending.
    Uses modal day of month for monthly cycles.
    """
    groups = defaultdict(list)
    
    for event in historical_events:
        if event.status != "settled" or event.amount is None:
            continue
        
        if event.category == "salary":
            desc_clean = event.description.lower().strip()
            if desc_clean in EXCLUDE_SALARY_DESCS:
                continue
            stream = salary_stream_key(event.description)
            groups[("salary", event.direction, stream)].append(event)
        elif event.category in ("debt_repayment", "loan", "mortgage", "insurance"):
            stream = obligation_stream_key(event.category, event.description)
            groups[(event.category, event.direction, stream)].append(event)
        else:
            groups[(event.category, event.direction, "main")].append(event)
    
    # Scheduled salary continuation
    if active_credits:
        for e in active_credits:
            if e.category == "salary" and e.status == "scheduled" and e.amount is not None:
                stream = salary_stream_key(e.description)
                key = ("salary", "credit", stream)
                if len(groups.get(key, [])) >= 1:
                    groups[key].append(e)

    patterns = []
    
    for (category, direction, stream), events in groups.items():
        if len(events) < 2:
            continue
        
        events.sort(key=lambda e: e.settlement_date)
        
        if category == "salary":
            last_desc = events[-1].description.lower().strip()
            if last_desc in TERMINAL_SALARY_DESCS:
                continue
        
        intervals = []
        for i in range(1, len(events)):
            delta = (events[i].settlement_date - events[i-1].settlement_date).days
            if delta > 0:
                intervals.append(delta)
        
        if not intervals:
            continue
        
        med_int = median(intervals)
        avg_int = mean(intervals)
        
        is_calendar_monthly = 27 <= med_int <= 33
        freq_days = 30
        if is_calendar_monthly:
            freq_days = 30
        elif 13 <= med_int <= 16:
            freq_days = 14
        elif 9 <= med_int <= 11:
            freq_days = 10
        elif 6 <= med_int <= 8:
            freq_days = 7
        elif 4 <= med_int <= 6:
            freq_days = 5
        elif 19 <= med_int <= 23:
            freq_days = 21
        elif len(intervals) >= 2 and avg_int <= 365:
            freq_days = round(avg_int)
        else:
            continue
        
        # Discretionary variable spending rule: only project if calendar monthly
        if category in DISCRETIONARY_VARIABLE and not is_calendar_monthly:
            continue
        
        amounts = [e.amount for e in events if e.amount is not None]
        if category in {"groceries", "transport"}:
            typical_amount = median(amounts)
        else:
            typical_amount = amounts[-1]
            
        last_event = events[-1]
        
        # Determine regular day of month using mode
        days_of_month = [e.settlement_date.day for e in events]
        mode_day = Counter(days_of_month).most_common(1)[0][0]
        
        pat = RecurringPattern(
            user_id=user_id,
            category=category,
            description=last_event.description,
            direction=direction,
            frequency_days=freq_days,
            typical_amount=typical_amount,
            last_occurrence=last_event.settlement_date,
            historical_count=len(events),
            event_ids=[e.event_id for e in events],
            flexibility=last_event.flexibility or "fixed",
            minimum_allowed_amount=last_event.minimum_allowed_amount,
            is_calendar_monthly=is_calendar_monthly,
            day_of_month=mode_day,
            currency=last_event.currency,
            stream=stream,
        )
        patterns.append(pat)

    return patterns


def project_future_events(
    patterns: List[RecurringPattern],
    request_date: date,
    forecast_days: int = 90,
    salary_amendments: Optional[Dict] = None,
    scheduled_events: Optional[List[FinancialEvent]] = None,
    expense_amendments: Optional[Dict] = None,
) -> List[ProjectedEvent]:
    """
    Project future occurrences into the 90-day forecast window.
    
    Key behaviors:
    1. Uses exact calendar-month advancement for monthly patterns.
    2. Projects secondary/gig income only if ongoing (not lapsed).
    3. Handles message-based salary amount and date adjustments.
    4. Handles message-based expense adjustments (e.g. confirmed rent increases).
    5. Deduplicates against already scheduled events per independent stream.
    6. Preserves original event currency for downstream FX conversion.
    """
    projected = []
    end_date = request_date + timedelta(days=forecast_days)
    
    scheduled_dates = defaultdict(set)
    if scheduled_events:
        for e in scheduled_events:
            if e.category in ("debt_repayment", "loan", "mortgage", "insurance"):
                stream = obligation_stream_key(e.category, e.description)
                scheduled_dates[(e.category, stream)].add(e.settlement_date)
            else:
                scheduled_dates[e.category].add(e.settlement_date)
    
    def _is_scheduled(pat: RecurringPattern, dt: date) -> bool:
        if pat.category in ("debt_repayment", "loan", "mortgage", "insurance"):
            return dt in scheduled_dates.get((pat.category, pat.stream), set())
        return dt in scheduled_dates.get(pat.category, set())
    
    for pattern in patterns:
        is_salary = pattern.category.lower() == "salary"
        
        # Check if non-primary credit pattern has lapsed
        if pattern.direction == "credit" and pattern.stream != "primary_payroll":
            days_since = (request_date - pattern.last_occurrence).days
            if days_since > pattern.frequency_days * 1.3:
                continue
        
        # Contract termination check from messages
        if salary_amendments and is_salary:
            if salary_amendments.get("contract_ended", False):
                continue
        
        base_amount = pattern.typical_amount
        if salary_amendments and is_salary and pattern.stream == "primary_payroll":
            amended_amount = salary_amendments.get("salary_amount")
            if amended_amount is not None:
                base_amount = amended_amount
        
        def _get_occurrence_amount(dt: date) -> float:
            amt = base_amount
            if expense_amendments and pattern.category in expense_amendments:
                exp_info = expense_amendments[pattern.category]
                eff_date = exp_info.get("effective_date")
                if not eff_date or dt >= eff_date:
                    pct = exp_info.get("percentage_increase")
                    new_amt = exp_info.get("new_amount")
                    if pct is not None:
                        amt = round(base_amount * (1.0 + pct / 100.0), 2)
                    elif new_amt is not None:
                        amt = new_amt
            return amt
        
        is_cal_monthly = pattern.is_calendar_monthly
        day_of_month = pattern.day_of_month
        curr_p = pattern.currency
        
        if is_cal_monthly:
            shifted_date = None
            if salary_amendments and is_salary and pattern.stream == "primary_payroll":
                shifted_date = salary_amendments.get("salary_date")
            
            if shifted_date and shifted_date >= request_date:
                curr_date = shifted_date
                day_of_month = shifted_date.day
                # Include shifted date itself if in forecast window
                if curr_date <= end_date and not _is_scheduled(pattern, curr_date):
                    pe = ProjectedEvent(
                        projected_date=curr_date,
                        amount=_get_occurrence_amount(curr_date),
                        direction=pattern.direction,
                        category=pattern.category,
                        description=pattern.description,
                        source_pattern=pattern,
                        is_salary=is_salary,
                        currency=curr_p,
                    )
                    projected.append(pe)
                
                # Advance for subsequent months
                while True:
                    curr_date = add_calendar_months(curr_date, day_of_month, 1)
                    if curr_date > end_date:
                        break
                    if _is_scheduled(pattern, curr_date):
                        continue
                    pe = ProjectedEvent(
                        projected_date=curr_date,
                        amount=_get_occurrence_amount(curr_date),
                        direction=pattern.direction,
                        category=pattern.category,
                        description=pattern.description,
                        source_pattern=pattern,
                        is_salary=is_salary,
                        currency=curr_p,
                    )
                    projected.append(pe)
            else:
                curr_date = pattern.last_occurrence
                while True:
                    curr_date = add_calendar_months(curr_date, day_of_month, 1)
                    if curr_date > end_date:
                        break
                    if curr_date < request_date:
                        continue
                    if _is_scheduled(pattern, curr_date):
                        continue
                    pe = ProjectedEvent(
                        projected_date=curr_date,
                        amount=_get_occurrence_amount(curr_date),
                        direction=pattern.direction,
                        category=pattern.category,
                        description=pattern.description,
                        source_pattern=pattern,
                        is_salary=is_salary,
                        currency=curr_p,
                    )
                    projected.append(pe)
        else:
            curr_date = pattern.last_occurrence
            while True:
                curr_date = curr_date + timedelta(days=pattern.frequency_days)
                if curr_date > end_date:
                    break
                if curr_date < request_date:
                    continue
                if _is_scheduled(pattern, curr_date):
                    continue
                pe = ProjectedEvent(
                    projected_date=curr_date,
                    amount=_get_occurrence_amount(curr_date),
                    direction=pattern.direction,
                    category=pattern.category,
                    description=pattern.description,
                    source_pattern=pattern,
                    is_salary=is_salary,
                    currency=curr_p,
                )
                projected.append(pe)
                
    return projected
