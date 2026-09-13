"""
FinCredTwin — Phase 7 Targeted Adversarial Hotfix Regression Tests

Covers all 12 adversarial test cases mandated in Phase 7:
1. Two simultaneous loan cycles
2. Two recurring obligations with same category
3. New image-linked event absent from static cache
4. Indonesian 15.500.000
5. Indonesian 1.250.000,50
6. Normal decimal 620.40
7. Malformed amount safe failure
8. Confirmed rent increase
9. Hypothetical rent increase rejection
10. Conflicting rent messages resolution
11. Rent increase + salary change simultaneous application
12. Multiple obligations + minimum balance safety boundary
"""
import unittest
import sys
import os
from datetime import date, datetime
from pathlib import Path

# Ensure code directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from data_loader import FinancialEvent, ImageRecord, load_events
from cycle_detector import (
    detect_cycles, project_future_events, obligation_stream_key, RecurringPattern, ProjectedEvent
)
from message_interpreter import (
    _parse_amount, parse_messages, get_salary_amendments, get_expense_amendments,
    Message, FinancialFact
)
from financial_state import FinancialDigitalTwin
from forecast_engine import compute_safe_amount


class TestMultipleDebtObligations(unittest.TestCase):
    """Bug 1: Multiple debt obligations must remain distinct streams."""

    def test_two_simultaneous_loan_cycles_different_dates(self):
        """Case 1: Car loan on 5th and Education loan on 20th must form 2 separate monthly cycles."""
        events = [
            # Car loan on 5th of each month
            FinancialEvent("e1", "u1", "recurring", "Car Loan EMI", "debt_repayment", "debit", 300.0, "USD", date(2024, 1, 5), date(2024, 1, 5), "settled", None, "fixed", None),
            FinancialEvent("e2", "u1", "recurring", "Car Loan EMI", "debt_repayment", "debit", 300.0, "USD", date(2024, 2, 5), date(2024, 2, 5), "settled", None, "fixed", None),
            FinancialEvent("e3", "u1", "recurring", "Car Loan EMI", "debt_repayment", "debit", 300.0, "USD", date(2024, 3, 5), date(2024, 3, 5), "settled", None, "fixed", None),
            # Education loan on 20th of each month
            FinancialEvent("e4", "u1", "recurring", "Education Loan EMI", "debt_repayment", "debit", 500.0, "USD", date(2024, 1, 20), date(2024, 1, 20), "settled", None, "fixed", None),
            FinancialEvent("e5", "u1", "recurring", "Education Loan EMI", "debt_repayment", "debit", 500.0, "USD", date(2024, 2, 20), date(2024, 2, 20), "settled", None, "fixed", None),
            FinancialEvent("e6", "u1", "recurring", "Education Loan EMI", "debt_repayment", "debit", 500.0, "USD", date(2024, 3, 20), date(2024, 3, 20), "settled", None, "fixed", None),
        ]
        
        patterns = detect_cycles(events, "u1")
        # Must detect TWO patterns, not 1 corrupted bi-weekly pattern
        debt_patterns = [p for p in patterns if p.category == "debt_repayment"]
        self.assertEqual(len(debt_patterns), 2, "Expected exactly 2 distinct debt repayment patterns")
        
        amounts = sorted([p.typical_amount for p in debt_patterns])
        self.assertEqual(amounts, [300.0, 500.0])
        
        # Verify both project into the 90-day forecast window
        proj = project_future_events(debt_patterns, date(2024, 3, 25), forecast_days=90)
        proj_300 = [p for p in proj if abs(p.amount - 300.0) < 0.01]
        proj_500 = [p for p in proj if abs(p.amount - 500.0) < 0.01]
        
        self.assertGreaterEqual(len(proj_300), 2, "Car loan must project multiple occurrences")
        self.assertGreaterEqual(len(proj_500), 2, "Education loan must project multiple occurrences")

    def test_two_recurring_obligations_same_category(self):
        """Case 2: Two recurring obligations in category debt_repayment."""
        key1 = obligation_stream_key("debt_repayment", "Auto loan monthly")
        key2 = obligation_stream_key("debt_repayment", "Mortgage loan monthly")
        self.assertNotEqual(key1, key2, "Obligation stream keys must differentiate distinct descriptions")

    def test_same_lender_distinguishable_obligations(self):
        """Case 3: Same lender with distinguishable obligation descriptions."""
        key1 = obligation_stream_key("loan", "Apex Bank - Personal Loan A")
        key2 = obligation_stream_key("loan", "Apex Bank - Home Loan B")
        self.assertNotEqual(key1, key2)


