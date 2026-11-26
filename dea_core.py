"""Optimize staged input reductions for an input-oriented CCR DEA model."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, islice, product

import clarabel
import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy import sparse
from scipy.linalg import block_diag
from scipy.optimize import linprog, minimize, nnls

FloatArray = NDArray[np.float64]

VERTEX_BATCH_SIZE = 4_000
VERTEX_DETERMINANT_TOLERANCE = 1e-11
VERTEX_FEASIBILITY_TOLERANCE = 1e-8
VERTEX_ZERO_TOLERANCE = 1e-10
VERTEX_ROUNDING_DIGITS = 9

MIN_INPUT_FRACTION = 1e-6
CONSTRAINT_TOLERANCE = 2e-7
ACTIVE_CONSTRAINT_TOLERANCE = 1e-6
PRUNING_TOLERANCE = 1e-10
SLSQP_OBJECTIVE_TOLERANCE = 1e-12
SLSQP_GAP_TOLERANCE = 2e-8
VERIFIED_GAP_TOLERANCE = 2e-7
SLSQP_MAX_ITERATIONS = 700
NNLS_MAX_ITERATIONS = 5_000
CLARABEL_TOLERANCE = 1e-11
CLARABEL_MAX_ITERATIONS = 300
LP_INFEASIBLE_STATUS = 2


@dataclass(frozen=True)
class QuadraticSolution:
    """Store a feasible reduction vector and a dual lower bound on its objective."""

    reductions: FloatArray
    objective: float
    lower_bound: float


def enumerate_dual_vertices(input_per_output: FloatArray) -> FloatArray:
    """Enumerate vertices of the CCR dual polyhedron for one positive output."""
    producer_count, input_count = input_per_output.shape
    coefficients = np.vstack([input_per_output, np.eye(input_count)])
    limits = np.r_[np.ones(producer_count), np.zeros(input_count)]
    row_combinations = combinations(range(len(limits)), input_count)
    vertices = {}

    while batch := list(islice(row_combinations, VERTEX_BATCH_SIZE)):
        rows = np.asarray(batch)
        active_systems = coefficients[rows]
        nonsingular = np.abs(np.linalg.det(active_systems)) > VERTEX_DETERMINANT_TOLERANCE
        if not nonsingular.any():
            continue

        rhs = limits[rows[nonsingular]][..., None]
        candidates = np.linalg.solve(active_systems[nonsingular], rhs)[..., 0]
        slack = coefficients @ candidates.T - limits[:, None]
        feasible = np.min(slack, axis=0) >= -VERTEX_FEASIBILITY_TOLERANCE
        for vertex in candidates[feasible]:
            vertex[np.abs(vertex) < VERTEX_ZERO_TOLERANCE] = 0
            key = tuple(np.round(vertex, VERTEX_ROUNDING_DIGITS))
            vertices[key] = vertex

    return np.array([vertices[key] for key in sorted(vertices)])


def efficiency_primal(
    reference_inputs: ArrayLike,
    reference_outputs: ArrayLike,
    target_inputs: ArrayLike,
    target_outputs: ArrayLike,
) -> float:
    """Compute the input-oriented CCR efficiency using the primal linear program."""
    inputs = np.asarray(reference_inputs)
    outputs = np.asarray(reference_outputs)
    if outputs.ndim == 1:
        outputs = outputs[:, None]

    input_scale = inputs.max(axis=0)
    output_scale = outputs.max(axis=0)
    scaled_inputs = inputs / input_scale
    scaled_outputs = outputs / output_scale
    scaled_target_inputs = np.asarray(target_inputs) / input_scale
    scaled_target_outputs = np.atleast_1d(target_outputs) / output_scale

    reference_count, input_count = inputs.shape
    output_count = outputs.shape[1]
    # The first variable is the common input multiplier. The rest weight reference units.
    input_constraints = np.column_stack([-scaled_target_inputs, scaled_inputs.T])
    output_constraints = np.column_stack([np.zeros(output_count), -scaled_outputs.T])
    result = linprog(
        np.r_[1.0, np.zeros(reference_count)],
        A_ub=np.vstack([input_constraints, output_constraints]),
        b_ub=np.r_[np.zeros(input_count), -scaled_target_outputs],
        bounds=(0, None),
        method="highs",
    )
    if not result.success:
        raise RuntimeError(result.message)
    return float(result.fun)


def dual_objective_lower_bound(
    weights: FloatArray,
    constraint_matrix: FloatArray,
    constraint_limits: FloatArray,
    multipliers: FloatArray,
) -> float:
    """Evaluate the Lagrangian dual at nonnegative inequality multipliers."""
    nonnegative_multipliers = np.maximum(multipliers, 0)
    linear_term = constraint_matrix.T @ nonnegative_multipliers
    minimum_lagrangian = -0.25 * linear_term @ np.linalg.solve(weights, linear_term)
    return float(minimum_lagrangian - constraint_limits @ nonnegative_multipliers)


def solve_with_clarabel(
    weights: FloatArray, constraint_matrix: FloatArray, constraint_limits: FloatArray
) -> tuple[FloatArray, FloatArray]:
    """Solve the same inequalities with a conic solver and return its dual variables."""
    settings = clarabel.DefaultSettings()
    settings.verbose = False
    settings.tol_gap_abs = CLARABEL_TOLERANCE
    settings.tol_gap_rel = CLARABEL_TOLERANCE
    settings.tol_feas = CLARABEL_TOLERANCE
    settings.max_iter = CLARABEL_MAX_ITERATIONS
    solver = clarabel.DefaultSolver(
        sparse.csc_matrix(np.triu(2 * weights)),
        np.zeros(len(weights)),
        sparse.csc_matrix(constraint_matrix),
        constraint_limits,
        [clarabel.NonnegativeConeT(len(constraint_limits))],
        settings,
    )
    solution = solver.solve()
    if str(solution.status) not in ("Solved", "AlmostSolved"):
        raise RuntimeError(f"Clarabel failed ({solution.status}).")
    return np.asarray(solution.x), np.asarray(solution.z)


def solve_convex_qp(
    weights: FloatArray,
    constraint_matrix: FloatArray,
    constraint_limits: FloatArray,
    initial: FloatArray,
) -> QuadraticSolution | None:
    """Minimize r.T @ weights @ r under linear inequalities.

    Return None for an infeasible branch and retry with Clarabel when the
    SLSQP solution lacks a sufficiently tight numerical lower bound.
    """
    if np.max(constraint_matrix @ initial - constraint_limits) > CONSTRAINT_TOLERANCE:
        feasibility = linprog(
            np.zeros(len(weights)),
            A_ub=constraint_matrix,
            b_ub=constraint_limits,
            bounds=(None, None),
            method="highs",
        )
        if feasibility.status == LP_INFEASIBLE_STATUS:
            return None
        if not feasibility.success:
            raise RuntimeError(f"Feasibility LP failed ({feasibility.message}).")
        initial = feasibility.x

    candidate = minimize(
        lambda reductions: reductions @ weights @ reductions,
        initial,
        jac=lambda reductions: 2 * weights @ reductions,
        method="SLSQP",
        constraints={
            "type": "ineq",
            "fun": lambda reductions: constraint_limits - constraint_matrix @ reductions,
            "jac": lambda reductions: -constraint_matrix,
        },
        options={"ftol": SLSQP_OBJECTIVE_TOLERANCE, "maxiter": SLSQP_MAX_ITERATIONS},
    )
    reductions = candidate.x
    slack = constraint_limits - constraint_matrix @ reductions
    fallback_reason = f"SLSQP status ({candidate.message})"
    if candidate.success:
        fallback_reason = "SLSQP constraint residual exceeded tolerance"
        if np.min(slack) >= -CONSTRAINT_TOLERANCE:
            multipliers = np.zeros(len(constraint_limits))
            active = slack < ACTIVE_CONSTRAINT_TOLERANCE
            try:
                if active.any():
                    multipliers[active], _ = nnls(
                        constraint_matrix[active].T,
                        -2 * weights @ reductions,
                        maxiter=NNLS_MAX_ITERATIONS,
                    )
            except RuntimeError as error:
                fallback_reason = f"Unable to estimate SLSQP dual multipliers ({error})"
            else:
                objective = float(reductions @ weights @ reductions)
                lower_bound = dual_objective_lower_bound(
                    weights, constraint_matrix, constraint_limits, multipliers
                )
                gap = abs(objective - lower_bound)
                if gap <= SLSQP_GAP_TOLERANCE * max(1.0, objective):
                    return QuadraticSolution(reductions, objective, lower_bound)
                fallback_reason = f"SLSQP dual gap exceeded tolerance ({gap:.3g})"

    try:
        reductions, multipliers = solve_with_clarabel(weights, constraint_matrix, constraint_limits)
    except RuntimeError as error:
        raise RuntimeError(f"{fallback_reason}. {error}") from error
    objective = float(reductions @ weights @ reductions)
    lower_bound = dual_objective_lower_bound(
        weights, constraint_matrix, constraint_limits, multipliers
    )
    residual = float(np.max(constraint_matrix @ reductions - constraint_limits))
    gap = abs(objective - lower_bound)
    if (
        not np.isfinite([objective, lower_bound, residual]).all()
        or residual > CONSTRAINT_TOLERANCE
        or gap > VERIFIED_GAP_TOLERANCE * max(1.0, objective)
    ):
        raise RuntimeError(
            f"{fallback_reason}. Clarabel verification failed "
            f"(residual={residual:.3g}, dual gap={gap:.3g})."
        )
    return QuadraticSolution(reductions, objective, lower_bound)


def build_stage_constraints(
    weighted_vertices: FloatArray, target: float, branch_index: int
) -> tuple[FloatArray, FloatArray]:
    """Build the stage inequalities when the selected vertex enforces the target."""
    input_count = weighted_vertices.shape[1]
    vertex_totals = weighted_vertices.sum(axis=1)
    constraint_matrix = np.vstack(
        [
            weighted_vertices,
            -weighted_vertices[branch_index : branch_index + 1],
            -np.eye(input_count),
            np.eye(input_count),
        ]
    )
    constraint_limits = np.r_[
        vertex_totals - 1.0,
        1.0 / target - vertex_totals[branch_index],
        np.zeros(input_count),
        np.full(input_count, 1.0 - MIN_INPUT_FRACTION),
    ]
    return constraint_matrix, constraint_limits


def radial_path(initial_efficiency: float, targets: FloatArray, input_count: int) -> FloatArray:
    """Reduce all inputs at the same rate at each efficiency target."""
    rates = 1.0 - initial_efficiency / targets
    return np.repeat(rates[:, None], input_count, axis=1)


def solve_single_stage(
    weighted_vertices: FloatArray, target: float
) -> tuple[FloatArray, dict[int, QuadraticSolution]]:
    """Return the best reduction for one target and the feasible vertex branches."""
    initial_efficiency = 1.0 / weighted_vertices.sum(axis=1).min()
    input_count = weighted_vertices.shape[1]
    start = np.full(input_count, 1.0 - initial_efficiency / target)
    weights = np.eye(input_count)
    feasible_branches: dict[int, QuadraticSolution] = {}
    for branch_index in range(len(weighted_vertices)):
        matrix, limits = build_stage_constraints(weighted_vertices, target, branch_index)
        solution = solve_convex_qp(weights, matrix, limits, start)
        if solution is not None:
            feasible_branches[branch_index] = solution

    if not feasible_branches:
        raise RuntimeError(f"No feasible improvement branch for target {target:.6f}.")
    best = min(feasible_branches.values(), key=lambda solution: solution.objective)
    return best.reductions, feasible_branches


def solve_monotone_path(
    weighted_vertices: FloatArray,
    targets: FloatArray,
    stage_branches: list[dict[int, QuadraticSolution]],
) -> FloatArray:
    """Solve all stages with nondecreasing reductions by pruning vertex combinations."""
    stage_count = len(targets)
    input_count = weighted_vertices.shape[1]
    variable_count = stage_count * input_count
    initial_efficiency = 1.0 / weighted_vertices.sum(axis=1).min()
    best_path = radial_path(initial_efficiency, targets, input_count)
    best_objective = float(np.square(best_path).sum())

    monotone_constraints = np.zeros(((stage_count - 1) * input_count, variable_count))
    identity = np.eye(input_count)
    for stage in range(stage_count - 1):
        current = slice(stage * input_count, (stage + 1) * input_count)
        following = slice((stage + 1) * input_count, (stage + 2) * input_count)
        monotone_constraints[current, current] = identity
        monotone_constraints[current, following] = -identity

    ranked: list[tuple[float, tuple[int, ...]]] = []
    for vertex_indices in product(*stage_branches):
        lower_bound = sum(
            branches[index].lower_bound for branches, index in zip(stage_branches, vertex_indices)
        )
        ranked.append((lower_bound, vertex_indices))
    ranked.sort()

    weights = np.eye(variable_count)
    monotone_limits = np.zeros(len(monotone_constraints))
    for lower_bound, vertex_indices in ranked:
        if lower_bound >= best_objective - PRUNING_TOLERANCE:
            break

        stage_matrices, stage_limits = zip(
            *[
                build_stage_constraints(weighted_vertices, target, index)
                for target, index in zip(targets, vertex_indices)
            ]
        )
        matrix = np.vstack([block_diag(*stage_matrices), monotone_constraints])
        limits = np.concatenate([*stage_limits, monotone_limits])
        start = np.concatenate(
            [branches[index].reductions for branches, index in zip(stage_branches, vertex_indices)]
        )
        solution = solve_convex_qp(weights, matrix, limits, start)
        if solution is not None and solution.objective < best_objective:
            best_objective = solution.objective
            best_path = solution.reductions.reshape(stage_count, input_count)

    return best_path
