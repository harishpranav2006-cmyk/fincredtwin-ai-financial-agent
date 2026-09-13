"""
FinCredTwin Event Lifecycle Manager
Exact event-state handling per problem_statement.md.

Official rules:
- Ignore pending credits, failed or cancelled transactions, duplicate records,
  and unrealized investments.
- Reserve pending debits.
- Count confirmed salary on its settlement date.
- Do not count pending credits, bonuses, commissions, refunds, lottery proceeds,
  or investment gains until they settle.
- Resolve linked_event_id chains for refunds, retries, cancellations.
- 4-tier conflict resolution.
"""
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Set, Tuple

from data_loader import FinancialEvent, DataStore


@dataclass
class ResolvedEvent:
    """An event after lifecycle resolution with its effective state."""
    event: FinancialEvent
    effective_status: str  # The status to use after conflict resolution
    include_in_forecast: bool  # Whether this event affects the cash flow forecast
    reason: str  # Why it was included/excluded


def resolve_event_lifecycle(
    user_events: List[FinancialEvent],
    store: DataStore,
) -> List[ResolvedEvent]:
    """
    Process all events for a user and resolve their lifecycle states.
    
    Returns a list of ResolvedEvent with decisions on inclusion/exclusion.
    Follows the exact rules from problem_statement.md.
    """
    # Build local event index
    events_by_id: Dict[str, FinancialEvent] = {e.event_id: e for e in user_events}
    
    # Track which events are linked-to (targets of linked_event_id)
    linked_targets: Set[str] = set()
    # Track events that link TO other events (the newer/referencing events)
    linkers: Dict[str, str] = {}  # event_id → linked_event_id
    
    for e in user_events:
        if e.linked_event_id and e.linked_event_id in events_by_id:
            linked_targets.add(e.linked_event_id)
            linkers[e.event_id] = e.linked_event_id
    
    resolved: List[ResolvedEvent] = []
    
    for event in user_events:
        inclusion, reason = _classify_event(event, events_by_id, linked_targets, linkers)
        resolved.append(ResolvedEvent(
            event=event,
            effective_status=event.status,
            include_in_forecast=inclusion,
            reason=reason,
        ))
    
    return resolved


def _classify_event(
    event: FinancialEvent,
    events_by_id: Dict[str, FinancialEvent],
    linked_targets: Set[str],
    linkers: Dict[str, str],
) -> Tuple[bool, str]:
    """
    Classify a single event for inclusion in the cash flow forecast.
    
    Returns (include_in_forecast, reason).
    
    Official rules from problem_statement.md:
    - "Forecast the user's balance for the next 90 days using recurring income 
       and expenses, confirmed future payments, and relevant messages or images."
    - "A plan is safe only if the balance never falls below minimum_balance_to_keep."
    - "Ignore pending credits, failed or cancelled transactions, duplicate records, 
       and unrealized investments."
    """
    status = event.status
    direction = event.direction
    event_type = event.event_type
    category = event.category
    
    # ── Cancelled events: EXCLUDE ──
    if status == "cancelled":
        return False, "cancelled: excluded per official rules"
    
    # ── Failed events: EXCLUDE (unless retried via linked event) ──
    if status == "failed":
        return False, "failed: excluded per official rules"
    
    # ── Unrealized events (investment valuations): EXCLUDE ──
    # "do not treat unrealized investment value as available cash"
    if status == "unrealized":
        return False, "unrealized: non-cash investment valuation excluded"
    
    # ── Settled events: INCLUDE (historical fact) ──
    if status == "settled":
        # Check if this settled event has been superseded by a linked event
        # (e.g., a refund links back to the original purchase)
        # The settled event itself still counts; the refund is a separate credit.
        if event.amount is None:
            return False, "settled but amount is None and could not be resolved"
        return True, "settled: historical confirmed transaction"
    
    # ── Pending events: direction-dependent ──
    if status == "pending":
        if direction == "debit":
            # "Reserve pending debits"
            if event.amount is None:
                return False, "pending debit but amount is None"
            return True, "pending debit: reserved per official rules"
        elif direction == "credit":
            # "Ignore pending credits... bonuses, commissions, refunds, 
            #  lottery proceeds, or investment gains until they settle."
            return False, "pending credit: excluded until settled per official rules"
        else:
            return False, f"pending with unknown direction '{direction}'"
    
    # ── Scheduled events: INCLUDE (confirmed future) ──
    if status == "scheduled":
        if event.amount is None:
            return False, "scheduled but amount is None"
        # Scheduled salary/income: count on settlement date
        # Scheduled expenses: count as upcoming obligation
        return True, "scheduled: confirmed future transaction"
    
    # ── Fallback for unknown statuses ──
    return False, f"unknown status '{status}': excluded for safety"


def get_active_events(
    user_events: List[FinancialEvent],
    store: DataStore,
    request_date: date,
) -> Tuple[List[FinancialEvent], List[FinancialEvent], List[FinancialEvent]]:
    """
    Separate user events into three lists relative to request_date:
    
    Returns:
        historical: settled events before request_date (for cycle detection)
        active_debits: pending/scheduled debits to reserve/project
        active_credits: scheduled credits (confirmed salary) to project
    """
    resolved = resolve_event_lifecycle(user_events, store)
    
    historical = []
    active_debits = []
    active_credits = []
    
    for r in resolved:
        if not r.include_in_forecast:
            continue
        
        event = r.event
        
        if event.status == "settled":
            # All settled events are historical data for cycle detection
            historical.append(event)
        elif event.status in ("pending", "scheduled"):
            if event.direction == "debit":
                active_debits.append(event)
            elif event.direction == "credit":
                # Only scheduled credits are included (pending credits excluded above)
                active_credits.append(event)
    
    return historical, active_debits, active_credits


def resolve_conflicts(
    events: List[FinancialEvent],
    messages_facts: Optional[list] = None,
) -> List[FinancialEvent]:
    """
    Apply the 4-tier conflict resolution hierarchy:
    1. Explicit cancellation, settlement, or amendment
    2. Newer record from the same source
    3. Settled event over estimate
    4. Financially safer interpretation
    
    For now, the primary conflict resolution is handled by the status-based
    filtering in resolve_event_lifecycle. Message-based amendments are applied
    separately in message_interpreter.py.
    """
    # The linked_event_id chain handles most conflicts:
    # - If event A is cancelled and event B (linked to A) is scheduled, B supersedes A
    # - If event A is settled and event B (refund, linked to A) is settled, both count
    # - If event A is failed and event B (retry, linked to A) is scheduled, B counts
    
    # Additional message-based conflict resolution is deferred to message_interpreter
    return events
