"""Compare staged DEA improvement plans on the public milkProd dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from dea_core import efficiency_primal, joint, single, vertices

INPUT_COLUMNS = ["energy", "vet", "cows"]
TARGET_FRACTIONS = np.array([0.25, 0.60, 1.00])
EFFICIENCY_TOLERANCE = 1e-7
VALIDATION_TOLERANCE = 1e-6


def load_data(path: Path) -> tuple[np.ndarray, np.ndarray]:
    frame = pd.read_csv(path, sep=";")
    data = frame[INPUT_COLUMNS + ["milk"]].to_numpy(dtype=float)
    if not len(data) or not np.isfinite(data).all() or (data <= 0).any():
        raise ValueError("milkProd inputs and milk output must be positive and finite.")
    return data[:, :-1], data[:, -1]


def improvement_paths(
    weighted_vertices: np.ndarray, initial_efficiency: float, targets: np.ndarray
) -> dict[str, np.ndarray]:
    stage_solutions = [single(weighted_vertices, target) for target in targets]
    independent, branches = zip(*stage_solutions)
    nested = joint(weighted_vertices, targets, independent, branches)
    num_inputs = weighted_vertices.shape[1]
    radial = np.repeat((1 - initial_efficiency / targets)[:, None], num_inputs, axis=1)
    return {
        "Independent": np.stack([stage["x"] for stage in independent]),
        "Nested": nested["x"],
        "Radial": radial,
    }


def run_experiment(inputs: np.ndarray, outputs: np.ndarray) -> dict:
    input_per_output = inputs / outputs[:, None]
    dual_vertices = vertices(input_per_output)
    efficiencies = np.array(
        [efficiency_primal(inputs, outputs, x, y) for x, y in zip(inputs, outputs)]
    )
    eligible = np.flatnonzero(efficiencies < 1 - EFFICIENCY_TOLERANCE)
    if not len(eligible):
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
            if shortfall > VALIDATION_TOLERANCE or np.max(achieved) > 1 + VALIDATION_TOLERANCE:
                raise RuntimeError(f"{method}, row {i + 1}: invalid target efficiency.")

            reversal = np.maximum(reductions[:-1] - reductions[1:], 0).sum()
            has_reversal = bool(reversal > VALIDATION_TOLERANCE)
            if method != "Independent" and has_reversal:
                raise RuntimeError(f"{method}, row {i + 1}: an input reduction was reversed.")

            objective = float(np.square(reductions).sum())
            by_method[method].append((objective, (objective / baseline - 1) * 100, has_reversal))

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
