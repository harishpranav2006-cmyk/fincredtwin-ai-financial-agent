"""
FinCredTwin Core Validation Script
Validates output.csv against all mandatory gates before generating the report.
"""
import csv
import sys
import time
from datetime import date, datetime
from collections import Counter

sys.path.insert(0, 'code')
from config import OUTPUT_COLUMNS, AFFORDABILITY_STATUSES, PAYMENT_METHODS

def load_csv(path):
    with open(path, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def main():
    start = time.time()
    
    sample_mode = "--sample" in sys.argv
    output_rows = load_csv('dataset/output.csv')
    sample_rows = load_csv('dataset/sample_requests.csv')
    request_rows = sample_rows if sample_mode else load_csv('dataset/requests.csv')
    option_rows = load_csv('dataset/request_payment_options.csv')
    profile_rows = load_csv('dataset/financial_profiles.csv')
    
    profiles = {r['user_id']: r for r in profile_rows}
    requests = {r['request_id']: r for r in request_rows}
    samples = {r['request_id']: r for r in sample_rows}
    options_by_req = {}
    for o in option_rows:
        options_by_req.setdefault(o['request_id'], []).append(o)
    
    output_by_id = {r['request_id']: r for r in output_rows}
    
    print("=" * 70)
    print(f"FINCREDTWIN CORE VALIDATION ({'SAMPLE MODE' if sample_mode else 'PRODUCTION 250-ROW MODE'})")
    print("=" * 70)
    
    failures = []
    warnings = []
    
    # ── Gate 1: Row count ──
    print(f"\n[1] Row Count")
    print(f"  Expected: {len(request_rows)}")
    print(f"  Output:   {len(output_rows)}")
    assert len(output_rows) == len(request_rows), f"ROW COUNT MISMATCH: {len(output_rows)} vs {len(request_rows)}"
    print(f"  PASS: {len(output_rows)} == {len(request_rows)}")
    
    # ── Gate 2: No missing request IDs ──
    print(f"\n[2] Missing Request IDs")
    req_ids = {r['request_id'] for r in request_rows}
    out_ids = {r['request_id'] for r in output_rows}
    missing = req_ids - out_ids
    extra = out_ids - req_ids
    if missing:
        failures.append(f"Missing request IDs: {missing}")
        print(f"  FAIL: Missing {len(missing)}: {missing}")
    else:
        print(f"  PASS: All {len(req_ids)} request IDs present")
    if extra:
        failures.append(f"Extra request IDs: {extra}")
        print(f"  FAIL: Extra {len(extra)}: {extra}")
    
    # ── Gate 3: No duplicate request IDs ──
    print(f"\n[3] Duplicate Request IDs")
    id_counts = Counter(r['request_id'] for r in output_rows)
    dupes = {k: v for k, v in id_counts.items() if v > 1}
    if dupes:
        failures.append(f"Duplicate IDs: {dupes}")
        print(f"  FAIL: {len(dupes)} duplicates")
    else:
        print(f"  PASS: No duplicates")
    
    # ── Gate 4: Valid Schema ──
    print(f"\n[4] Schema Validation")
    if output_rows:
        actual_cols = list(output_rows[0].keys())
        if actual_cols == OUTPUT_COLUMNS:
            print(f"  PASS: Columns match official order")
        else:
            failures.append(f"Column mismatch: {actual_cols} vs {OUTPUT_COLUMNS}")
            print(f"  FAIL: Column mismatch")
    
    # ── Gate 5: Per-row validation ──
    print(f"\n[5] Per-Row Validation")
    row_failures = 0
    
    for row in output_rows:
        rid = row['request_id']
        req = requests[rid]
        profile = profiles[req['user_id']]
        
        errs = validate_row(row, req, profile, options_by_req.get(rid, []))
        if errs:
            row_failures += 1
            if row_failures <= 10:
                for e in errs:
                    warnings.append(f"{rid}: {e}")
    
    print(f"  Rows with validation warnings: {row_failures}/{len(output_rows)}")
    
    # ── Gate 6: Affordability/Method distribution ──
    print(f"\n[6] Distribution")
    status_dist = Counter(r['affordability_status'] for r in output_rows)
    method_dist = Counter(r['recommended_payment_method'] for r in output_rows)
    
    print(f"  Affordability:")
    for s in sorted(status_dist):
        print(f"    {s}: {status_dist[s]}")
    print(f"  Methods:")
    for m in sorted(method_dist):
        print(f"    {m}: {method_dist[m]}")
    
    # ── Gate 7: Sample comparison ──
    field_match = {}
    sample_ids_present = any(rid in output_by_id for rid in samples)
    if sample_ids_present:
        print(f"\n[7] Sample Regression (reference only, not accuracy claim)")
        fields = [
            'affordability_status',
            'recommended_payment_method',
            'spending_changes_needed',
            'earliest_date_for_full_payment',
            'payment_plan',
            'amount_safe_to_pay',
        ]
        field_match = {f: 0 for f in fields}
        
        for rid, sample in samples.items():
            out = output_by_id.get(rid, {})
            for f in fields:
                exp = sample.get(f, '').strip()
                act = out.get(f, '').strip()
                matched = (exp == act)
                if f == 'amount_safe_to_pay':
                    try:
                        matched = abs(float(exp) - float(act)) < 1.0
                    except Exception:
                        pass
                if matched:
                    field_match[f] += 1
        
        for f in fields:
            pct = field_match[f] / len(samples) * 100
            print(f"  {f:30s}: {field_match[f]}/{len(samples)} ({pct:.1f}%)")
        
        tot_m = sum(field_match.values())
        tot_f = len(fields) * len(samples)
        print(f"  {'OVERALL FIELD ACCURACY':30s}: {tot_m}/{tot_f} ({tot_m/tot_f*100:.1f}%)")
    else:
        print(f"\n[7] Sample Regression: Skipped (production run evaluated {len(output_rows)} unseen evaluation requests)")

    
    # ── Summary ──
    elapsed = time.time() - start
    print(f"\n{'=' * 70}")
    print(f"VALIDATION SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Critical failures: {len(failures)}")
    print(f"  Row warnings:      {row_failures}")
    print(f"  Validation time:   {elapsed:.2f}s")
    
    if failures:
        print(f"\n  CRITICAL FAILURES:")
        for f in failures:
            print(f"    - {f}")
    
    if warnings:
        print(f"\n  WARNINGS (first 10):")
        for w in warnings[:10]:
            print(f"    - {w}")
    
    return len(failures), row_failures, status_dist, method_dist, field_match


def validate_row(row, req, profile, options):
    """Validate a single output row. Returns list of error strings."""
    errors = []
    
    status = row.get('affordability_status', '')
    method = row.get('recommended_payment_method', '')
    plan_str = row.get('payment_plan', '')
    safe_str = row.get('amount_safe_to_pay', '')
    earliest = row.get('earliest_date_for_full_payment', '')
    changes = row.get('spending_changes_needed', '')
    requested = float(req['requested_amount'])
    
    # Enum validation
    if status not in AFFORDABILITY_STATUSES:
        errors.append(f"invalid affordability_status: {status}")
    if method not in PAYMENT_METHODS:
        errors.append(f"invalid payment_method: {method}")
    
    # Amount bounds
    try:
        safe = float(safe_str)
        if safe < -0.01:
            errors.append(f"amount_safe_to_pay negative: {safe}")
        if safe > requested + 0.01:
            errors.append(f"amount_safe_to_pay {safe} > requested {requested}")
    except ValueError:
        errors.append(f"amount_safe_to_pay not a number: {safe_str}")
    
    # affordable_now consistency
    if status == 'affordable_now':
        if earliest and earliest != req['request_date']:
            errors.append(f"affordable_now but earliest_date={earliest}, expected {req['request_date']}")
    
    # not_affordable consistency
    if status == 'not_affordable':
        if method != 'not_recommended':
            errors.append(f"not_affordable but method={method}")
        if plan_str != 'none':
            errors.append(f"not_affordable but plan={plan_str}")
    
    # partial_payment rules
    if method == 'partial_payment':
        if req['allows_partial_payment'].lower() != 'true':
            errors.append("partial_payment but request doesn't allow it")
    
    # Plan validation
    if plan_str and plan_str != 'none':
        plan_parts = plan_str.split('|')
        plan_total = 0
        for part in plan_parts:
            try:
                d, a = part.split(':')
                plan_total += float(a)
                datetime.strptime(d, '%Y-%m-%d')
            except (ValueError, IndexError):
                errors.append(f"malformed plan part: {part}")
    
    return errors


if __name__ == '__main__':
    critical, warnings_count, status_dist, method_dist, field_match = main()
    sys.exit(0 if critical == 0 else 1)
