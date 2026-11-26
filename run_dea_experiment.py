"""Compare staged DEA improvement plans on the public milkProd dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from dea_core import (
    FloatArray,
    efficiency_primal,
    enumerate_dual_vertices,
    radial_path,
    solve_monotone_path,
    solve_single_stage,
)

INPUT_COLUMNS = ["energy", "vet", "cows"]
TARGET_FRACTIONS = np.array([0.25, 0.60, 1.00])
EFFICIENCY_TOLERANCE = 1e-7
VALIDATION_TOLERANCE = 1e-6


def load_data(path: Path) -> tuple[FloatArray, FloatArray]:
    """Read and validate the three milkProd inputs and the milk output."""
    frame = pd.read_csv(path, sep=";")
    data = frame[INPUT_COLUMNS + ["milk"]].to_numpy(dtype=float)
    if len(data) == 0 or not np.isfinite(data).all() or (data <= 0).any():
        raise ValueError("milkProd inputs and milk output must be positive and finite.")
    return data[:, :-1], data[:, -1]


def improvement_paths(
    weighted_vertices: FloatArray, initial_efficiency: float, targets: FloatArray
) -> dict[str, FloatArray]:
    """Compute independent, monotone, and proportional staged reductions."""
    stage_solutions = [solve_single_stage(weighted_vertices, target) for target in targets]
    independent = np.stack([reductions for reductions, _ in stage_solutions])
    stage_branches = [branches for _, branches in stage_solutions]
    return {
        "Independent": independent,
        "Nested": solve_monotone_path(weighted_vertices, targets, stage_branches),
        "Radial": radial_path(initial_efficiency, targets, weighted_vertices.shape[1]),
    }


def run_experiment(inputs: FloatArray, outputs: FloatArray) -> dict:
    """Compare path objectives and re-evaluate each stage with the CCR linear program."""
    input_per_output = inputs / outputs[:, None]
    dual_vertices = enumerate_dual_vertices(input_per_output)
    efficiencies = np.array(
        [efficiency_primal(inputs, outputs, x, y) for x, y in zip(inputs, outputs)]
    )
    eligible = np.flatnonzero(efficiencies < 1 - EFFICIENCY_TOLERANCE)
    if len(eligible) == 0:
        raise ValueError("No producers have an initial efficiency below 1.")

    by_method = {"Independent": [], "Nested": [], "Radial": []}
    max_target_shortfall = 0.0

    for i in eligible:
        initial_efficiency = efficiencies[i]
        targets = initial_efficiency + TARGET_FRACTIONS * (1 - initial_efficiency)
        weighted_vertices = dual_vertices * input_per_output[i]
        paths = improvement_paths(weighted_vertices, initial_efficiency, targets)
        baseline = float(np.square(paths["Independent"]).sum())

        for method, reductions in paths.items():
            achieved = np.array(
                [
                    efficiency_primal(inputs, outputs, inputs[i] * (1 - rate), outputs[i])
                    for rate in reductions
                ]
            )
            shortfall = max(0.0, float(np.max(targets - achieved)))
            max_target_shortfall = max(max_target_shortfall, shortfall)
            if (
                shortfall > VALIDATION_TOLERANCE
                or np.max(achieved) > 1 + VALIDATION_TOLERANCE
            ):
                raise RuntimeError(f"{method}, row {i + 1}: invalid target efficiency.")

            reversal = np.maximum(reductions[:-1] - reductions[1:], 0).sum()
            has_reversal = bool(reversal > VALIDATION_TOLERANCE)
            if method != "Independent" and has_reversal:
                raise RuntimeError(f"{method}, row {i + 1}: an input reduction was reversed.")

            objective = float(np.square(reductions).sum())
            increase_percent = (objective / baseline - 1) * 100
            by_method[method].append((objective, increase_percent, has_reversal))

    summary = {}
    for method, records in by_method.items():
        objectives, increases, reversals = zip(*records)
        summary[method] = {
            "mean_objective": float(np.mean(objectives)),
            "mean_increase_percent": float(np.mean(increases)),
            "max_increase_percent": max(increases),
            "reversal_count": sum(reversals),
        }
    return {
        "producer_count": len(inputs),
        "evaluated_producers": len(eligible),
        "max_target_shortfall": max_target_shortfall,
        "methods": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Path to milkProd.csv or milkProd.csv.gz")
    args = parser.parse_args()
    try:
        inputs, outputs = load_data(args.dataset)
        result = run_experiment(inputs, outputs)
    except (KeyError, OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
