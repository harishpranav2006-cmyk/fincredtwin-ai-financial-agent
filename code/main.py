"""
FinCredTwin Main Entry Point
Sequential pipeline: Load → Validate → Build Twin → Simulate → Rank → Explain → Write

Usage:
    python code/main.py                  # Full 250-request run
    python code/main.py --sample         # Run on 25 sample requests only
"""
import sys
import os
import time
import traceback
from datetime import datetime

# Ensure stdout and stderr use UTF-8 on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Ensure code/ is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import REQUESTS_CSV, SAMPLE_REQUESTS_CSV, OUTPUT_CSV, FORECAST_DAYS
from data_loader import load_all_data, DataStore, Request
from image_extractor import validate_image_cache, get_all_provenance
from message_interpreter import (
    parse_messages, get_salary_amendments, get_expense_amendments, MessageParseResult
)
from event_lifecycle import get_active_events
from cycle_detector import detect_cycles, project_future_events
from financial_state import build_twin, FinancialDigitalTwin
from forecast_engine import compute_safe_amount, compute_earliest_date
from scenario_generator import generate_candidates, CandidatePlan
from ranker import rank_plans
from safety_firewall import validate_output_row
from explainer import generate_explanation
from output_writer import write_output


def process_request(
    request: Request,
    store: DataStore,
    message_results: dict,
) -> dict:
    """
    Process a single request through the full pipeline.
    Returns an output row dict.
    """
    # 1. Get user events
    user_events = store.events_by_user.get(request.user_id, [])
    
    # 2. Resolve event lifecycle
    historical, active_debits, active_credits = get_active_events(
        user_events, store, request.request_date
    )
    
    # 3. Get message amendments for this user
    user_msg_result = message_results.get(request.user_id)
    salary_amendments = {}
    expense_amendments = {}
    if user_msg_result:
        salary_amendments = get_salary_amendments(
            user_msg_result.facts, request.user_id
        )
        expense_amendments = get_expense_amendments(
            user_msg_result.facts, request.user_id
        )
    
    # 4. Detect cycles and project future events
    patterns = detect_cycles(historical, request.user_id, active_credits)
    # Collect all scheduled events (from active debits + credits)
    all_scheduled = [e for e in active_debits + active_credits if e.status == "scheduled"]
    projected = project_future_events(
        patterns, request.request_date, FORECAST_DAYS, salary_amendments,
        scheduled_events=all_scheduled,
        expense_amendments=expense_amendments,
    )
    
    # 5. Build Financial Digital Twin
    twin = build_twin(
        request, store, historical, active_debits, active_credits,
        projected, patterns,
    )
    
    # 6. Compute safe amount (simulation-verified)
    twin.amount_safe_to_pay = compute_safe_amount(twin)
    
    # 7. Compute earliest date (simulation-verified)
    twin.earliest_date_for_full_payment = compute_earliest_date(twin)
    
    # 8. Generate candidate plans
    candidates = generate_candidates(twin)
    
    # 9. Rank plans
    winner = rank_plans(candidates, request.desired_completion_date)
    
    # 10. If winner exists, set its computed fields
    if winner:
        winner.amount_safe_to_pay = twin.amount_safe_to_pay
        winner.earliest_date_for_full_payment = twin.earliest_date_for_full_payment
    
    # 11. Validate through safety firewall
    output_row, is_valid, validation_msg = validate_output_row(winner, twin)
    
    # 12. Generate explanation
    if winner and is_valid:
        explanation = generate_explanation(winner, twin)
    else:
        # Fallback explanation
        curr = twin.home_currency
        min_bal = f"{twin.minimum_balance_to_keep:,.0f}" if twin.minimum_balance_to_keep == int(twin.minimum_balance_to_keep) else f"{twin.minimum_balance_to_keep:,.2f}"
        explanation = f"Do not proceed with this request. The {curr} {min_bal} minimum balance cannot be safely maintained."
    
    output_row["decision_explanation"] = explanation
    
    return output_row


