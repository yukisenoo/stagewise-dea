import gzip
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

from dea_core import (
    efficiency_primal,
    enumerate_dual_vertices,
    solve_convex_qp,
    solve_with_clarabel,
)
from run_dea_experiment import load_data, run_experiment


class DualVertexTests(unittest.TestCase):
    def test_dual_vertices_agree_with_ccr_lp(self) -> None:
        inputs = np.array([[8.0, 2.0], [14.0, 15.0], [2.0, 3.0]])
        outputs = np.ones(len(inputs))
        vertices = enumerate_dual_vertices(inputs / outputs[:, None])
        dual_efficiencies = 1.0 / (inputs @ vertices.T).min(axis=1)
        primal_efficiencies = [
            efficiency_primal(inputs, outputs, row, output)
            for row, output in zip(inputs, outputs)
        ]

        np.testing.assert_allclose(dual_efficiencies, primal_efficiencies, atol=1e-10)


class QuadraticProgramTests(unittest.TestCase):
    def setUp(self) -> None:
        self.weights = np.eye(1)
        self.matrix = np.array([[-1.0], [1.0]])
        self.limits = np.array([-0.25, 0.75])
        self.initial = np.array([0.5])

    def test_solution_matches_analytic_optimum_and_lower_bound(self) -> None:
        solution = solve_convex_qp(self.weights, self.matrix, self.limits, self.initial)

        self.assertIsNotNone(solution)
        np.testing.assert_allclose(solution.reductions, [0.25], atol=1e-8)
        self.assertAlmostEqual(solution.objective, 0.0625, places=8)
        self.assertAlmostEqual(solution.lower_bound, 0.0625, places=8)

    def test_retries_with_clarabel_when_dual_fit_fails(self) -> None:
        with (
            patch("dea_core.nnls", side_effect=RuntimeError("dual fit failed")),
            patch("dea_core.solve_with_clarabel", wraps=solve_with_clarabel) as fallback,
        ):
            solution = solve_convex_qp(self.weights, self.matrix, self.limits, self.initial)

        fallback.assert_called_once()
        self.assertIsNotNone(solution)
        self.assertAlmostEqual(solution.objective, 0.0625, places=8)
        self.assertAlmostEqual(solution.lower_bound, 0.0625, places=8)

    def test_returns_none_for_an_infeasible_branch(self) -> None:
        limits = np.array([-1.0, 0.5])

        self.assertIsNone(solve_convex_qp(self.weights, self.matrix, limits, self.initial))


class ExperimentTests(unittest.TestCase):
    def test_monotone_path_avoids_reversals_and_matches_exhaustive_search(self) -> None:
        inputs = np.array([
            [8.0, 2.0],
            [14.0, 15.0],
            [11.0, 13.0],
            [5.0, 10.0],
            [10.0, 9.0],
            [2.0, 3.0],
        ])
        outputs = np.ones(len(inputs))

        summary = run_experiment(inputs, outputs)
        # Disable pruning so every feasible vertex combination reaches the solver.
        with patch("dea_core.PRUNING_TOLERANCE", -np.inf):
            exhaustive = run_experiment(inputs, outputs)

        self.assertEqual(summary["evaluated_producers"], 4)
        self.assertLess(summary["max_target_shortfall"], 1e-6)
        methods = summary["methods"]
        self.assertEqual(methods["Independent"]["reversal_count"], 3)
        self.assertEqual(methods["Nested"]["reversal_count"], 0)
        self.assertEqual(methods["Radial"]["reversal_count"], 0)
        self.assertGreater(
            methods["Nested"]["mean_objective"], methods["Independent"]["mean_objective"]
        )
        self.assertLess(methods["Nested"]["mean_objective"], methods["Radial"]["mean_objective"])
        self.assertAlmostEqual(
            methods["Nested"]["mean_objective"],
            exhaustive["methods"]["Nested"]["mean_objective"],
            places=9,
        )

    def test_loads_gzip_dataset(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "milkProd.csv.gz"
            path.write_bytes(gzip.compress(b"energy;vet;cows;milk\n10;20;30;40\n"))

            inputs, outputs = load_data(path)

            np.testing.assert_array_equal(inputs, [[10.0, 20.0, 30.0]])
            np.testing.assert_array_equal(outputs, [40.0])


if __name__ == "__main__":
    unittest.main()
