"""Compare and verify two staged plans for one producer against a fixed DEA frontier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from numpy.typing import ArrayLike
import pandas as pd

from dea_core import efficiency_primal, enumerate_dual_vertices
from run_dea_experiment import (
    EFFICIENCY_TOLERANCE,
    INPUT_COLUMNS,
    TARGET_FRACTIONS,
    VALIDATION_TOLERANCE,
    improvement_paths,
    load_data,
)


def compare_plans(
    reference_inputs: ArrayLike,
    reference_outputs: ArrayLike,
    initial_inputs: ArrayLike,
    initial_output: float,
    targets: ArrayLike | None = None,
) -> dict:
    """Return cumulative reductions, planned inputs, CCR checks, and J for one unit.

    Reference inputs have shape (units, inputs); reference outputs have shape
    (units,). The target unit has one input vector and one fixed positive output.
    Targets default to closing 25%, 60%, and 100% of its initial efficiency gap.
    All reductions are fractions of the initial inputs, not of the previous stage.
    """
    inputs = np.asarray(reference_inputs, dtype=float)
    outputs = np.asarray(reference_outputs, dtype=float)
    initial = np.asarray(initial_inputs, dtype=float)
    if (
        inputs.ndim != 2
        or min(inputs.shape) == 0
        or outputs.shape != (len(inputs),)
        or initial.shape != (inputs.shape[1],)
        or np.ndim(initial_output) != 0
    ):
        raise ValueError("Provide a reference input matrix, one output per unit, and one target unit.")
    values = np.r_[inputs.ravel(), outputs, initial, initial_output]
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("All inputs and outputs must be positive and finite.")

    initial_efficiency = efficiency_primal(inputs, outputs, initial, initial_output)
    if initial_efficiency >= 1 - EFFICIENCY_TOLERANCE:
        raise ValueError("The target unit must have initial efficiency below 1.")
    targets = np.asarray(
        initial_efficiency + TARGET_FRACTIONS * (1 - initial_efficiency)
        if targets is None else targets,
        dtype=float,
    )
    if (
        targets.ndim != 1
        or targets.size == 0
        or not np.isfinite(targets).all()
        or (targets <= initial_efficiency).any()
        or (targets > 1).any()
        or (np.diff(targets) < 0).any()
    ):
        raise ValueError("Targets must be nondecreasing, above initial efficiency, and at most 1.")

    vertices = enumerate_dual_vertices(inputs / outputs[:, None])
    paths = improvement_paths(vertices * initial / initial_output, initial_efficiency, targets)
    baseline = float(np.square(paths["Independent"]).sum())
    methods = {}
    for method in ("Independent", "Nested"):
        reductions = paths[method]
        planned_inputs = initial * (1 - reductions)
        achieved = np.array([
            efficiency_primal(inputs, outputs, row, initial_output) for row in planned_inputs
        ])
        reversal = float(np.maximum(reductions[:-1] - reductions[1:], 0).sum())
        has_reversal = reversal > VALIDATION_TOLERANCE
        if (
            (achieved < targets - VALIDATION_TOLERANCE).any()
            or (achieved > 1 + VALIDATION_TOLERANCE).any()
            or (reductions < -VALIDATION_TOLERANCE).any()
            or (reductions >= 1).any()
            or (method == "Nested" and has_reversal)
        ):
            raise RuntimeError(f"{method}: the plan failed the CCR or reduction checks.")
        objective = float(np.square(reductions).sum())
        methods[method] = {
            "cumulative_reductions": reductions.tolist(),
            "planned_inputs": planned_inputs.tolist(),
            "achieved_efficiencies": achieved.tolist(),
            "objective": objective,
            "increase_percent": (objective / baseline - 1) * 100,
            "has_reversal": has_reversal,
        }
    return {
        "reference_producers": len(inputs),
        "initial_inputs": initial.tolist(),
        "fixed_output": float(initial_output),
        "initial_efficiency": initial_efficiency,
        "targets": targets.tolist(),
        "methods": methods,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Path to milkProd.csv or milkProd.csv.gz")
    parser.add_argument("--farm-no", type=int, default=80, help="milkProd farmNo (default: 80)")
    parser.add_argument("--targets", type=float, nargs="+", help="Optional efficiency targets")
    args = parser.parse_args()
    try:
        inputs, outputs = load_data(args.dataset)
        identifiers = pd.read_csv(args.dataset, sep=";", usecols=["farmNo"])["farmNo"]
        matching_rows = np.flatnonzero(identifiers.to_numpy() == args.farm_no)
        if len(matching_rows) != 1:
            raise ValueError(f"Expected one row for farmNo {args.farm_no}; found {len(matching_rows)}.")
        row = int(matching_rows[0])
        result = compare_plans(inputs, outputs, inputs[row], outputs[row], args.targets)
    except (KeyError, OSError, ValueError) as error:
        parser.error(str(error))
    result = {"farm_no": args.farm_no, "input_columns": INPUT_COLUMNS, **result}
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
