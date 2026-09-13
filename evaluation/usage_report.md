# FinCredTwin Usage Report

## Run Summary

| Metric | Value |
|---|---|
| Date | 2026-09-13 |
| Provider / Model | none |
| LLM Calls | 0 |
| Vision Calls | 0 |
| Input Tokens | 0 |
| Output Tokens | 0 |
| Total Tokens | 0 |
| Average Tokens / Request | 0 |
| Estimated Total Cost | $0.00 |
| Estimated Cost / Request | $0.00 |

## Architecture Notes

This run executed the fully hardened deterministic FinCredTwin pipeline:
- Rule-based message interpreter (20+ robust regex patterns with provenance across English and Indonesian)
- Provenance-verified image amount cache (16/16 verified offline image extractions)
- Deterministic 90-day cashflow simulation engine with exact daily balance invariants
- Adversarial prompt injection defense (quarantining unexecutable instruction payloads)
- Zero external LLM or Vision API calls

## Performance & Execution Profile

| Phase | Duration |
|---|---|
| Image cache validation | < 0.01s |
| Dataset loading (250 requests, 25,342 events) | 0.25s |
| Message parsing & injection defense (215 messages) | < 0.02s |
| Request processing (250 requests) | 0.85s |
| Safety firewall & validation | < 0.02s |
| Output serialization | < 0.02s |
| **Total Pipeline Runtime** | **~1.15s** |
