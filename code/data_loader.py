"""
FinCredTwin Data Loader
CSV ingestion with type coercion and index building.
Fills blank amounts from image cache.
"""
import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Set

from config import (
    FINANCIAL_EVENTS_CSV, FINANCIAL_PROFILES_CSV, EXCHANGE_RATES_CSV,
    IMAGES_CSV, MESSAGES_CSV, PAYMENT_OPTIONS_CSV, REQUESTS_CSV,
    SAMPLE_REQUESTS_CSV,
)
from image_extractor import get_image_amount_by_event, get_image_amount


# ── Typed Data Structures ─────────────────────────────────────────────

@dataclass
class Request:
    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: float
    desired_completion_date: date
    allows_partial_payment: bool
    request_text: str


@dataclass
class FinancialProfile:
    user_id: str
    home_currency: str
    current_available_balance: float
    minimum_balance_to_keep: float
    financial_priorities: List[str]
    expense_categories_to_protect: Set[str]
    expense_categories_user_is_willing_to_reduce: Set[str]
    expense_categories_user_is_willing_to_stop: Set[str]
    payment_methods_user_will_consider: Set[str]
    max_installment_months: Optional[int]


@dataclass
class FinancialEvent:
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str
    amount: Optional[float]
    currency: str
    event_date: date
    settlement_date: date
    status: str
    linked_event_id: Optional[str]
    flexibility: str
    minimum_allowed_amount: Optional[float]
    # Provenance: if amount was filled from image
    amount_source: str = "csv"  # 'csv' or 'image_cache:<image_id>'


@dataclass
class PaymentOption:
    payment_option_id: str
    request_id: str
    payment_method: str
    payment_amount: float
    number_of_payments: int
    first_payment_date: date
    payment_frequency_days: Optional[int]
    financing_fee: float
    total_payable_amount: float


@dataclass
class Message:
    message_id: str
    user_id: str
    request_id: Optional[str]
    related_event_id: Optional[str]
    sent_at: datetime
    source_type: str
    message_text: str


@dataclass
class ImageRecord:
    image_id: str
    user_id: str
    request_id: Optional[str]
    related_event_id: Optional[str]


@dataclass
class ExchangeRate:
    rate_date: date
    from_currency: str
    to_currency: str
    rate: float


@dataclass
class SampleRequest:
    """Sample request with ground-truth output fields for regression testing."""
    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: float
    desired_completion_date: date
    allows_partial_payment: bool
    request_text: str
    # Ground truth output fields
    amount_safe_to_pay: float
    affordability_status: str
    recommended_payment_method: str
    payment_plan: str
    earliest_date_for_full_payment: str
    spending_changes_needed: str
    decision_explanation: str


# ── Parsing Helpers ───────────────────────────────────────────────────

def _parse_date(s: str) -> date:
    """Parse YYYY-MM-DD date string."""
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def _parse_datetime(s: str) -> datetime:
    """Parse ISO datetime string."""
    s = s.strip()
    # Handle formats like 2025-07-29T09:30:00Z
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _parse_float(s: str) -> Optional[float]:
    """Parse float, return None for blank."""
    s = s.strip()
    if not s:
        return None
    return float(s)


def _parse_int(s: str) -> Optional[int]:
    """Parse int, return None for blank."""
    s = s.strip()
    if not s:
        return None
    return int(s)


def _parse_bool(s: str) -> bool:
    """Parse boolean from 'true'/'false' string."""
    return s.strip().lower() == "true"


def _parse_pipe_list(s: str) -> List[str]:
    """Parse pipe-delimited list, return empty list for blank."""
    s = s.strip()
    if not s:
        return []
    return [x.strip() for x in s.split("|") if x.strip()]


def _parse_pipe_set(s: str) -> Set[str]:
    """Parse pipe-delimited set, return empty set for blank."""
    return set(_parse_pipe_list(s))


def _opt_str(s: str) -> Optional[str]:
    """Return None for blank strings."""
    s = s.strip()
    return s if s else None


# ── CSV Readers ───────────────────────────────────────────────────────

