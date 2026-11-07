import unittest

from main import detect_operation


class OperationDetectionTests(unittest.TestCase):
    def test_supported_operators(self):
        cases = {
            "1246 + 325": "Addition",
            "2048 - 16": "Soustraction",
            "2048 − 16": "Soustraction",
            "493 * 37": "Multiplication",
            "493 x 37": "Multiplication",
            "493 × 37": "Multiplication",
            "12,43 / 4,56": "Division",
            "2048 : 8": "Division",
            "2048 div 8": "Division",
        }
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                self.assertEqual(detect_operation(expression), expected)

    def test_missing_operator_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "introuvable"):
            detect_operation("1246 325")

    def test_mixed_operators_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "une seule opération"):
            detect_operation("1 + 2 * 3")


if __name__ == "__main__":
    unittest.main()
