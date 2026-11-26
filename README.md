# DEAによる段階的な改善計画

DEA（データ包絡分析法）は、人員・設備・費用などの資源と、そこから得られる成果を使って、複数の組織や事業体の相対的な効率と改善余地を見積もる手法です。このプロジェクトでは、成果の量を保ちながら、効率目標を3段階で達成する計画をPythonで比較します。

## 課題と結果

各段階を別々に最適化すると、たとえば第1段階で当初より10%減らしたエネルギー支出を、第2段階では当初比5%減まで増やす計画が選ばれます。この場合、第1段階の削減を5ポイント取り消す必要があります。そこで、各項目の累積削減率が段階を追って下がらないように制約を設け、全段階を同時に最適化しました（Nested）。

病院の効率分析を背景とする研究です。病院分析で使ったデータの共有範囲に配慮し、公開用の数値実験にはデンマークの酪農事業体108件の公開データを使いました。エネルギー支出・獣医費・乳牛頭数を入力、牛乳生産量を出力とし、初期効率が1未満の97件を評価しました。各事業体の目標は、効率1までの差を25%、60%、100%埋める3段階です。 [データの出典（CRAN）](https://search.r-project.org/CRAN/refmans/Benchmarking/html/milkProd.html)

| 計画の決め方 | 削減を取り消す事業体数 | 変更量 $J$ の平均増加率（対Independent） |
| --- | ---: | ---: |
| 段階ごとに独立して最適化（Independent） | 20 / 97件 | 0%（基準） |
| 3段階を同時に最適化（Nested） | 0 / 97件 | +0.14% |
| 各段階ですべての入力を同じ割合で削減（Radial） | 0 / 97件 | +149.84% |

**この実験では、削減の取り消しを20件から0件にしながら、変更量を表す目的値 $J$ の増加は平均0.14%、最大2.17%に収まりました。** $J$ は各項目・各段階の累積削減率を二乗して合計した値です。基準比は事業体ごとにIndependentに対する増加率を求め、97件で平均しています。

## 実装上の工夫

- **最適性の数値検証。** 二次計画で得た候補の目的値と双対下界を照合します。SLSQPが収束しない場合や、制約残差・双対ギャップが許容範囲を超える場合は、Clarabelで解き直します。双対変数の推定に失敗した場合も、この経路で再計算します。
- **双対下界による枝刈り。** 段階を結ぶ制約を緩めて得た各段階の下界を合計し、その枝全体の下界にします。すでに得た計画の目的値を改善できない枝は、二次計画を解く前に除外します。
- **別の定式化で効率を再評価。** 改善後の入力を入力指向CCRの主問題に入れ、HiGHSで各段階の効率を再計算します。目標達成と、Nestedで削減が取り消されていないことを確認します。

実験の流れと集計は[実験スクリプト](run_dea_experiment.py)、最適化とCCRの計算は[計算モジュール](dea_core.py)にあります。

## 定式化とコードの対応

初期入力を $x^0$、固定する出力を $y^0$、段階 $t$ の累積削減率ベクトルを $r^t$ とすると、変更後の入力は $x^t=x^0\odot(\mathbf{1}-r^t)$ です。$\odot$ は要素ごとの積です。Nestedでは入力指向CCRの効率値 $E$ を使い、次の問題を解きます。

$$
\begin{aligned}
&\min_{r^1,\ldots,r^T} J = \sum_{t=1}^{T}\|r^t\|_2^2 \\
&\text{subject to}\quad
\mathbf{0}\le r^1\le\cdots\le r^T\le(1-\varepsilon)\mathbf{1},\\
&\hphantom{\text{subject to}\quad}
\tau_t \le E(x^t;y^0)\le1\qquad(t=1,\ldots,T).
\end{aligned}
$$

1出力のCCRでは、双対の実行可能領域 $v\ge0,\ (x_i/y_i)^\top v\ge1$ の頂点 $v_h$ を使うと、効率を $E(x^t;y^0)=1/\min_h[B_h(\mathbf{1}-r^t)]$ と表せます。ここで $B_{hj}=v_{hj}x_j^0/y^0$ です。効率が1以下になるには全頂点で $B_h(\mathbf{1}-r^t)\ge1$ が必要です。目標効率以上になるには、少なくとも1つの頂点で $B_h(\mathbf{1}-r^t)\le1/\tau_t$ が必要です。この頂点を選ぶごとに線形制約付きの凸二次計画になります。

| 記号 | コード | 意味 |
| --- | --- | --- |
| $B$ | `weighted_vertices` | 双対頂点の係数に評価対象の初期入力・出力を反映した行列 |
| $h$ | `branch_index` | 目標効率を満たすために選んだ双対頂点の行番号 |
| $\tau_t$ | `target` / `targets` | 各段階で達成する効率値 |
| $r^t$ | `reductions` | 初期状態からの累積削減率 |
| $W$ | `weights` | 二次計画の目的 $r^\top W r$ の重み行列。この実験では単位行列 |

入力が $d$ 項目、事業体が $n$ 件の場合、頂点列挙では最大 $\binom{n+d}{d}$ 通りの制約の組み合わせを調べます。頂点数が $H$、段階数が $T$ のとき、段階をつなぐ候補は枝刈り前で最大 $H^T$ 通りです。実装の主な検証範囲は3入力・1出力・3段階です。

## 実行方法

Python 3.13を使用します。リポジトリのルートで以下を実行します。手元のmacOS（Apple Silicon）で、全108件の計算に約10秒かかりました。小さな行列演算を多数繰り返すため、BLASとOpenMPのスレッド数を1に設定して並列化のオーバーヘッドを抑えています。

### macOS / Linux

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
curl -fL -o milkProd.csv.gz https://raw.githubusercontent.com/cran/Benchmarking/master/data/milkProd.csv.gz
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python run_dea_experiment.py milkProd.csv.gz
```

### Windows（PowerShell）

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/cran/Benchmarking/master/data/milkProd.csv.gz' -OutFile 'milkProd.csv.gz'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
.\.venv\Scripts\python.exe run_dea_experiment.py milkProd.csv.gz
```

### 出力例

集計結果を標準出力にJSONで表示します。以下は `Nested` の行を抜粋し、小数を丸めた例です。

```json
{
  "producer_count": 108,
  "evaluated_producers": 97,
  "max_target_shortfall": 1.02e-13,
  "methods": {
    "Nested": {
      "mean_objective": 0.087347,
      "mean_increase_percent": 0.143474,
      "max_increase_percent": 2.167485,
      "reversal_count": 0
    }
  }
}
```

| 出力項目 | 意味 |
| --- | --- |
| `producer_count` / `evaluated_producers` | 比較に使った総事業体数と、段階的な改善計画を計算した対象数 |
| `max_target_shortfall` | 全方式・全段階での、再評価効率が目標を下回った幅の最大値。許容誤差は $10^{-6}$ |
| `mean_objective` | 各事業体の $J$ の平均 |
| `mean_increase_percent` / `max_increase_percent` | 事業体ごとの基準比 $(J/J_{\mathrm{Independent}}-1)\times100$ の平均と最大 |
| `reversal_count` | 前段階から累積削減率が下がった項目・段階の減少幅合計が $10^{-6}$ を超えた事業体数 |

## テスト

依存パッケージをインストールした仮想環境の Python で `-m unittest discover -s tests -v` を実行します。人工データで、CCRの主問題と双対頂点での効率の一致、二次計画の解析解と双対下界、Clarabelへの切り替え、実行不能な枝、枝刈りあり・なしの結果の一致、CSVの読み込みを検証します。

## コードの利用

コードの著作権は著作権者に帰属します。GitHub上での閲覧とフォークにはGitHub利用規約が適用されます。法令や利用規約で認められる範囲を超える再配布や他のプロジェクトでの利用には、権利者の許諾が必要です。 [GitHubのライセンス案内](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)
