# DEAによる段階的な改善計画

**後の段階の効率目標も達成するには、最初の段階でどの資源をどれだけ見直せばよいか？**

## 1事業体の改善計画

公開の酪農データ `milkProd` に含まれる事業体80で、牛乳生産量を保ちながら、同じ3段階の目標に対する計画を比べました。初期効率は0.7384です。表の百分率は初期値からの累積削減率です。計画全体の変更量 $J$ は、全入力・全段階の削減率を小数で表し、二乗して合計した単位のない指標です。金銭的な費用を表すものではありません。

| 段階（目標効率） | 項目 | 段階ごとに個別最適化 | 全段階を同時に最適化 |
| --- | --- | ---: | ---: |
| 第1段階（0.8038） | エネルギー支出 | 9.64% | 0.00% |
|  | 獣医費 | 8.37% | 0.00% |
|  | 乳牛頭数 | 3.80% | 14.65% |
| 第2段階（0.8954） | エネルギー支出 | 0.00% | 0.00% |
|  | 獣医費 | 0.00% | 0.00% |
|  | 乳牛頭数 | 23.37% | 23.37% |
| 第3段階（1.0000） | エネルギー支出 | 0.00% | 0.00% |
|  | 獣医費 | 0.00% | 0.00% |
|  | 乳牛頭数 | 31.39% | 31.39% |
| 計画全体 | 変更量 $J$ | 0.17090 | 0.17461 |

