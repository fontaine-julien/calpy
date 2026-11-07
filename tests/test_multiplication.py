import unittest

from ops.multiplication import compute_french_multiplication, shift_dot_columns


class MultiplicationShiftTests(unittest.TestCase):
    def test_each_partial_product_gets_one_dot_per_shift(self):
        layout = compute_french_multiplication("493", 0, "237", 0)

        self.assertEqual(shift_dot_columns(layout.width, 0), [])
        self.assertEqual(shift_dot_columns(layout.width, 1), [layout.width - 1])
        self.assertEqual(
            shift_dot_columns(layout.width, 2),
            [layout.width - 2, layout.width - 1],
        )

        for shift, partial in enumerate(layout.partials):
            for column in shift_dot_columns(layout.width, shift):
                self.assertIsNone(partial[column])


if __name__ == "__main__":
    unittest.main()