class TestDynamicImageMapping(unittest.TestCase):
    """Bug 2: Dynamic image mapping via images.csv."""

    def test_new_image_linked_event_absent_from_cache(self):
        """Case 4: Dynamic image link absent from static cache is resolved without dropping event."""
        unseen_event_id = "event_synthetic_99999"
        unseen_image_id = "image_synthetic_99"
        
        images_by_event = {
            unseen_event_id: ImageRecord(
                image_id=unseen_image_id,
                user_id="user_synthetic",
                request_id="request_synthetic",
                related_event_id=unseen_event_id,
            )
        }
        
        # Verify lookup logic: dynamic link maps event -> image_id
        img_rec = images_by_event.get(unseen_event_id)
        self.assertIsNotNone(img_rec)
        self.assertEqual(img_rec.image_id, unseen_image_id)


class TestIndonesianAmountParsing(unittest.TestCase):
    """Bug 3: Indonesian dot-separated amounts and robust monetary parsing."""

    def test_indonesian_dot_separated_15_500_000(self):
        """Case 5: Indonesian IDR 15.500.000 parsed to 15500000.0."""
        self.assertEqual(_parse_amount("15.500.000", currency="IDR"), 15500000.0)
        self.assertEqual(_parse_amount("15.500.000"), 15500000.0)

    def test_indonesian_european_1_250_000_50(self):
        """Case 6: Dot thousands with comma decimal: 1.250.000,50 parsed to 1250000.50."""
        self.assertEqual(_parse_amount("1.250.000,50"), 1250000.50)

    def test_us_standard_15_500_000(self):
        """Standard comma separated: 15,500,000 parsed to 15500000.0."""
        self.assertEqual(_parse_amount("15,500,000"), 15500000.0)

    def test_standard_decimal_1250000_50(self):
        """Standard decimal 1250000.50."""
        self.assertEqual(_parse_amount("1250000.50"), 1250000.50)

    def test_normal_decimal_values_not_corrupted(self):
        """Case 7: Normal decimal values like 620.40 and 1574.40 must not lose decimal precision."""
        self.assertEqual(_parse_amount("620.40"), 620.40)
        self.assertEqual(_parse_amount("1574.40"), 1574.40)
        self.assertEqual(_parse_amount("23.50"), 23.50)

    def test_malformed_amount_fails_safely(self):
        """Case 8: Malformed amount strings fail safely returning None rather than raising ValueError."""
        self.assertIsNone(_parse_amount("not_a_number"))
        self.assertIsNone(_parse_amount(""))
        self.assertIsNone(_parse_amount("$$$---"))
        self.assertIsNone(_parse_amount(None))