def _read_csv(path) -> List[dict]:
    """Read CSV file and return list of row dicts."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def load_requests(path=None) -> List[Request]:
    rows = _read_csv(path or REQUESTS_CSV)
    return [
        Request(
            request_id=r["request_id"].strip(),
            user_id=r["user_id"].strip(),
            request_date=_parse_date(r["request_date"]),
            request_type=r["request_type"].strip(),
            requested_amount=float(r["requested_amount"]),
            desired_completion_date=_parse_date(r["desired_completion_date"]),
            allows_partial_payment=_parse_bool(r["allows_partial_payment"]),
            request_text=r["request_text"].strip(),
        )
        for r in rows
    ]


def load_profiles() -> Dict[str, FinancialProfile]:
    rows = _read_csv(FINANCIAL_PROFILES_CSV)
    profiles = {}
    for r in rows:
        uid = r["user_id"].strip()
        profiles[uid] = FinancialProfile(
            user_id=uid,
            home_currency=r["home_currency"].strip(),
            current_available_balance=float(r["current_available_balance"]),
            minimum_balance_to_keep=float(r["minimum_balance_to_keep"]),
            financial_priorities=_parse_pipe_list(r["financial_priorities"]),
            expense_categories_to_protect=_parse_pipe_set(r["expense_categories_to_protect"]),
            expense_categories_user_is_willing_to_reduce=_parse_pipe_set(r["expense_categories_user_is_willing_to_reduce"]),
            expense_categories_user_is_willing_to_stop=_parse_pipe_set(r["expense_categories_user_is_willing_to_stop"]),
            payment_methods_user_will_consider=_parse_pipe_set(r["payment_methods_user_will_consider"]),
            max_installment_months=_parse_int(r["max_installment_months"]),
        )
    return profiles


def load_events(images_by_event: Optional[Dict[str, ImageRecord]] = None) -> List[FinancialEvent]:
    """Load financial events and dynamically fill blank amounts via images.csv links."""
    rows = _read_csv(FINANCIAL_EVENTS_CSV)
    events = []
    for r in rows:
        eid = r["event_id"].strip()
        raw_amount = r["amount"].strip()
        amount = None
        amount_source = "csv"

        if raw_amount:
            amount = float(raw_amount)
        else:
            # Primary lookup: dynamic link from images.csv
            image_rec = images_by_event.get(eid) if images_by_event else None
            image_id = image_rec.image_id if image_rec else None
            
            # Secondary fallback: static map if images_by_event not provided
            if not image_id:
                prov_fallback = get_image_amount_by_event(eid)
                if prov_fallback:
                    image_id = prov_fallback.image_id
            
            if image_id:
                prov = get_image_amount(image_id)
                if prov:
                    amount = prov.amount
                    amount_source = f"image_cache:{prov.image_id}"
                else:
                    # Dynamic unseen image linked via images.csv
                    amount_source = f"image_file:{image_id}"
            # If still None, amount remains None — never treated as zero, never drop event row

        events.append(FinancialEvent(
            event_id=eid,
            user_id=r["user_id"].strip(),
            event_type=r["event_type"].strip(),
            description=r["description"].strip(),
            category=r["category"].strip(),
            direction=r["direction"].strip(),
            amount=amount,
            currency=r["currency"].strip(),
            event_date=_parse_date(r["event_date"]),
            settlement_date=_parse_date(r["settlement_date"]) if r["settlement_date"].strip() else _parse_date(r["event_date"]),
            status=r["status"].strip(),
            linked_event_id=_opt_str(r["linked_event_id"]),
            flexibility=r["flexibility"].strip() if r["flexibility"].strip() else "fixed",
            minimum_allowed_amount=_parse_float(r["minimum_allowed_amount"]),
            amount_source=amount_source,
        ))
    return events


def load_payment_options() -> List[PaymentOption]:
    rows = _read_csv(PAYMENT_OPTIONS_CSV)
    return [
        PaymentOption(
            payment_option_id=r["payment_option_id"].strip(),
            request_id=r["request_id"].strip(),
            payment_method=r["payment_method"].strip(),
            payment_amount=float(r["payment_amount"]),
            number_of_payments=int(r["number_of_payments"]),
            first_payment_date=_parse_date(r["first_payment_date"]),
            payment_frequency_days=_parse_int(r["payment_frequency_days"]),
            financing_fee=float(r["financing_fee"]),
            total_payable_amount=float(r["total_payable_amount"]),
        )
        for r in rows
    ]


def load_messages() -> List[Message]:
    rows = _read_csv(MESSAGES_CSV)
    return [
        Message(
            message_id=r["message_id"].strip(),
            user_id=r["user_id"].strip(),
            request_id=_opt_str(r["request_id"]),
            related_event_id=_opt_str(r["related_event_id"]),
            sent_at=_parse_datetime(r["sent_at"]),
            source_type=r["source_type"].strip(),
            message_text=r["message_text"].strip(),
        )
        for r in rows
    ]


def load_images() -> List[ImageRecord]:
    rows = _read_csv(IMAGES_CSV)
    return [
        ImageRecord(
            image_id=r["image_id"].strip(),
            user_id=r["user_id"].strip(),
            request_id=_opt_str(r["request_id"]),
            related_event_id=_opt_str(r["related_event_id"]),
        )
        for r in rows
    ]


def load_exchange_rates() -> List[ExchangeRate]:
    rows = _read_csv(EXCHANGE_RATES_CSV)
    return [
        ExchangeRate(
            rate_date=_parse_date(r["rate_date"]),
            from_currency=r["from_currency"].strip(),
            to_currency=r["to_currency"].strip(),
            rate=float(r["rate"]),
        )
        for r in rows
    ]


def load_sample_requests() -> List[SampleRequest]:
    rows = _read_csv(SAMPLE_REQUESTS_CSV)
    return [
        SampleRequest(
            request_id=r["request_id"].strip(),
            user_id=r["user_id"].strip(),
            request_date=_parse_date(r["request_date"]),
            request_type=r["request_type"].strip(),
            requested_amount=float(r["requested_amount"]),
            desired_completion_date=_parse_date(r["desired_completion_date"]),
            allows_partial_payment=_parse_bool(r["allows_partial_payment"]),
            request_text=r["request_text"].strip(),
            amount_safe_to_pay=float(r["amount_safe_to_pay"]),
            affordability_status=r["affordability_status"].strip(),
            recommended_payment_method=r["recommended_payment_method"].strip(),
            payment_plan=r["payment_plan"].strip(),
            earliest_date_for_full_payment=r["earliest_date_for_full_payment"].strip(),
            spending_changes_needed=r["spending_changes_needed"].strip(),
            decision_explanation=r["decision_explanation"].strip(),
        )
        for r in rows
    ]


# ── Index Builders ────────────────────────────────────────────────────

@dataclass
class DataStore:
    """Central data store with all loaded data and prebuilt indexes."""
    requests: List[Request] = field(default_factory=list)
    profiles: Dict[str, FinancialProfile] = field(default_factory=dict)
    events: List[FinancialEvent] = field(default_factory=list)
    payment_options: List[PaymentOption] = field(default_factory=list)
    messages: List[Message] = field(default_factory=list)
    images: List[ImageRecord] = field(default_factory=list)
    exchange_rates: List[ExchangeRate] = field(default_factory=list)
    
    # Prebuilt indexes
    events_by_user: Dict[str, List[FinancialEvent]] = field(default_factory=dict)
    events_by_id: Dict[str, FinancialEvent] = field(default_factory=dict)
    options_by_request: Dict[str, List[PaymentOption]] = field(default_factory=dict)
    messages_by_user: Dict[str, List[Message]] = field(default_factory=dict)
    images_by_event: Dict[str, ImageRecord] = field(default_factory=dict)
    # Exchange rate index: (rate_date, from_currency, to_currency) → rate
    fx_rates: Dict[tuple, float] = field(default_factory=dict)
    # All available rate dates for fallback
    fx_rate_dates: List[date] = field(default_factory=list)


def build_indexes(store: DataStore) -> None:
    """Build all lookup indexes on the data store."""
    from collections import defaultdict
    
    # Events by user
    ebu = defaultdict(list)
    for e in store.events:
        ebu[e.user_id].append(e)
        store.events_by_id[e.event_id] = e
    store.events_by_user = dict(ebu)
    
    # Payment options by request
    obr = defaultdict(list)
    for o in store.payment_options:
        obr[o.request_id].append(o)
    store.options_by_request = dict(obr)
    
    # Messages by user
    mbu = defaultdict(list)
    for m in store.messages:
        mbu[m.user_id].append(m)
    store.messages_by_user = dict(mbu)
    
    # Images by event
    for img in store.images:
        if img.related_event_id:
            store.images_by_event[img.related_event_id] = img
    
    # Exchange rates
    all_dates = set()
    for r in store.exchange_rates:
        store.fx_rates[(r.rate_date, r.from_currency, r.to_currency)] = r.rate
        all_dates.add(r.rate_date)
    store.fx_rate_dates = sorted(all_dates)


def load_all_data(request_path=None) -> DataStore:
    """Load all CSV files and build indexes."""
    store = DataStore()
    store.requests = load_requests(request_path)
    store.profiles = load_profiles()
    store.images = load_images()
    
    # Dynamic image-by-event association from images.csv
    images_by_event = {img.related_event_id: img for img in store.images if img.related_event_id}
    store.images_by_event = images_by_event
    
    store.events = load_events(images_by_event=images_by_event)
    store.payment_options = load_payment_options()
    store.messages = load_messages()
    store.exchange_rates = load_exchange_rates()
    build_indexes(store)
    return store
