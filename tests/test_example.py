"""Check the single-unit example using synthetic data with a known reversal."""

import unittest

import numpy as np

from dea_core import efficiency_primal
from examples.compare_plans import compare_plans


class SingleUnitPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inputs = np.array([
            [8.0, 2.0], [14.0, 15.0], [11.0, 13.0],
            [5.0, 10.0], [10.0, 9.0], [2.0, 3.0],
        ])
        self.outputs = np.ones(len(self.inputs))
        self.initial = self.inputs[1].copy()

    def test_example_meets_targets_and_reports_the_planning_tradeoff(self) -> None:
        plan = compare_plans(self.inputs, self.outputs, self.initial, 1.0)

        self.assertTrue(plan["methods"]["Independent"]["has_reversal"])
        self.assertFalse(plan["methods"]["Nested"]["has_reversal"])
        self.assertGreater(plan["methods"]["Nested"]["increase_percent"], 0)
        for method, result in plan["methods"].items():
            reductions = np.array(result["cumulative_reductions"])
            planned = np.array(result["planned_inputs"])
            np.testing.assert_allclose(planned, self.initial * (1 - reductions))
            self.assertAlmostEqual(result["objective"], float(np.square(reductions).sum()))
            achieved = np.array([
                efficiency_primal(self.inputs, self.outputs, row, 1.0) for row in planned
            ])
            np.testing.assert_allclose(result["achieved_efficiencies"], achieved, atol=1e-7)
            self.assertTrue((achieved >= np.array(plan["targets"]) - 1e-6).all())
            self.assertTrue((achieved <= 1 + 1e-6).all())
            if method == "Nested":
                self.assertTrue((np.diff(reductions, axis=0) >= -1e-6).all())

    def test_accepts_custom_targets_and_rejects_invalid_sequences(self) -> None:
        targets = [0.40, 0.70, 1.00]
        plan = compare_plans(self.inputs, self.outputs, self.initial, 1.0, targets)
        self.assertEqual(plan["targets"], targets)
        for invalid in ([], [0.10, 1.00], [0.70, 0.40, 1.00], [0.40, 1.01], [np.nan]):
            with self.subTest(targets=invalid), self.assertRaises(ValueError):
                compare_plans(self.inputs, self.outputs, self.initial, 1.0, invalid)


if __name__ == "__main__":
    unittest.main()
