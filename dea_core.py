"""Independent implementation of the formulations in proposals 1 and 2.

No existing evaluator is imported or modified. Data are read without rewriting.
Finite vertex enumeration is intended for the supplied 2/3 input, one-output cases.
"""
from __future__ import annotations
import itertools
import numpy as np
from scipy.optimize import linprog, minimize, nnls
from scipy.linalg import block_diag
from scipy import sparse

EPS = 1e-6
TOL = 2e-7


def vertices(A):
    n, d = A.shape
    C = np.vstack([A, np.eye(d)])
    b = np.r_[np.ones(n), np.zeros(d)]
    found = {}
    combs = iter(itertools.combinations(range(n + d), d))
    while batch := list(itertools.islice(combs, 4000)):
        ix = np.asarray(batch)
        M = C[ix]
        ok = np.abs(np.linalg.det(M)) > 1e-11
        if not ok.any():
            continue
        P = np.linalg.solve(M[ok], b[ix[ok]][..., None])[..., 0]
        good = np.min(C @ P.T - b[:, None], axis=0) >= -1e-8
        for p in P[good]:
            p[np.abs(p) < 1e-10] = 0
            found[tuple(np.round(p, 9))] = p
    return np.array([found[k] for k in sorted(found)])


def efficiency_primal(X, Y, x, y):
    """Input-oriented CCR LP, independent of enumerated dual vertices."""
    X, Y = np.asarray(X), np.asarray(Y)
    if Y.ndim == 1:
        Y = Y[:, None]
    y = np.atleast_1d(y)
    sx, sy = X.max(axis=0), Y.max(axis=0)
    Xs, Ys, xs, ys = X / sx, Y / sy, x / sx, y / sy
    n, d = X.shape
    G = np.vstack([np.column_stack([-xs, Xs.T]),
                   np.column_stack([np.zeros(Y.shape[1]), -Ys.T])])
    b = np.r_[np.zeros(d), -ys]
    sol = linprog(np.r_[1., np.zeros(n)], A_ub=G, b_ub=b,
                  bounds=(0, None), method='highs')
    if not sol.success:
        raise RuntimeError(sol.message)
    return float(sol.fun)


def quadratic(W, G, b, initial=None, force_clarabel=False):
    """min x'Wx s.t. Gx<=b, with a feasible dual lower bound."""
    dim = len(W)
    if initial is None or np.max(G @ initial - b) > TOL:
        lp = linprog(np.zeros(dim), A_ub=G, b_ub=b,
                     bounds=[(None, None)] * dim, method='highs')
        if lp.status == 2:
            return None
        if not lp.success:
            raise RuntimeError(lp.message)
        initial = lp.x
    result = minimize(lambda x: x @ W @ x, initial,
                      jac=lambda x: 2 * W @ x, method='SLSQP',
                      constraints={'type': 'ineq', 'fun': lambda x: b - G @ x,
                                   'jac': lambda x: -G},
                      options={'ftol': 1e-12, 'maxiter': 700})
    x = result.x
    active = b - G @ x < 1e-6
    lam = np.zeros(len(b))
    if active.any():
        try:
            lam[active] = nnls(G[active].T, -2 * W @ x, maxiter=5000)[0]
        except RuntimeError:
            pass
    def lower_bound(lam):
        lam = np.maximum(lam, 0)
        v = G.T @ lam
        return float(-0.25 * v @ np.linalg.solve(W, v) - b @ lam)
    lb = lower_bound(lam)
    gap = float(x @ W @ x - lb)
    if (force_clarabel or not result.success or np.max(G @ x - b) > TOL
            or gap > 2e-8 * max(1., x @ W @ x)):
        import clarabel
        settings = clarabel.DefaultSettings()
        settings.verbose = False
        settings.tol_gap_abs = 1e-11
        settings.tol_gap_rel = 1e-11
        settings.tol_feas = 1e-11
        settings.max_iter = 300
        solver = clarabel.DefaultSolver(sparse.csc_matrix(np.triu(2 * W)),
                    np.zeros(dim), sparse.csc_matrix(G), b,
                    [clarabel.NonnegativeConeT(len(b))], settings)
        sol = solver.solve()
        if str(sol.status) not in ('Solved', 'AlmostSolved'):
            raise RuntimeError(f'Clarabel failed: {sol.status}')
        x = np.array(sol.x)
        lb = lower_bound(np.array(sol.z))
    primal = float(x @ W @ x)
    residual = float(max(0., np.max(G @ x - b)))
    if residual > TOL or primal - lb > 2e-7 * max(1., primal):
        raise RuntimeError(f'QP verification failed: residual={residual}, gap={primal-lb}')
    return {'x': x, 'fun': primal, 'lb': lb, 'residual': residual,
            'gap': max(0., primal - lb)}


