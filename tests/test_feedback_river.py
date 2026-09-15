import unittest
from datetime import date

from src.feedback_river import DataValidationError, aggregate, anonymize_text, transform, validate_records


RECORD = {"id": "1", "created_at": "2026-09-15T10:00:00Z", "country": "BE", "payment_method": "Card", "channel": "Web", "rating": 4, "comment": "Hi"}


class FeedbackRiverTests(unittest.TestCase):
    def test_anonymization_is_deterministic_and_removes_identifiers(self):
        text = "email jane@example.com, +32 470 12 34 56, order #ABC123, https://secret.test/a"
        first = anonymize_text(text)
        self.assertEqual(first, anonymize_text(text))
        self.assertNotIn("jane@example.com", first)
        self.assertNotIn("https://secret.test", first)
        self.assertNotIn("ABC123", first)

    def test_validation_reports_missing_fields(self):
        with self.assertRaisesRegex(DataValidationError, "missing required fields"):
            validate_records([{"id": "1"}])

    def test_transform_anonymizes_optional_fields(self):
        record = {**RECORD, "email": "jane@example.com", "phone": "+32 470 12 34 56", "order_id": "ABC123"}
        result = transform([record])[0]
        self.assertNotIn("jane@example.com", result["email"])
        self.assertNotIn("ABC123", result["order_id"])

    def test_daily_and_weekly_aggregation(self):
        records = transform([RECORD, {**RECORD, "id": "2", "created_at": "2026-09-14T10:00:00Z", "rating": 2, "country": "FR"}])
        daily = aggregate(records, "daily", date(2026, 9, 15))
        weekly = aggregate(records, "weekly", date(2026, 9, 15))
        self.assertEqual(daily["total"], 1)
        self.assertEqual(weekly["total"], 2)
        self.assertEqual(weekly["dimensions"]["country"][1]["value"], "FR")


if __name__ == "__main__":
    unittest.main()
