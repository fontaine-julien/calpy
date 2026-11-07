import unittest

from ops.division import parse_division, prepare_division


def displayed_dividend(layout) -> str:
    digits = "".join(str(value) for value in layout.dividend_cells)
    boundary = layout.dividend_comma_boundary
    if boundary is None:
        return digits
    return f"{digits[:boundary]},{digits[boundary:]}"


class DivisionPreparationTests(unittest.TestCase):
    def test_decimal_divisor_is_made_integer_with_minimal_factor(self):
        layout = prepare_division("12,43/4,56")

        self.assertEqual(layout.transform_label, "× 100")
        self.assertEqual(displayed_dividend(layout), "1243")
        self.assertEqual(layout.divisor_str, "456")
        self.assertEqual(layout.quotient_str, "2")
        self.assertEqual(layout.remainder, 331)

    def test_dot_decimal_separator_is_accepted(self):
        layout = prepare_division("12.43 : 4.56")

        self.assertEqual(layout.original_dividend_str, "12,43")
        self.assertEqual(layout.original_divisor_str, "4,56")
        self.assertEqual(layout.transform_label, "× 100")

    def test_common_terminal_zeros_are_simplified(self):
        layout = prepare_division("4500/900")

        self.assertEqual(layout.transform_label, "÷ 100")
        self.assertEqual(displayed_dividend(layout), "45")
        self.assertEqual(layout.divisor_str, "9")
        self.assertEqual(layout.quotient_str, "5")
        self.assertEqual(layout.remainder, 0)

    def test_largest_common_power_of_ten_is_used(self):
        layout = prepare_division("123000 div 5000")

        self.assertEqual(layout.transform_label, "÷ 1000")
        self.assertEqual(displayed_dividend(layout), "123")
        self.assertEqual(layout.divisor_str, "5")

    def test_decimal_dividend_can_remain_after_minimal_shift(self):
        layout = prepare_division("1,234/0,5")

        self.assertEqual(layout.transform_label, "× 10")
        self.assertEqual(displayed_dividend(layout), "12,34")
        self.assertEqual(layout.divisor_str, "5")
        self.assertEqual(layout.quotient_str, "2,46")

    def test_zero_divisor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "zéro"):
            parse_division("10/0,00")

    def test_invalid_expression_is_rejected_without_partial_match(self):
        with self.assertRaisesRegex(ValueError, "Expression invalide"):
            parse_division("12,43/4,56 texte")


if __name__ == "__main__":
    unittest.main()