def constraints(B, tau, h):
    d = B.shape[1]
    return (np.vstack([B, -B[h:h+1], -np.eye(d), np.eye(d)]),
            np.r_[B.sum(axis=1) - 1., 1./tau - B[h].sum(),
                  np.zeros(d), np.full(d, 1. - EPS)])


def single(B, tau, W=None, force_clarabel=False):
    W = np.eye(B.shape[1]) if W is None else W
    initial = np.full(B.shape[1], 1. - 1. / (B.sum(axis=1).min() * tau))
    solutions = []
    for h in range(len(B)):
        G, b = constraints(B, tau, h)
        q = quadratic(W, G, b, initial, force_clarabel)
        if q is not None:
            q['h'] = h
        solutions.append(q)
    good = [s for s in solutions if s is not None]
    if not good:
        raise RuntimeError('No feasible branch')
    best = min(good, key=lambda s: s['fun']).copy()
    best['global_lb'] = min(s['lb'] for s in good)
    return best, solutions


def joint(B, taus, independent, branch_solutions, common=False):
    T, d, H = len(taus), B.shape[1], len(B)
    e0 = 1. / B.sum(axis=1).min()
    radial = np.array([np.full(d, 1 - e0/t) for t in taus])
    best = {'x': radial.ravel(), 'fun': float(np.sum(radial**2)),
            'gap': 0., 'residual': 0., 'h': None}
    mono = np.zeros(((T-1)*d, T*d))
    for t in range(T-1):
        mono[t*d:(t+1)*d, t*d:(t+1)*d] = np.eye(d)
        mono[t*d:(t+1)*d, (t+1)*d:(t+2)*d] = -np.eye(d)
    combos = ([tuple([h]*T) for h in range(H)] if common
              else itertools.product(range(H), repeat=T))
    ranked = []
    for hs in combos:
        ss = [branch_solutions[t][h] for t, h in enumerate(hs)]
        if any(s is None for s in ss):
            continue
        ranked.append((sum(s['lb'] for s in ss), hs))
    ranked.sort()
    solved, certs = 0, []
    for lb, hs in ranked:
        if lb >= best['fun'] - 1e-10:
            certs.append(lb)
            break  # all remaining certified lower bounds are at least this large
        cons = [constraints(B, tau, h) for tau,h in zip(taus,hs)]
        G = np.vstack([block_diag(*[c[0] for c in cons]), mono])
        b = np.r_[np.concatenate([c[1] for c in cons]), np.zeros((T-1)*d)]
        initial = np.concatenate([branch_solutions[t][h]['x'] for t,h in enumerate(hs)])
        sol = quadratic(np.eye(T*d), G, b, initial)
        solved += 1
        if sol is None:
            continue
        certs.append(sol['lb'])
        if sol['fun'] < best['fun']:
            best = dict(sol, h=hs)
    best['global_lb'] = min(certs) if certs else best['fun']
    best['global_gap'] = max(0., best['fun'] - best['global_lb'])
    best['solved_qps'] = solved
    best['x'] = best['x'].reshape(T,d)
    return best


def grid_ray(B, taus):
    d = B.shape[1]
    assert d == 3
    directions = [np.array([i,j,20-i-j])/20 for i in range(21) for j in range(21-i)]
    directions.append(np.ones(d)/d)
    best = None
    for u in directions:
        intercept, slope = B.sum(axis=1), B @ u
        path = []
        for tau in taus:
            positive = slope > 1e-12
            a = np.min((intercept[positive] - 1/tau)/slope[positive])
            path.append(a*u)
        path = np.array(path)
        if (path.min() < -TOL or path.max() > 1-EPS+TOL or
                min(np.min(B @ (1-r)) for r in path) < 1-TOL):
            continue
        value = float(np.sum(path**2))
        if best is None or value < best['fun']:
            best = {'x': path, 'fun': value, 'direction': u}
    if best is None:
        raise RuntimeError('No feasible grid ray')
    return best