個別最適化では、第1段階で減らしたエネルギー支出と獣医費を、第2段階で元の水準に戻します。同時最適化では、第1段階から乳牛頭数に変更を集中させ、その削減を段階ごとに積み上げます。両方式とも3段階すべての目標に達し、この事業体では同時最適化によって $J$ が2.17%増えました。 [この例をPythonで再現する](docs/model.md#1事業体の計画を再現する)

初期の計画の違いを示すため、97件中で $J$ の増加率が最大の事業体を選びました。全97件の平均増加率は0.14%です。頭数も連続量として扱うモデル上の計画で、各段階を特定の年には対応させていません。[計算結果のJSON](results/producer80.json)には、初期入力、丸め前の削減率、変更後の入力、CCRによる効率の再評価を収録しています。

DEA（データ包絡分析法）は、人員・設備・費用などの資源と、そこから得られる成果を使って、複数の組織や事業体の相対的な効率と改善余地を見積もる手法です。このプロジェクトでは、成果の量を保ちながら、効率目標を3段階で達成する計画をPythonで比較します。

[課題と結果](#課題と結果) · [最小の実行例](#最小の実行例) · [ディレクトリ構成](#ディレクトリ構成) · [実行方法](#実行方法) · [定式化](docs/model.md)

## 研究背景

日本医師会総合政策研究機構の調査では、有効回答1,211病院のうち、2024年度に経常赤字だった病院は62.2%でした。必要な医療を提供し続けるには、限られた人員や病床をどう活用するかが課題になります。 [令和7年 病院の緊急経営調査（図表2-5）](https://www.jmari.med.or.jp/wp-content/uploads/2025/10/WP496.pdf)

研究の出発点は、医師数・看護職員数・病床数を投入資源、1日平均の入院・外来患者数を医療サービス量の指標として、病院間の相対的な効率を比較したDEA分析です。この経験から、見つけた改善余地に対して、どの資源をどの段階で見直すかを考える改善計画に取り組んでいます。

## 課題と結果

個別最適化（Independent）では、後の段階で一部の削減を取り消す計画が選ばれることがあります。同時最適化（Nested）では、各入力の累積削減率が段階を追って下がらないように制約を設け、3段階をまとめて最適化します。

公開の酪農データを用い、初期効率が1未満の97事業体で3方式を比較しました。変更量を測る指標 $J$ は、各入力・各段階の累積削減率を二乗して合計した値です。表の増加率は、事業体ごとにIndependentを基準として計算し、97件で平均しています。

| 方式 | 計画の決め方 | 削減の取り消しが発生した事業体 | $J$ の平均増加率 |
| --- | --- | ---: | ---: |
| Independent | 段階ごとに独立して最適化 | 20 / 97件 | 0%（基準） |
| Nested | 削減の取り消しを制限し、全段階を同時に最適化 | 0 / 97件 | +0.14% |
| Radial | 段階ごとに全入力を同じ割合で削減 | 0 / 97件 | +149.84% |

**Nestedでは取り消しが発生した事業体が20件から0件になり、目的値 $J$ の増加は平均0.14%、最大2.17%でした。**

## ディレクトリ構成

```text
.
├── README.md              # 研究概要、実験結果、再現手順
├── run_dea_experiment.py  # 入力の読み込み、3方式の比較、JSON出力
├── dea_core.py            # CCR効率の計算と改善計画の最適化
├── requirements.txt       # 実行に必要なPythonパッケージ
├── examples/
│   └── compare_plans.py   # 1事業体の初期値と目標から2方式の計画を比較
├── results/
│   └── producer80.json    # 冒頭の事業体80の計算結果
├── docs/
│   └── model.md           # 数式とコードの対応、計算規模の限界
├── tests/
│   ├── test_dea.py        # 最適化、再評価、gzip読み込みのテスト
│   └── test_example.py    # 1事業体の計画と目標値の検証
└── .gitignore             # 仮想環境とダウンロードしたデータの除外設定
```

実験コードの入口は [run_dea_experiment.py](run_dea_experiment.py) です。[dea_core.py](dea_core.py) が各方式の改善計画とCCR効率値を求め、実験スクリプトが結果を集計します。

### 説明・実装・出力の対応

| 確かめたいこと | 説明 | 実行するコード | 得られる出力 |
| --- | --- | --- | --- |
| 全段階を考えると、最初の計画はどう変わるか | [1事業体の改善計画](#1事業体の改善計画) | [examples/compare_plans.py](examples/compare_plans.py) | 入力別・段階別の削減率、再評価した効率、$J$（[保存例](results/producer80.json)） |
| 取り消しを防ぐと、全体の変更量はどれだけ増えるか | [課題と結果](#課題と結果) | [run_dea_experiment.py](run_dea_experiment.py) | 97件での取り消し件数、$J$ の平均・最大増加率のJSON |
| 目標達成や求解結果をどう確かめるか | [定式化](docs/model.md)・[実装上の工夫](#実装上の工夫) | [tests/](tests/) | CCR再評価、下界、枝刈りなどのテスト結果 |

## 入力データ

病院分析で使ったデータの共有範囲に配慮し、再現実験にはデンマークの酪農事業体108件の公開データ `milkProd` を使います。実験スクリプトは、セミコロン区切りのCSVまたはgzip圧縮したCSVを読み込みます。 [データの出典（CRAN）](https://search.r-project.org/CRAN/refmans/Benchmarking/html/milkProd.html)

| データの役割 | CSV列 | 指標 |
| --- | --- | --- |
| 入力 | `energy` | エネルギー支出 |
| 入力 | `vet` | 獣医費 |
| 入力 | `cows` | 乳牛頭数 |
| 出力 | `milk` | 牛乳生産量（kg） |

頭数を含む全入力を連続量として扱い、改善の方向と規模を比較しました。各事業体の目標は、効率1までの差を25%、60%、100%埋める3段階です。

## 最小の実行例

[環境の準備とデータ取得](#実行方法)の後、次のコードで冒頭の事業体80の計画を求められます。DEAでは比較対象から効率の基準を作るため、1事業体の初期値に加えて、参照用の108事業体のデータも渡します。

```python
from pathlib import Path
from examples.compare_plans import compare_plans
from run_dea_experiment import load_data

inputs, outputs = load_data(Path("milkProd.csv.gz"))
plan = compare_plans(
    inputs, outputs,
    initial_inputs=[93166, 23293, 90],  # energy, vet, cows
    initial_output=573431,            # milk（kg）を固定
)
print(plan["targets"])
print(plan["methods"]["Nested"]["cumulative_reductions"])
```

目標を省略すると、効率1までの差を25%、60%、100%埋める3段階を設定します。任意の目標を比較する場合は、例えば `targets=[0.80, 0.90, 1.00]` を追加します。返る削減率は割合なので、`0.14645` は約14.65%の削減です。

冒頭と同じ条件の全結果をJSONで表示するコマンドは次のとおりです。`--farm-no` にはCSVの `farmNo` を指定します。

```sh
.venv/bin/python -m examples.compare_plans milkProd.csv.gz --farm-no 80
```

Windows（PowerShell）では次のコマンドを使います。

```powershell
.\.venv\Scripts\python.exe -m examples.compare_plans milkProd.csv.gz --farm-no 80
```

| 1事業体の出力項目 | 意味 |
| --- | --- |
| `initial_inputs` / `fixed_output` | 初期入力 / 全段階で保つ出力 |
| `initial_efficiency` / `targets` | 初期効率 / 各段階の目標効率 |
| `cumulative_reductions` / `planned_inputs` | 各段階・各入力の累積削減率 / 変更後の入力 |
| `achieved_efficiencies` | 変更後の入力をCCRで再評価した各段階の効率 |
| `objective` / `increase_percent` | 計画全体の $J$ / Independentに対する増加率（%） |
| `has_reversal` | 削減の取り消しの合計が許容誤差 $10^{-6}$ を超えたか |

## 実行方法

**必要な環境はPython 3.13です。** リポジトリのルートで、仮想環境の作成、依存パッケージの導入、データの取得、実行を行います。

```sh
git clone https://github.com/yukisenoo/stagewise-dea.git
cd stagewise-dea
```

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

小さな行列演算を多数繰り返すため、BLASとOpenMPのスレッド数を1に設定して並列化の負荷を抑えています。macOS（Apple Silicon）で全108件の処理に約10秒かかりました。

## 出力例

集計結果はJSONとして標準出力に表示されます。以下は `Nested` の結果を抜粋し、表示桁数を丸めた例です。`max_target_shortfall` は浮動小数点計算の誤差により実行環境によって異なります。

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
| `producer_count` / `evaluated_producers` | 比較に使った総事業体数 / 改善計画を計算した対象数 |
| `max_target_shortfall` | 全方式・全段階で再評価した効率が、目標を下回った幅の最大値。許容誤差は $10^{-6}$ |
| `mean_objective` | 事業体ごとに計算した目的値 $J$ の平均 |
| `mean_increase_percent` / `max_increase_percent` | Independentを基準とした $J$ の事業体ごとの増加率の平均 / 最大 |
| `reversal_count` | 累積削減率が前段階より下がった分を項目・段階ごとに合計し、その値が $10^{-6}$ を超えた事業体数 |

## 実装上の工夫

- **双対下界による枝刈り**。段階を結ぶ制約を緩めて得た各段階の下界を合計し、求解済みの計画を改善できない枝を除外します。
- **求解結果の確認とソルバーの切り替え**。SLSQPの目的値と双対下界を照合します。SLSQPが収束しない場合、制約残差や双対ギャップが許容範囲を超えた場合、双対変数を推定できない場合はClarabelで解き直します。
- **CCRによる再評価**。計画で求めた入力を使って、入力指向CCRの主問題をHiGHSで解きます。各段階の目標達成と、Nestedで削減の取り消しが発生しないことを確認します。

[定式化とコードの対応](docs/model.md)に、目的関数、段階間の制約、コード内の変数、計算規模の限界をまとめています。

## テスト

macOS / Linuxでは次のコマンドでテストを実行します。

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Windowsでは `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` を実行します。[最適化のテスト](tests/test_dea.py)では人工データを使い、CCRの主問題と双対頂点の一致、二次計画とその下界、Clarabelへの切り替え、枝刈りあり・なしの一致、gzipデータの読み込みを検証します。[1事業体の実行例のテスト](tests/test_example.py)では、計画の目標達成、削減の取り消し、任意の目標値の受け渡しを確認します。

## コードの利用

閲覧用に公開しています（ライセンスは付与していません）。
