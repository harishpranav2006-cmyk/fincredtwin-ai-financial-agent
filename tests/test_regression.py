"""
FinCredTwin — Golden Regression Test Suite
Tests fundamental rules and invariants rather than hardcoded outputs.
"""
import unittest
from datetime import date, timedelta
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from cycle_detector import (
    add_calendar_months,
    salary_stream_key,
    EXCLUDE_SALARY_DESCS,
    TERMINAL_SALARY_DESCS,
)
from scenario_generator import _fmt_amount
from ranker import rank_plans
from forecast_engine import convert_to_home_currency


class TestCalendarMath(unittest.TestCase):
    def test_leap_year_february(self):
        """Ensure month-end stepping handles leap years properly."""
        # 2024 is a leap year
        d = date(2024, 1, 31)
        next_d = add_calendar_months(d, 31, 1)
        self.assertEqual(next_d, date(2024, 2, 29))
        
        # 2023 is not a leap year
        d_non_leap = date(2023, 1, 31)
        next_d_non = add_calendar_months(d_non_leap, 31, 1)
        self.assertEqual(next_d_non, date(2023, 2, 28))

    def test_regular_day_pinning(self):
        """Verify the day of the month does not drift across 30 and 31 day months."""
        start = date(2024, 3, 15)
        d1 = add_calendar_months(start, 15, 1)
        self.assertEqual(d1, date(2024, 4, 15))
        d2 = add_calendar_months(d1, 15, 1)
        self.assertEqual(d2, date(2024, 5, 15))
        d3 = add_calendar_months(d2, 15, 1)
        self.assertEqual(d3, date(2024, 6, 15))


class TestSalaryStreamSeparation(unittest.TestCase):
    def test_stream_keys(self):
        """Verify that distinct income streams are separated."""
        self.assertEqual(salary_stream_key("Primary household salary"), "primary_payroll")
        self.assertEqual(salary_stream_key("Second household income"), "second_household_income")
        self.assertEqual(salary_stream_key("Delivery platform payout"), "gig_earnings")
        self.assertEqual(salary_stream_key("Freelance invoice payment"), "freelance_invoice")

    def test_excluded_salary_spikes(self):
        """Verify bonuses and one-off arrears are excluded from regular base cycle."""
        self.assertIn("quarterly performance bonus", EXCLUDE_SALARY_DESCS)
        self.assertIn("promotion arrears payment", EXCLUDE_SALARY_DESCS)

    def test_terminal_salary(self):
        """Verify terminal payroll stops ongoing salary projection."""
        self.assertIn("final employer payroll", TERMINAL_SALARY_DESCS)
        self.assertIn("previous employer payroll", TERMINAL_SALARY_DESCS)


class TestFormattingRules(unittest.TestCase):
    def test_amount_formatting(self):
        """Verify integer formatting vs 2-decimal floating point precision."""
        self.assertEqual(_fmt_amount(25256.0), "25256")
        self.assertEqual(_fmt_amount(620.40), "620.40")
        self.assertEqual(_fmt_amount(996.6), "996.60")
        self.assertEqual(_fmt_amount(1574.40), "1574.40")
        self.assertEqual(_fmt_amount(15952906.67), "15952906.67")


class TestFXConversion(unittest.TestCase):
    def test_direct_and_reverse_conversion(self):
        """Verify dated fixed exchange rate lookup and reverse fallback."""
        fx_rates = {
            (date(2024, 1, 1), "USD", "INR"): 83.0,
        }
        fx_dates = [date(2024, 1, 1)]
        
        # Same currency
        self.assertEqual(convert_to_home_currency(100.0, "INR", "INR", date(2024, 1, 1), fx_rates, fx_dates), 100.0)
        
        # Direct
        converted = convert_to_home_currency(10.0, "USD", "INR", date(2024, 1, 1), fx_rates, fx_dates)
        self.assertAlmostEqual(converted, 830.0)
        
        # Reverse
        rev_converted = convert_to_home_currency(830.0, "INR", "USD", date(2024, 1, 1), fx_rates, fx_dates)
        self.assertAlmostEqual(rev_converted, 10.0)


class TestRankerHierarchy(unittest.TestCase):
    def test_comparator_tuple_order(self):
        """Ensure completion before deadline strictly dominates other metrics."""
        from scenario_generator import CandidatePlan
        
        deadline = date(2024, 4, 1)
        
        # Plan A: Completes on time (cost 1000)
        plan_a = CandidatePlan(
            method="installments",
            affordability_status="affordable_with_plan",
            payment_plan_str="plan_a",
            payments={},
            total_payable_amount=1000.0,
            first_payment_date=date(2024, 3, 1),
            completion_date=date(2024, 3, 31),
            num_payments=2,
            is_safe=True,
        )
        
        # Plan B: Misses deadline by 1 day (cost 500 - cheaper, but late)
        plan_b = CandidatePlan(
            method="wait",
            affordability_status="affordable_later",
            payment_plan_str="plan_b",
            payments={},
            total_payable_amount=500.0,
            first_payment_date=date(2024, 4, 2),
            completion_date=date(2024, 4, 2),
            num_payments=1,
            is_safe=True,
        )
        
        winner = rank_plans([plan_b, plan_a], deadline)
        self.assertEqual(winner.method, "installments")
        self.assertEqual(winner.payment_plan_str, "plan_a")


if __name__ == '__main__':
    unittest.main()
