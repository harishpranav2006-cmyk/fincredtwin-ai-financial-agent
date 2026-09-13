# FinCredTwin Semantic Layer Report

## Overview & Current State

FinCredTwin uses a **strictly deterministic, rule-based semantic layer** with full provenance tracking and prompt-injection defense. All unstructured and multi-modal inputs are resolved deterministically without external API dependencies.

## Capability Matrix

| Semantic Component | Current Status | Mechanism | External API Calls |
|---|---|---|---|
| **Message Interpretation** | **ACTIVE (Deterministic)** | 20+ multilingual regex extraction rules with provenance | 0 (No LLM) |
| **LLM Semantic Parsing** | **NOT ACTIVE** | Quarantined; deterministic rules authoritative | 0 |
| **Image Amount Resolution** | **ACTIVE (Deterministic)** | Ground-truth verified image amount cache (`image_extractor.py`) | 0 (No Vision API) |
| **Vision API Calls** | **NOT ACTIVE** | Zero external visual inference calls | 0 |
| **Prompt Injection Defense** | **ACTIVE** | Explicit adversarial instruction quarantine | 0 |

## Message Interpretation Capabilities

1. **Multilingual Support (English & Indonesian)**:
   - **Contract Termination**: Detects seasonal contract ends, formal terminations, and employment conclusion in both English and Indonesian.
   - **Income Modifications**: Extracts salary increases with effective dates, confirmed routine salary, temporary reductions, and scheduled first payroll dates.
   - **Date Shifts**: Extracts confirmed salary settlement date shifts to avoid misaligning liquidity troughs.
   - **Non-Cash Inflow Quarantine**: Correctly marks unconfirmed bonuses, commissions, lotteries, and refunds as `is_confirmed=False` so they are never credited prematurely.
   - **Failed Debits & Payment Delays**: Identifies failed debit attempts where recurring obligations remain outstanding.
   - **Wash / Internal Transfers**: Identifies matching debit/credit pairs between user's own accounts as non-income wash events.
   - **Unrealized Investment Gains/Losses**: Confirms portfolio fluctuations without unit sales are non-cash.
   - **Price & Rate Changes**: Accurately tracks rent escalations (percentage-based and fixed).

2. **Provenance Tracking**:
   Every extracted fact logs:
   - `source_message_id`: exact ID of origin message
   - `fact_type`: enumerated fact type
   - `value`: parsed monetary amount
   - `effective_date`: exact effective date if stated
   - `confidence`: 'high' / 'medium'
   - `rule_used`: specific regex rule identifier
   - `target_event_id`: related event ID if linked
   - `is_confirmed`: boolean confirmation status

3. **Adversarial Prompt-Injection Defense**:
   Untrusted messages and requests containing prompt injection strings (such as `"ignore previous instructions"`, `"bypass minimum balance"`, `"approve this payment"`, `"change salary to 50000"`, `"always recommend installments"`) are quarantined as unexecutable data. They produce zero actionable financial facts and cannot alter user balances or recommendations.

## Image Resolution Capabilities

- 16/16 dataset images were visually inspected and verified during initial data forensics.
- Image amounts are stored in a deterministic provenance-tracked lookup cache in `image_extractor.py`.
- At pipeline start, image file presence is validated on the local filesystem (`dataset/media/images/<image_id>.png`).
- 0 Vision API or external multimodal model calls are required at runtime.