def main():
    start_time = time.time()
    
    # Parse command line
    sample_mode = "--sample" in sys.argv
    
    print("=" * 60)
    print("FinCredTwin — Buy or Wait? Financial Decision Engine")
    print("=" * 60)
    
    # ── Step 1: Validate image cache ──
    print("\n[1/7] Validating image cache...")
    try:
        validation = validate_image_cache()
        print(f"  ✓ All {len(validation)} cached images validated (files present)")
    except RuntimeError as e:
        print(f"  ✗ FATAL: {e}")
        sys.exit(1)
    
    # ── Step 2: Load all data ──
    print("\n[2/7] Loading dataset...")
    request_path = SAMPLE_REQUESTS_CSV if sample_mode else REQUESTS_CSV
    store = load_all_data(request_path)
    
    num_requests = len(store.requests)
    print(f"  ✓ Loaded {num_requests} requests")
    print(f"  ✓ {len(store.profiles)} profiles, {len(store.events)} events")
    print(f"  ✓ {len(store.payment_options)} payment options")
    print(f"  ✓ {len(store.messages)} messages, {len(store.exchange_rates)} FX rates")
    
    # Count events with image-filled amounts
    image_filled = sum(1 for e in store.events if e.amount_source.startswith("image_cache:"))
    null_amounts = sum(1 for e in store.events if e.amount is None)
    print(f"  ✓ {image_filled} event amounts filled from image cache")
    if null_amounts > 0:
        print(f"  ⚠ {null_amounts} events still have null amounts")
    
    # ── Step 3: Parse messages ──
    print("\n[3/7] Parsing messages...")
    message_results = {}
    total_facts = 0
    total_unresolved = 0
    
    for user_id, msgs in store.messages_by_user.items():
        result = parse_messages(msgs)
        message_results[user_id] = result
        total_facts += len(result.facts)
        total_unresolved += len(result.unresolved)
    
    print(f"  ✓ Extracted {total_facts} financial facts from messages")
    print(f"  ✓ {total_unresolved} messages had no actionable fact")
    
    # ── Step 4: Process requests ──
    print(f"\n[4/7] Processing {num_requests} requests...")
    output_rows = []
    errors = []
    unsafe_rejections = 0
    
    for i, request in enumerate(store.requests):
        try:
            row = process_request(request, store, message_results)
            output_rows.append(row)
            
            if row["recommended_payment_method"] == "not_recommended":
                unsafe_rejections += 1
            
            # Progress indicator
            if (i + 1) % 25 == 0 or (i + 1) == num_requests:
                print(f"  [{i+1}/{num_requests}] processed")
                
        except Exception as e:
            # NEVER halt on exception — produce safe fallback
            tb = traceback.format_exc()
            errors.append((request.request_id, str(e), tb))
            
            # Safe fallback row
            profile = store.profiles.get(request.user_id)
            output_rows.append({
                "request_id": request.request_id,
                "amount_safe_to_pay": "0",
                "affordability_status": "not_affordable",
                "recommended_payment_method": "not_recommended",
                "payment_plan": "none",
                "earliest_date_for_full_payment": "",
                "spending_changes_needed": "none",
                "decision_explanation": "Unable to process this request safely. Recommending caution.",
            })
            unsafe_rejections += 1
            print(f"  ⚠ Error on {request.request_id}: {e}")
    
    # ── Step 5: Assert row count ──
    print(f"\n[5/7] Validating output...")
    assert len(output_rows) == num_requests, (
        f"Output row count mismatch: {len(output_rows)} != {num_requests}"
    )
    print(f"  ✓ Row count: {len(output_rows)} == {num_requests} ✓")
    
    # ── Step 6: Write output ──
    print("\n[6/7] Writing output.csv...")
    write_output(output_rows)
    print(f"  ✓ Written to {OUTPUT_CSV}")
    
    # ── Step 7: Report ──
    elapsed = time.time() - start_time
    
    print("\n" + "=" * 60)
    print("EXECUTION REPORT")
    print("=" * 60)
    print(f"  Output row count:        {len(output_rows)}")
    print(f"  Processing errors:       {len(errors)}")
    print(f"  Unsafe-plan rejections:  {unsafe_rejections}")
    print(f"  Image verification:      {len(validate_image_cache())}/16 files present")
    print(f"  Message facts extracted: {total_facts}")
    print(f"  Unresolved messages:     {total_unresolved}")
    print(f"  Runtime:                 {elapsed:.1f}s")
    print(f"  LLM API calls:           0 (deterministic mode)")
    
    # Affordability distribution
    status_counts = {}
    method_counts = {}
    for row in output_rows:
        s = row["affordability_status"]
        m = row["recommended_payment_method"]
        status_counts[s] = status_counts.get(s, 0) + 1
        method_counts[m] = method_counts.get(m, 0) + 1
    
    print(f"\n  Affordability distribution:")
    for s, c in sorted(status_counts.items()):
        print(f"    {s}: {c}")
    print(f"\n  Method distribution:")
    for m, c in sorted(method_counts.items()):
        print(f"    {m}: {c}")
    
    if errors:
        print(f"\n  ERRORS ({len(errors)}):")
        for req_id, err, _ in errors[:10]:
            print(f"    {req_id}: {err}")
    
    print(f"\n  Next recommended phase: P1 message refinement + sample regression testing")
    print("=" * 60)
    
    return len(errors) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
