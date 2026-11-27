# 定式化とコードの対応

[READMEに戻る](../README.md) · [計算モジュール](../dea_core.py) · [実験スクリプト](../run_dea_experiment.py)

## 段階的な改善計画

初期入力を $x^0$、固定する出力を $y^0$、段階 $t$ の累積削減率ベクトルを $r^t$ とすると、変更後の入力は $x^t=x^0\odot(\mathbf{1}-r^t)$ です。$\odot$ は要素ごとの積です。入力指向CCRの効率値 $E$ は、同じ出力を保ちながら入力を一律にどこまで縮小できるかを表します。Nestedはこの効率値を使い、次の問題を解きます。

$$
\begin{aligned}
&\min_{r^1,\ldots,r^T} J = \sum_{t=1}^{T}\|r^t\|_2^2 \\
&\text{subject to}\quad
\mathbf{0}\le r^1\le\cdots\le r^T\le(1-\varepsilon)\mathbf{1},\\
&\hphantom{\text{subject to}\quad}
\tau_t \le E(x^t;y^0)\le1\qquad(t=1,\ldots,T).
\end{aligned}
$$

段階間の不等式は入力項目ごとに適用します。変更後の入力を正に保つため、実装では $\varepsilon=10^{-6}$ を使います。

1出力のCCRでは、双対の実行可能領域 $v\ge0,\ (x_i/y_i)^\top v\ge1$ の頂点 $v_h$ を使うと、効率を $E(x^t;y^0)=1/\min_h[B_h(\mathbf{1}-r^t)]$ と表せます。ここで $B_{hj}=v_{hj}x_j^0/y^0$ です。効率が1以下になるには全頂点で $B_h(\mathbf{1}-r^t)\ge1$ が必要です。目標効率以上になるには、少なくとも1つの頂点で $B_h(\mathbf{1}-r^t)\le1/\tau_t$ が必要です。この頂点を選ぶごとに線形制約付きの凸二次計画になります。

| 記号 | コード | 意味 |
| --- | --- | --- |
| $B$ | `weighted_vertices` | 双対頂点の係数に評価対象の初期入力・出力を反映した行列 |
| $h$ | `branch_index` | 目標効率を満たすために選んだ双対頂点の行番号 |
| $\tau_t$ | `target` / `targets` | 各段階で達成する効率値 |
| $r^t$ | `reductions` | 初期状態からの累積削減率 |
| $W$ | `weights` | 二次計画の目的 $r^\top W r$ の重み行列。この実験では単位行列 |

## 計算規模の限界

入力が $d$ 項目、事業体が $n$ 件の場合、頂点列挙では最大 $\binom{n+d}{d}$ 通りの制約の組み合わせを調べます。頂点数が $H$、段階数が $T$ のとき、段階をつなぐ候補は枝刈り前で最大 $H^T$ 通りです。実装の主な検証範囲は3入力・1出力・3段階です。
