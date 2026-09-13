"""
FinCredTwin Financial State Builder
Constructs the Financial Digital Twin for a given request.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Set

from data_loader import (
    DataStore, FinancialEvent, FinancialProfile, PaymentOption, Request,
)
from cycle_detector import ProjectedEvent, RecurringPattern


@dataclass
class FinancialDigitalTwin:
    """
    The complete financial state of a user as of request_date.
    Everything needed to run the 90-day simulation.
    """
    # Request context
    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: float
    desired_completion_date: date
    allows_partial_payment: bool
    request_text: str
    
    # Profile
    home_currency: str
    current_available_balance: float
    minimum_balance_to_keep: float
    financial_priorities: List[str]
    expense_categories_to_protect: Set[str]
    expense_categories_user_is_willing_to_reduce: Set[str]
    expense_categories_user_is_willing_to_stop: Set[str]
    payment_methods_user_will_consider: Set[str]
    max_installment_months: Optional[int]
    
    # Resolved events
    pending_debits: List[FinancialEvent] = field(default_factory=list)
    scheduled_events: List[FinancialEvent] = field(default_factory=list)
    
    # Projected recurring events
    projected_events: List[ProjectedEvent] = field(default_factory=list)
    recurring_patterns: List[RecurringPattern] = field(default_factory=list)
    
    # Payment options available for this request
    payment_options: List[PaymentOption] = field(default_factory=list)
    
    # Flexible recurring expenses (candidates for spending changes)
    flexible_expenses: List[FinancialEvent] = field(default_factory=list)
    
    # Exchange rate lookup
    fx_rates: Dict[tuple, float] = field(default_factory=dict)
    fx_rate_dates: List[date] = field(default_factory=list)
    
    # Computed fields (populated by forecast engine)
    amount_safe_to_pay: float = 0.0
    earliest_date_for_full_payment: str = ""


def build_twin(
    request: Request,
    store: DataStore,
    historical_events: List[FinancialEvent],
    active_debits: List[FinancialEvent],
    active_credits: List[FinancialEvent],
    projected_events: List[ProjectedEvent],
    recurring_patterns: List[RecurringPattern],
) -> FinancialDigitalTwin:
    """
    Assemble the Financial Digital Twin for a request.
    """
    profile = store.profiles[request.user_id]
    options = store.options_by_request.get(request.request_id, [])
    
    # Collect all pending/scheduled events
    pending_debits = [
        e for e in active_debits 
        if e.status == "pending" and e.direction == "debit"
    ]
    
    scheduled_events = []
    for e in active_debits + active_credits:
        if e.status == "scheduled":
            scheduled_events.append(e)
    
    # Identify flexible recurring expenses for potential spending changes
    flexible_expenses = _find_flexible_expenses(
        recurring_patterns, historical_events, profile
    )
    
    return FinancialDigitalTwin(
        request_id=request.request_id,
        user_id=request.user_id,
        request_date=request.request_date,
        request_type=request.request_type,
        requested_amount=request.requested_amount,
        desired_completion_date=request.desired_completion_date,
        allows_partial_payment=request.allows_partial_payment,
        request_text=request.request_text,
        home_currency=profile.home_currency,
        current_available_balance=profile.current_available_balance,
        minimum_balance_to_keep=profile.minimum_balance_to_keep,
        financial_priorities=profile.financial_priorities,
        expense_categories_to_protect=profile.expense_categories_to_protect,
        expense_categories_user_is_willing_to_reduce=profile.expense_categories_user_is_willing_to_reduce,
        expense_categories_user_is_willing_to_stop=profile.expense_categories_user_is_willing_to_stop,
        payment_methods_user_will_consider=profile.payment_methods_user_will_consider,
        max_installment_months=profile.max_installment_months,
        pending_debits=pending_debits,
        scheduled_events=scheduled_events,
        projected_events=projected_events,
        recurring_patterns=recurring_patterns,
        payment_options=options,
        flexible_expenses=flexible_expenses,
        fx_rates=store.fx_rates,
        fx_rate_dates=store.fx_rate_dates,
    )


def _find_flexible_expenses(
    patterns: List[RecurringPattern],
    historical_events: List[FinancialEvent],
    profile: FinancialProfile,
) -> List[FinancialEvent]:
    """
    Find recurring expense events that are flexible (reducible or stoppable)
    and not in protected categories.
    
    Returns the most recent event for each flexible pattern.
    """
    flexible = []
    
    for pattern in patterns:
        if pattern.direction != "debit":
            continue
        
        # Must not be in protected categories
        if pattern.category in profile.expense_categories_to_protect:
            continue
        
        # Check flexibility
        if pattern.flexibility not in ("stoppable", "reducible", "reducible_or_stoppable"):
            continue
        
        # Check if user is willing to reduce or stop this category
        can_reduce = pattern.category in profile.expense_categories_user_is_willing_to_reduce
        can_stop = pattern.category in profile.expense_categories_user_is_willing_to_stop
        
        if not (can_reduce or can_stop):
            continue
        
        # Find the most recent historical event for this pattern
        for eid in reversed(pattern.event_ids):
            for e in historical_events:
                if e.event_id == eid:
                    flexible.append(e)
                    break
            else:
                continue
            break
    
    return flexible
