"""
FinCredTwin Configuration
Paths, constants, and settings for the financial decision engine.
"""
import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
# Resolve relative to this file's parent (code/) then up to repo root.
CODE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CODE_DIR.parent
DATASET_DIR = REPO_ROOT / "dataset"

# Input files
REQUESTS_CSV = DATASET_DIR / "requests.csv"
SAMPLE_REQUESTS_CSV = DATASET_DIR / "sample_requests.csv"
FINANCIAL_PROFILES_CSV = DATASET_DIR / "financial_profiles.csv"
FINANCIAL_EVENTS_CSV = DATASET_DIR / "financial_events.csv"
EXCHANGE_RATES_CSV = DATASET_DIR / "exchange_rates.csv"
PAYMENT_OPTIONS_CSV = DATASET_DIR / "request_payment_options.csv"
MESSAGES_CSV = DATASET_DIR / "messages.csv"
IMAGES_CSV = DATASET_DIR / "images.csv"
IMAGES_DIR = DATASET_DIR / "media" / "images"

# Output files
OUTPUT_CSV = DATASET_DIR / "output.csv"
ROOT_OUTPUT_CSV = REPO_ROOT / "output.csv"


# Evaluation
EVALUATION_DIR = CODE_DIR / "evaluation"
USAGE_REPORT_MD = EVALUATION_DIR / "usage_report.md"

# ── Constants ──────────────────────────────────────────────────────────
FORECAST_DAYS = 90  # 90-day forward horizon (days 0..90 = 91 data points)

# ── Output columns (exact order per problem_statement.md) ─────────────
OUTPUT_COLUMNS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]

# ── Allowed enum values ───────────────────────────────────────────────
AFFORDABILITY_STATUSES = {
    "affordable_now",
    "affordable_with_plan",
    "affordable_later",
    "not_affordable",
}

PAYMENT_METHODS = {
    "full_payment",
    "partial_payment",
    "installments",
    "wait",
    "not_recommended",
}

# ── Event statuses per problem_statement.md ───────────────────────────
EVENT_STATUSES = {
    "settled",
    "pending",
    "scheduled",
    "failed",
    "cancelled",
    "unrealized",
}