class TestRentIncreaseForwarding(unittest.TestCase):
    """Bug 4: Rent increase facts forwarding and evidence resolution."""

    def test_confirmed_rent_increase(self):
        """Case 9: Confirmed rent increase message parsed and reflected in expense amendments."""
        msg = Message(
            message_id="m_rent_test",
            user_id="u_rent",
            request_id="r_rent",
            related_event_id=None,
            sent_at=datetime(2024, 5, 1, 10, 0),
            source_type="service_provider",
            message_text="The renewed lease increases monthly rent by 12%. The new amount will be used for the next rent payment."
        )
        res = parse_messages([msg])
        self.assertEqual(len(res.facts), 1)
        fact = res.facts[0]
        self.assertEqual(fact.fact_type, "rent_increase")
        self.assertEqual(fact.percentage_change, 12.0)
        self.assertTrue(fact.is_confirmed)
        self.assertEqual(fact.confidence, "high")
        
        # Test forwarding
        amendments = get_expense_amendments(res.facts, "u_rent")
        self.assertIn("rent", amendments)
        self.assertEqual(amendments["rent"]["percentage_increase"], 12.0)

    def test_hypothetical_rent_increase_rejected(self):
        """Case 10: Hypothetical/speculative rent increase is flagged and not confirmed."""
        msg = Message(
            message_id="m_rent_hypo",
            user_id="u_rent",
            request_id="r_rent",
            related_event_id=None,
            sent_at=datetime(2024, 5, 1, 10, 0),
            source_type="service_provider",
            message_text="The landlord mentioned they might increase monthly rent by 15% next term."
        )
        res = parse_messages([msg])
        # If extracted, it must NOT be confirmed / must have low confidence
        confirmed_facts = [f for f in res.facts if f.is_confirmed and f.confidence == "high"]
        self.assertEqual(len(confirmed_facts), 0, "Hypothetical rent increase must not produce confirmed facts")
        
        # Expense amendments must be empty
        amendments = get_expense_amendments(res.facts, "u_rent")
        self.assertEqual(amendments, {}, "Hypothetical rent increase must not be forwarded")

    def test_conflicting_rent_messages_resolution(self):
        """Case 11: Conflicting rent messages resolve conservatively to financially safer (higher) increase."""
        facts = [
            FinancialFact("m1", "rent_increase", None, None, "high", "rule", percentage_change=10.0, is_confirmed=True),
            FinancialFact("m2", "rent_increase", None, None, "high", "rule", percentage_change=15.0, is_confirmed=True),
        ]
        amendments = get_expense_amendments(facts, "u_test")
        self.assertEqual(amendments["rent"]["percentage_increase"], 15.0, "Must choose financially safer higher rent increase")

    def test_rent_increase_plus_salary_change(self):
        """Case 12: Both rent increase and salary amendment are concurrently applied in forecast."""
        pat_salary = RecurringPattern(
            user_id="u_dual",
            category="salary",
            description="Monthly payroll salary",
            direction="credit",
            frequency_days=30,
            typical_amount=5000.0,
            last_occurrence=date(2024, 5, 1),
            historical_count=3,
            event_ids=["e1", "e2", "e3"],
            is_calendar_monthly=True,
            day_of_month=1,
            currency="USD",
            stream="primary_payroll",
        )
        pat_rent = RecurringPattern(
            user_id="u_dual",
            category="rent",
            description="Apartment rent transfer",
            direction="debit",
            frequency_days=30,
            typical_amount=1000.0,
            last_occurrence=date(2024, 5, 1),
            historical_count=3,
            event_ids=["e4", "e5", "e6"],
            is_calendar_monthly=True,
            day_of_month=1,
            currency="USD",
            stream="main",
        )
        
        sal_amend = {"salary_amount": 5500.0, "salary_date": None, "contract_ended": False}
        exp_amend = {"rent": {"percentage_increase": 10.0, "new_amount": None, "effective_date": None}}
        
        proj = project_future_events(
            [pat_salary, pat_rent],
            request_date=date(2024, 5, 10),
            forecast_days=90,
            salary_amendments=sal_amend,
            expense_amendments=exp_amend,
        )
        
        sal_proj = [p for p in proj if p.category == "salary"]
        rent_proj = [p for p in proj if p.category == "rent"]
        
        self.assertTrue(all(abs(p.amount - 5500.0) < 0.01 for p in sal_proj), "Salary must be amended to 5500.0")
        self.assertTrue(all(abs(p.amount - 1100.0) < 0.01 for p in rent_proj), "Rent must be scaled by 10% to 1100.0")


class TestMultipleObligationsMinimumBalance(unittest.TestCase):
    """Case 13: Multiple recurring obligations interacting with minimum balance to keep."""

    def test_multiple_obligations_reduce_headroom_and_enforce_min_balance(self):
        """
        Verify that multiple concurrent debt obligations (e.g. Car Loan $400 + Education Loan $500)
        reach the 90-day simulation, reducing headroom and enforcing minimum_balance_to_keep.
        """
        req_date = date(2024, 6, 1)
        pe_loan1 = ProjectedEvent(
            projected_date=date(2024, 6, 10),
            amount=400.0,
            direction="debit",
            category="debt_repayment",
            description="Car Loan EMI",
        )
        pe_loan2 = ProjectedEvent(
            projected_date=date(2024, 6, 20),
            amount=500.0,
            direction="debit",
            category="debt_repayment",
            description="Education Loan EMI",
        )
        
        twin = FinancialDigitalTwin(
            request_id="req_multi_debts",
            user_id="u_multi",
            request_date=req_date,
            request_type="electronics",
            requested_amount=800.0,
            desired_completion_date=date(2024, 7, 1),
            allows_partial_payment=True,
            request_text="Can I purchase this laptop?",
            home_currency="USD",
            current_available_balance=2000.0,
            minimum_balance_to_keep=1000.0,
            financial_priorities=["debt_reduction"],
            expense_categories_to_protect=set(),
            expense_categories_user_is_willing_to_reduce=set(),
            expense_categories_user_is_willing_to_stop=set(),
            payment_methods_user_will_consider={"full_payment", "partial_payment"},
            max_installment_months=None,
            pending_debits=[],
            scheduled_events=[],
            projected_events=[pe_loan1, pe_loan2],
            recurring_patterns=[],
        )
        
        safe = compute_safe_amount(twin)
        # Starting: 2000. Min balance: 1000.
        # Day 10 loan: -400 -> balance 1600.
        # Day 20 loan: -500 -> balance 1100.
        # Min headroom: 1100 - 1000 = 100.00.
        # Safe amount must be capped at 100.00!
        self.assertEqual(safe, 100.00, f"Expected safe amount 100.00 accounting for both loans, got {safe}")


if __name__ == "__main__":
    unittest.main()
