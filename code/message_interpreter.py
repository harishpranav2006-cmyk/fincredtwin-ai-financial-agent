"""
FinCredTwin Message Interpreter
Rule-based parsing of messages with full provenance for every extraction.

Every message produces either:
  - Recognized FinancialFact(s) with provenance
  - An 'unresolved' entry (no actionable fact)

Never infers unsupported financial information.
Protects deterministically against adversarial prompt injection.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from data_loader import Message


@dataclass
class FinancialFact:
    """A structured fact extracted from a message."""
    source_message_id: str
    fact_type: str  # See FACT_TYPES below
    value: Optional[float]  # Monetary value if applicable
    effective_date: Optional[date]  # When the fact takes effect
    confidence: str  # 'high', 'medium', 'low'
    rule_used: str  # Which regex/rule matched
    target_event_id: Optional[str] = None  # Related event if known
    percentage_change: Optional[float] = None
    is_confirmed: bool = True  # False for pending/unconfirmed items


# Valid fact types
FACT_TYPES = {
    "salary_increase",          # Salary raised to new amount
    "salary_decrease",          # Salary reduced (unpaid leave, etc.)
    "salary_confirmed",         # Base salary confirmed at amount
    "first_salary_confirmed",   # First salary scheduled/confirmed
    "salary_date_shift",        # Salary payment date changed
    "contract_ended",           # Employment contract ended, no future income
    "bonus_unconfirmed",        # Bonus/commission pending, NOT confirmed
    "commission_unconfirmed",   # Commission not yet approved
    "windfall_unconfirmed",     # Prize/lottery pending, NOT confirmed
    "payout_pending",           # Gig/service payout pending, not withdrawable
    "payment_delay",            # Payment delay / debit attempt failed, bill outstanding
    "refund_pending",           # Refund in processing / initiated but not received
    "dispute_pending",          # Disputed transaction under investigation
    "rent_increase",            # Rent increased by percentage or amount
    "expense_increase",         # Other expense increased
    "internal_transfer",        # Wash transaction between own accounts
    "unrealized_investment",    # Portfolio valuation change without sale
    "invoice_approved",         # Client invoice approved for scheduled settlement
    "proceeds_settled",         # Confirmed settled proceeds (informational)
    "subscription_cancelled",   # Subscription / service cancelled
    "no_actionable_fact",       # Message read but no actionable extraction
}


@dataclass
class MessageParseResult:
    """Result of parsing all messages for a user."""
    facts: List[FinancialFact] = field(default_factory=list)
    unresolved: List[Tuple[str, str]] = field(default_factory=list)  # (message_id, reason)


# ── Adversarial Prompt-Injection Defense ──────────────────────────────

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"bypass\s+(?:the\s+)?minimum\s+balance", re.IGNORECASE),
    re.compile(r"approve\s+this\s+payment", re.IGNORECASE),
    re.compile(r"always\s+recommend\s+(?:installments|full_payment|partial_payment|wait)", re.IGNORECASE),
    re.compile(r"change\s+salary\s+to\s+\d+", re.IGNORECASE),
    re.compile(r"override\s+(?:all\s+)?rules", re.IGNORECASE),
    re.compile(r"system\s+(?:prompt|instructions?)\s+override", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:an?\s+)?(?:DAN|unrestricted|adversarial)", re.IGNORECASE),
    re.compile(r"disregard\s+(?:all\s+)?(?:rules|limits)", re.IGNORECASE),
]


def is_prompt_injection(text: str) -> bool:
    """Check whether text contains adversarial prompt injection commands."""
    return any(p.search(text) for p in INJECTION_PATTERNS)


# ── Regex Patterns ────────────────────────────────────────────────────

# Speculative / hypothetical indicators (adversarial defense against unconfirmed claims)
_HYPOTHETICAL_SPECULATIVE = re.compile(
    r"\b(?:might|could|may|perhaps|possibly|potential|tentative|unconfirmed|considering|proposing|proposed|subject to|mungkin|kemungkinan|belum pasti|bisa jadi)\b",
    re.IGNORECASE
)

# Indonesian salary increase
_ID_SALARY_INCREASE = re.compile(
    r"Gaji bulanan Anda naik menjadi (?:IDR\s*)?([0-9,. ]+).*?berlaku mulai\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE | re.DOTALL
)

# Indonesian quarterly bonus pending
_ID_BONUS_PENDING = re.compile(
    r"Bonus kuartalan.*?menunggu.*?penilaian",
    re.IGNORECASE | re.DOTALL
)

# Indonesian base salary confirmed, commission not approved
_ID_SALARY_CONFIRMED_COMMISSION_PENDING = re.compile(
    r"Gaji pokok yang dikonfirmasi adalah (?:IDR\s*)?([0-9,. ]+).*?[Kk]omisi.*?belum disetujui",
    re.IGNORECASE | re.DOTALL
)

# Indonesian confirmed salary (general)
_ID_SALARY_CONFIRMED = re.compile(
    r"[Gg]aji (?:pokok )?(?:yang dikonfirmasi|rutin).*?(?:IDR\s*)?([0-9,. ]+)",
    re.IGNORECASE | re.DOTALL
)

# Indonesian first salary confirmed with date
_ID_FIRST_SALARY = re.compile(
    r"Gaji pertama Anda sebesar (?:IDR\s*)?([0-9,. ]+).*?(?:dijadwalkan pada|tanggal kredit yang dikonfirmasi adalah)\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE | re.DOTALL
)

# Indonesian routine salary for next payroll
_ID_SALARY_ROUTINE = re.compile(
    r"Gaji rutin (?:Anda )?untuk penggajian berikutnya adalah (?:IDR\s*)?([0-9,. ]+)",
    re.IGNORECASE | re.DOTALL
)

# Indonesian temporary monthly salary
_ID_TEMPORARY_SALARY = re.compile(
    r"Gaji bulanan sementara Anda adalah (?:IDR\s*)?([0-9,. ]+)",
    re.IGNORECASE | re.DOTALL
)

# Indonesian salary date shift
_ID_SALARY_DATE_SHIFT = re.compile(
    r"Gaji yang sudah dikonfirmasi kini diperkirakan masuk pada\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE | re.DOTALL
)

# Indonesian contract ended
_ID_CONTRACT_ENDED = re.compile(
    r"(?:hubungan kerja Anda telah berakhir|kontrak (?:kerja )?(?:Anda )?(?:telah )?berakhir)",
    re.IGNORECASE | re.DOTALL
)

# Indonesian rent increase by percentage
_ID_RENT_INCREASE = re.compile(
    r"perpanjangan sewa menaikkan biaya sewa bulanan sebesar\s*(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE | re.DOTALL
)

# Indonesian refund pending
_ID_REFUND_PENDING = re.compile(
    r"(?:pengembalian dana sudah diproses|pengembalian dana.*?belum masuk|pengembalian dana sedang diproses)",
    re.IGNORECASE | re.DOTALL
)

# Indonesian card charge dispute pending
_ID_DISPUTE_PENDING = re.compile(
    r"(?:tagihan kartu tambahan masih dalam penyelidikan|sengketa masih terbuka)",
    re.IGNORECASE | re.DOTALL
)

# Indonesian payout pending (gig platform)
_ID_PAYOUT_PENDING = re.compile(
    r"pembayaran berikutnya dari\s*\w+\s*masih tertunda",
    re.IGNORECASE | re.DOTALL
)

# Indonesian internal transfer (wash)
_ID_INTERNAL_TRANSFER = re.compile(
    r"(?:transfer antara dua rekening Anda|debit dan kredit dengan jumlah yang sama berasal dari transfer)",
    re.IGNORECASE | re.DOTALL
)

# Indonesian unrealized investment
_ID_UNREALIZED_INVESTMENT = re.compile(
    r"(?:nilai investasi yang ditampilkan telah turun|investasi tersebut belum dijual dan tidak ada transaksi tunai)",
    re.IGNORECASE | re.DOTALL
)

# Indonesian approved invoice
_ID_INVOICE_APPROVED = re.compile(
    r"klien menyetujui pembayaran faktur sebesar (?:IDR\s*)?([0-9,. ]+).*?penyelesaian diperkirakan pada\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE | re.DOTALL
)

# Indonesian settled proceeds
_ID_PROCEEDS_SETTLED = re.compile(
    r"(?:hasil penjualan investasi Anda sudah masuk|klaim hadiah.*?sudah ditutup)",
    re.IGNORECASE | re.DOTALL
)

# Indonesian subscription / service cancellation
_ID_SUBSCRIPTION_CANCELLED = re.compile(
    r"(?:langganan telah dibatalkan|konfirmasi pembatalan|layanan telah dihentikan)",
    re.IGNORECASE | re.DOTALL
)

# English salary reduction
_EN_SALARY_REDUCED = re.compile(
    r"(?:next salary|monthly pay) is reduced to (?:EUR|USD|INR|ZAR|IDR)?\s*([0-9,. ]+)",
    re.IGNORECASE
)

# English temporary pay
_EN_TEMPORARY_PAY = re.compile(
    r"temporary monthly pay is (?:EUR|USD|INR|ZAR|IDR)?\s*([0-9,. ]+)",
    re.IGNORECASE
)

# English salary date shift
_EN_SALARY_DATE_SHIFT = re.compile(
    r"salary is now expected on\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE
)

# English contract ended
_EN_CONTRACT_ENDED = re.compile(
    r"(?:seasonal contract has ended|contract (?:has )?ended|no (?:off-season )?income.*?confirmed|your employment has ended|employment has ended)",
    re.IGNORECASE
)

# English rent increase by percentage
_EN_RENT_INCREASE_PCT = re.compile(
    r"(?:renewed lease )?increases? monthly rent by\s*(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE
)

# English rent increase to specific amount
_EN_RENT_INCREASE_TO = re.compile(
    r"rent (?:is|has been|will be) (?:updated|increased|raised) to\s*(?:EUR|USD|INR|ZAR|IDR)?\s*([0-9,. ]+)",
    re.IGNORECASE
)

# English internal transfer (wash)
_EN_INTERNAL_TRANSFER = re.compile(
    r"(?:transfer between your (?:two|own) accounts|internal transfer|matching debit and credit)",
    re.IGNORECASE
)

# English prize/windfall pending
_EN_WINDFALL_PENDING = re.compile(
    r"(?:prize|lottery|windfall|winning).*?(?:pending|processing|still in)",
    re.IGNORECASE
)

# English payout pending (gig work)
_EN_PAYOUT_PENDING = re.compile(
    r"(?:payout|earnings).*?(?:pending|not (?:yet )?(?:withdrawable|available|confirmed))",
    re.IGNORECASE
)

# English bonus not confirmed
_EN_BONUS_PENDING = re.compile(
    r"(?:bonus|commission|incentive).*?(?:pending|not (?:yet )?(?:confirmed|approved|finalized))",
    re.IGNORECASE
)

# English salary increase with effective date
_EN_SALARY_INCREASE_APPLIES = re.compile(
    r"(?:monthly salary has increased to|salary has increased to|pay has increased to)\s*(?:EUR|USD|INR|ZAR|IDR)?\s*([0-9,. ]+).*?(?:change applies from|effective from)\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE | re.DOTALL
)

# English salary increase (general)
_EN_SALARY_INCREASE = re.compile(
    r"(?:salary|monthly pay|monthly salary) (?:is |has been )?(?:increased|raised|updated) to\s*(?:EUR|USD|INR|ZAR|IDR)?\s*([0-9,. ]+)",
    re.IGNORECASE
)

# English first salary confirmed with date
_EN_FIRST_SALARY = re.compile(
    r"(?:first salary (?:from the new employer )?(?:will be|is|of)|regular salary of)\s*(?:EUR|USD|INR|ZAR|IDR)?\s*([0-9,. ]+).*?(?:confirmed credit date is|scheduled for|confirmed for|resumes on)\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE | re.DOTALL
)

# English regular salary with arrears
_EN_SALARY_REGULAR_ARREARS = re.compile(
    r"regular salary for the next payroll is (?:EUR|USD|INR|ZAR|IDR)?\s*([0-9,. ]+).*?arrears adjustment",
    re.IGNORECASE | re.DOTALL
)

# English confirmed salary
_EN_SALARY_CONFIRMED = re.compile(
    r"confirmed (?:salary|base pay|base salary) (?:is|of)\s*(?:EUR|USD|INR|ZAR|IDR)?\s*([0-9,. ]+)",
    re.IGNORECASE
)

# English regular salary for next payroll (without arrears)
_EN_SALARY_NEXT_PAYROLL = re.compile(
    r"regular salary for the next payroll is (?:EUR|USD|INR|ZAR|IDR)?\s*([0-9,. ]+)",
    re.IGNORECASE
)

# English payment delay / failed debit
_EN_PAYMENT_DELAY = re.compile(
    r"(?:previous debit attempt failed|bill is still outstanding and another debit will be attempted)",
    re.IGNORECASE
)

# English refund pending
_EN_REFUND_PENDING = re.compile(
    r"(?:refund has been initiated but has not reached|foreign-currency refund is still processing|refund is in process|refund has not reached your account yet)",
    re.IGNORECASE
)

# English card charge dispute pending
_EN_DISPUTE_PENDING = re.compile(
    r"(?:extra card charge is still being investigated|dispute is open and no reversal has been posted)",
    re.IGNORECASE
)

# English unrealized investment
_EN_UNREALIZED_INVESTMENT = re.compile(
    r"(?:portfolio’s displayed market value|portfolio's displayed market value|displayed value of the investment).*?(?:no units have been sold|holding has not been sold|no cash proceeds|no cash transaction)",
    re.IGNORECASE
)

# English approved client invoice
_EN_INVOICE_APPROVED = re.compile(
    r"client approved an invoice payment of\s*(?:EUR|USD|INR|ZAR|IDR)?\s*([0-9,. ]+).*?settlement is expected on\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE | re.DOTALL
)

# English settled proceeds
_EN_PROCEEDS_SETTLED = re.compile(
    r"(?:prize proceeds have reached your account|proceeds from your investment sale have settled in the cash account)",
    re.IGNORECASE
)

# English subscription / service cancellation
_EN_SUBSCRIPTION_CANCELLED = re.compile(
    r"(?:subscription (?:has been|was) cancelled|cancellation confirmed|service (?:has been|was) terminated)",
    re.IGNORECASE
)

# English expense/subscription/service price increase
_EN_EXPENSE_INCREASE = re.compile(
    r"(?:subscription|plan|service|premium|fee|charge) (?:price |cost |amount )?(?:is |has been |will be )?(?:increased|raised|updated|going up) (?:to |by )?(?:EUR|USD|INR|ZAR|IDR)?\s*([0-9,. ]+)",
    re.IGNORECASE
)

# Indonesian general payroll update (no specific amount change)
_ID_PAYROLL_UPDATE = re.compile(
    r"(?:penggajian|payroll).*?(?:pembaruan|update|dikonfirmasi|confirmed)",
    re.IGNORECASE | re.DOTALL
)


def _parse_amount(s: str, currency: Optional[str] = None) -> Optional[float]:
    """
    Parse monetary amount string with robust international/localized format support:
    - Standard US/UK: 15,500,000.50, 15,500,000, 620.40, 1574.40
    - Indonesian / European: 15.500.000, 1.250.000,50, 1250000,50
    - Currency prefixes/symbols: IDR 15.500.000, $6,500, €1.250,50
    Fails safely (returns None) on malformed values without crashing the pipeline.
    """
    if not s or not isinstance(s, str):
        return None
    
    clean = s.strip()
    # Remove currency abbreviations and symbols
    clean = re.sub(r'(?i)\b(?:IDR|USD|EUR|GBP|INR|ZAR|AUD|CAD|SGD|JPY|CNY|RP)\b', '', clean)
    clean = re.sub(r'[\$€£₹¥]', '', clean)
    clean = clean.strip().rstrip('.')  # strip sentence-ending period
    clean = clean.replace(' ', '')
    
    if not clean:
        return None
    
    try:
        # Case A: Both '.' and ',' present
        if '.' in clean and ',' in clean:
            last_dot = clean.rfind('.')
            last_comma = clean.rfind(',')
            if last_comma > last_dot:
                # European / Indonesian decimal comma: 1.250.000,50 -> 1250000.50
                clean = clean.replace('.', '')
                clean = clean.replace(',', '.')
            else:
                # US / UK decimal dot: 1,250,000.50 -> 1250000.50
                clean = clean.replace(',', '')
        
        # Case B: Only ',' present
        elif ',' in clean:
            if clean.count(',') > 1:
                clean = clean.replace(',', '')
            else:
                parts = clean.split(',')
                if len(parts[-1]) != 3 or (currency and currency.upper() in ('IDR', 'EUR')):
                    clean = clean.replace(',', '.')
                else:
                    clean = clean.replace(',', '')
        
        # Case C: Only '.' present
        elif '.' in clean:
            if clean.count('.') > 1:
                clean = clean.replace('.', '')
            else:
                parts = clean.split('.')
                if len(parts[-1]) in (1, 2):
                    pass  # Keep standard decimal point (e.g. 620.40, 1574.40)
                elif len(parts[-1]) == 3 and (currency and currency.upper() == 'IDR'):
                    clean = clean.replace('.', '')
                else:
                    pass  # Standard float
        
        return float(clean)
    except (ValueError, TypeError):
        return None


def _parse_date_str(s: str) -> date:
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def parse_messages(messages: List[Message]) -> MessageParseResult:
    """
    Parse all messages and extract financial facts.
    Every message gets exactly one outcome: recognized fact(s) or an 'unresolved' entry.
    Adversarial prompt injection attempts are rejected immediately.
    """
    result = MessageParseResult()
    
    for msg in messages:
        # Prompt Injection Defense: reject adversarial payloads
        if is_prompt_injection(msg.message_text):
            result.unresolved.append((
                msg.message_id,
                "prompt injection attempt rejected; treated strictly as unexecutable data"
            ))
            continue
        
        facts = _parse_single_message(msg)
        if facts:
            result.facts.extend(facts)
        else:
            result.unresolved.append((
                msg.message_id,
                "no actionable financial fact extracted"
            ))
    
    return result


def _parse_single_message(msg: Message) -> List[FinancialFact]:
    """Try all rules against a single message. Return list of extracted facts."""
    text = msg.message_text
    facts = []
    
    # ── Indonesian patterns ───────────────────────────────────────────
    
    # Salary increase with effective date (Indonesian)
    m = _ID_SALARY_INCREASE.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="salary_increase",
            value=_parse_amount(m.group(1)),
            effective_date=_parse_date_str(m.group(2)),
            confidence="high",
            rule_used="ID_SALARY_INCREASE",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # First salary confirmed (Indonesian)
    m = _ID_FIRST_SALARY.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="first_salary_confirmed",
            value=_parse_amount(m.group(1)),
            effective_date=_parse_date_str(m.group(2)),
            confidence="high",
            rule_used="ID_FIRST_SALARY",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # Temporary salary (Indonesian)
    m = _ID_TEMPORARY_SALARY.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="salary_decrease",
            value=_parse_amount(m.group(1)),
            effective_date=None,
            confidence="high",
            rule_used="ID_TEMPORARY_SALARY",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # Routine salary for next payroll (Indonesian)
    m = _ID_SALARY_ROUTINE.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="salary_confirmed",
            value=_parse_amount(m.group(1)),
            effective_date=None,
            confidence="high",
            rule_used="ID_SALARY_ROUTINE",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # Salary date shift (Indonesian)
    m = _ID_SALARY_DATE_SHIFT.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="salary_date_shift",
            value=None,
            effective_date=_parse_date_str(m.group(1)),
            confidence="high",
            rule_used="ID_SALARY_DATE_SHIFT",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # Contract ended (Indonesian)
    m = _ID_CONTRACT_ENDED.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="contract_ended",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="ID_CONTRACT_ENDED",
        ))
        return facts
    
    # Rent increase (Indonesian)
    m = _ID_RENT_INCREASE.search(text)
    if m:
        is_hypo = bool(_HYPOTHETICAL_SPECULATIVE.search(text))
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="rent_increase",
            value=None,
            effective_date=None,
            confidence="low" if is_hypo else "high",
            rule_used="ID_RENT_INCREASE",
            percentage_change=float(m.group(1)),
            target_event_id=msg.related_event_id,
            is_confirmed=not is_hypo,
        ))
        return facts
    
    # Bonus pending (Indonesian)
    m = _ID_BONUS_PENDING.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="bonus_unconfirmed",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="ID_BONUS_PENDING",
            is_confirmed=False,
        ))
        return facts
    
    # Base salary confirmed, commission pending (Indonesian)
    m = _ID_SALARY_CONFIRMED_COMMISSION_PENDING.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="salary_confirmed",
            value=_parse_amount(m.group(1)),
            effective_date=None,
            confidence="high",
            rule_used="ID_SALARY_CONFIRMED_COMMISSION_PENDING",
            target_event_id=msg.related_event_id,
        ))
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="commission_unconfirmed",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="ID_SALARY_CONFIRMED_COMMISSION_PENDING_COMMISSION",
            is_confirmed=False,
        ))
        return facts
    
    # Approved invoice (Indonesian)
    m = _ID_INVOICE_APPROVED.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="invoice_approved",
            value=_parse_amount(m.group(1)),
            effective_date=_parse_date_str(m.group(2)),
            confidence="high",
            rule_used="ID_INVOICE_APPROVED",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # Payout pending (Indonesian)
    m = _ID_PAYOUT_PENDING.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="payout_pending",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="ID_PAYOUT_PENDING",
            is_confirmed=False,
        ))
        return facts
    
    # Internal transfer (Indonesian)
    m = _ID_INTERNAL_TRANSFER.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="internal_transfer",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="ID_INTERNAL_TRANSFER",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # Unrealized investment (Indonesian)
    m = _ID_UNREALIZED_INVESTMENT.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="unrealized_investment",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="ID_UNREALIZED_INVESTMENT",
            is_confirmed=False,
        ))
        return facts
    
    # Refund pending (Indonesian)
    m = _ID_REFUND_PENDING.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="refund_pending",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="ID_REFUND_PENDING",
            is_confirmed=False,
        ))
        return facts
    
    # Card dispute pending (Indonesian)
    m = _ID_DISPUTE_PENDING.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="dispute_pending",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="ID_DISPUTE_PENDING",
            is_confirmed=False,
        ))
        return facts
    
    # Settled proceeds (Indonesian)
    m = _ID_PROCEEDS_SETTLED.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="proceeds_settled",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="ID_PROCEEDS_SETTLED",
            is_confirmed=True,
        ))
        return facts
    
    # Subscription cancelled (Indonesian)
    m = _ID_SUBSCRIPTION_CANCELLED.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="subscription_cancelled",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="ID_SUBSCRIPTION_CANCELLED",
        ))
        return facts
    
    # ── English patterns ──────────────────────────────────────────────
    
    # Contract ended (English)
    m = _EN_CONTRACT_ENDED.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="contract_ended",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="EN_CONTRACT_ENDED",
        ))
        return facts
    
    # Salary increase with effective date (English)
    m = _EN_SALARY_INCREASE_APPLIES.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="salary_increase",
            value=_parse_amount(m.group(1)),
            effective_date=_parse_date_str(m.group(2)),
            confidence="high",
            rule_used="EN_SALARY_INCREASE_APPLIES",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # First salary confirmed (English)
    m = _EN_FIRST_SALARY.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="first_salary_confirmed",
            value=_parse_amount(m.group(1)),
            effective_date=_parse_date_str(m.group(2)),
            confidence="high",
            rule_used="EN_FIRST_SALARY",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # Temporary/reduced pay (English)
    m = _EN_TEMPORARY_PAY.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="salary_decrease",
            value=_parse_amount(m.group(1)),
            effective_date=None,
            confidence="high",
            rule_used="EN_TEMPORARY_PAY",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    m = _EN_SALARY_REDUCED.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="salary_decrease",
            value=_parse_amount(m.group(1)),
            effective_date=None,
            confidence="high",
            rule_used="EN_SALARY_REDUCED",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # Regular salary with arrears (English)
    m = _EN_SALARY_REGULAR_ARREARS.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="salary_confirmed",
            value=_parse_amount(m.group(1)),
            effective_date=None,
            confidence="high",
            rule_used="EN_SALARY_REGULAR_ARREARS",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # Salary date shift (English)
    m = _EN_SALARY_DATE_SHIFT.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="salary_date_shift",
            value=None,
            effective_date=_parse_date_str(m.group(1)),
            confidence="high",
            rule_used="EN_SALARY_DATE_SHIFT",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # Internal transfer (English)
    m = _EN_INTERNAL_TRANSFER.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="internal_transfer",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="EN_INTERNAL_TRANSFER",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # Rent increase by percentage (English)
    m = _EN_RENT_INCREASE_PCT.search(text)
    if m:
        is_hypo = bool(_HYPOTHETICAL_SPECULATIVE.search(text))
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="rent_increase",
            value=None,
            effective_date=None,
            confidence="low" if is_hypo else "high",
            rule_used="EN_RENT_INCREASE_PCT",
            percentage_change=float(m.group(1)),
            target_event_id=msg.related_event_id,
            is_confirmed=not is_hypo,
        ))
        return facts
    
    # Rent increase to amount (English)
    m = _EN_RENT_INCREASE_TO.search(text)
    if m:
        is_hypo = bool(_HYPOTHETICAL_SPECULATIVE.search(text))
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="rent_increase",
            value=_parse_amount(m.group(1)),
            effective_date=None,
            confidence="low" if is_hypo else "high",
            rule_used="EN_RENT_INCREASE_TO",
            target_event_id=msg.related_event_id,
            is_confirmed=not is_hypo,
        ))
        return facts
    
    # Payment delay / failed debit (English)
    m = _EN_PAYMENT_DELAY.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="payment_delay",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="EN_PAYMENT_DELAY",
            target_event_id=msg.related_event_id,
            is_confirmed=False,
        ))
        return facts
    
    # Refund pending (English)
    m = _EN_REFUND_PENDING.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="refund_pending",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="EN_REFUND_PENDING",
            target_event_id=msg.related_event_id,
            is_confirmed=False,
        ))
        return facts
    
    # Card dispute pending (English)
    m = _EN_DISPUTE_PENDING.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="dispute_pending",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="EN_DISPUTE_PENDING",
            target_event_id=msg.related_event_id,
            is_confirmed=False,
        ))
        return facts
    
    # Unrealized investment (English)
    m = _EN_UNREALIZED_INVESTMENT.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="unrealized_investment",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="EN_UNREALIZED_INVESTMENT",
            is_confirmed=False,
        ))
        return facts
    
    # Approved invoice (English)
    m = _EN_INVOICE_APPROVED.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="invoice_approved",
            value=_parse_amount(m.group(1)),
            effective_date=_parse_date_str(m.group(2)),
            confidence="high",
            rule_used="EN_INVOICE_APPROVED",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # Settled proceeds (English)
    m = _EN_PROCEEDS_SETTLED.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="proceeds_settled",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="EN_PROCEEDS_SETTLED",
            is_confirmed=True,
        ))
        return facts
    
    # Subscription cancelled (English)
    m = _EN_SUBSCRIPTION_CANCELLED.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="subscription_cancelled",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="EN_SUBSCRIPTION_CANCELLED",
        ))
        return facts
    
    # Windfall pending (English)
    m = _EN_WINDFALL_PENDING.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="windfall_unconfirmed",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="EN_WINDFALL_PENDING",
            is_confirmed=False,
        ))
        return facts
    
    # Payout pending (English)
    m = _EN_PAYOUT_PENDING.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="payout_pending",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="EN_PAYOUT_PENDING",
            is_confirmed=False,
        ))
        return facts
    
    # Bonus pending (English)
    m = _EN_BONUS_PENDING.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="bonus_unconfirmed",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="EN_BONUS_PENDING",
            is_confirmed=False,
        ))
        return facts
    
    # Salary increase (English general)
    m = _EN_SALARY_INCREASE.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="salary_increase",
            value=_parse_amount(m.group(1)),
            effective_date=None,
            confidence="high",
            rule_used="EN_SALARY_INCREASE",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # Confirmed salary (English)
    m = _EN_SALARY_CONFIRMED.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="salary_confirmed",
            value=_parse_amount(m.group(1)),
            effective_date=None,
            confidence="high",
            rule_used="EN_SALARY_CONFIRMED",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # Regular salary for next payroll (English)
    m = _EN_SALARY_NEXT_PAYROLL.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="salary_confirmed",
            value=_parse_amount(m.group(1)),
            effective_date=None,
            confidence="high",
            rule_used="EN_SALARY_NEXT_PAYROLL",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # Expense increase (English)
    m = _EN_EXPENSE_INCREASE.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="expense_increase",
            value=_parse_amount(m.group(1)),
            effective_date=None,
            confidence="medium",
            rule_used="EN_EXPENSE_INCREASE",
            target_event_id=msg.related_event_id,
        ))
        return facts
    
    # Indonesian general payroll update (informational)
    m = _ID_PAYROLL_UPDATE.search(text)
    if m:
        facts.append(FinancialFact(
            source_message_id=msg.message_id,
            fact_type="no_actionable_fact",
            value=None,
            effective_date=None,
            confidence="high",
            rule_used="ID_PAYROLL_UPDATE_INFORMATIONAL",
            is_confirmed=True,
        ))
        return facts
    
    # No pattern matched
    return []


def get_salary_amendments(
    facts: List[FinancialFact],
    user_id: str,
) -> Dict[str, object]:
    """
    Extract salary-related amendments from parsed facts.
    
    Returns a dict with keys:
      'salary_amount': Optional[float] — amended salary amount
      'salary_date': Optional[date] — shifted salary date
      'contract_ended': bool — whether employment has ended
    """
    amendments = {
        "salary_amount": None,
        "salary_date": None,
        "contract_ended": False,
    }
    
    for fact in facts:
        if fact.fact_type == "salary_increase" and fact.value is not None:
            amendments["salary_amount"] = fact.value
            if fact.effective_date is not None:
                amendments["salary_date"] = fact.effective_date
        elif fact.fact_type == "first_salary_confirmed" and fact.value is not None:
            amendments["salary_amount"] = fact.value
            if fact.effective_date is not None:
                amendments["salary_date"] = fact.effective_date
        elif fact.fact_type == "salary_decrease" and fact.value is not None:
            amendments["salary_amount"] = fact.value
        elif fact.fact_type == "salary_confirmed" and fact.value is not None:
            amendments["salary_amount"] = fact.value
        elif fact.fact_type == "salary_date_shift" and fact.effective_date is not None:
            amendments["salary_date"] = fact.effective_date
        elif fact.fact_type == "contract_ended":
            amendments["contract_ended"] = True
    
    return amendments


def get_expense_amendments(
    facts: List[FinancialFact],
    user_id: str,
) -> Dict[str, Dict[str, object]]:
    """
    Extract confirmed expense-related amendments (such as confirmed rent increases) from parsed facts.
    
    Returns a dict mapping category (e.g. 'rent') to amendment parameters:
      {
        'rent': {
          'percentage_increase': Optional[float],
          'new_amount': Optional[float],
          'effective_date': Optional[date],
        }
      }
    
    Adversarial safety rules:
    - Never applies unconfirmed, speculative, or low-confidence facts.
    - If multiple conflicting rent amendments exist, picks the financially safer
      interpretation (highest expense increase) per challenge rules §6.3.
    """
    amendments: Dict[str, Dict[str, object]] = {}
    
    rent_facts = [
        f for f in facts
        if f.fact_type == "rent_increase" and f.is_confirmed and f.confidence == "high"
    ]
    
    if rent_facts:
        max_pct = None
        max_amt = None
        eff_date = None
        
        for f in rent_facts:
            if f.percentage_change is not None:
                if max_pct is None or f.percentage_change > max_pct:
                    max_pct = f.percentage_change
            if f.value is not None:
                if max_amt is None or f.value > max_amt:
                    max_amt = f.value
            if f.effective_date is not None:
                eff_date = f.effective_date
                
        amendments["rent"] = {
            "percentage_increase": max_pct,
            "new_amount": max_amt,
            "effective_date": eff_date,
        }
        
    return amendments
