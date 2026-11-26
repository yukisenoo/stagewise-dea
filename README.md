# DEAによる段階的な改善計画

データ包絡分析法（DEA）の効率目標を段階的に達成するための、大学院研究のPython実験です。

## 現在の研究｜段階的な改善計画（研究案②）

効率目標ごとに変更量が最小となる案を別々に選ぶと、次の目標へ進む際に、前の段階で減らした資源を再び増やす必要が生じることがあります。そこで、各資源の累積削減率が段階を追って下がらないように制約を設け、3段階の改善計画を同時に求める方法（Nested）を検討しました。Pythonで最適化を実装し、各段階の計画が目標効率を満たすことをDEAで再評価しました。

### 数値実験の結果

デンマークの酪農事業体108件の公開データを用い、初期効率が1未満の97件で比較しました。各事業体について、効率1までの差を25%、60%、100%埋める3つの目標を設定しました。 [データの出典（CRAN）](https://search.r-project.org/CRAN/refmans/Benchmarking/html/milkProd.html)

| 改善計画の決め方 | 削減の取り消しが生じた事業体 | 変更量の指標の平均増加率 |
| --- | ---: | ---: |
| 各目標を別々に最適化 | 20 / 97件 | 基準 |
| 取り消しを制約して3段階を同時に最適化（Nested） | 0 / 97件 | +0.14% |
| 段階ごとに全資源を同じ割合で削減 | 0 / 97件 | +149.84% |

変更量の指標は、初期状態からの累積削減率を各項目・各段階で二乗して足し合わせた値です。表では、各事業体の基準案に対する増加率を平均しています。Nestedでの増加率は最大2.17%でした。

## 実行方法

[実験スクリプト](run_dea_experiment.py)は、3方式の集計結果をJSONで標準出力に表示します。[DEAの計算処理](dea_core.py)では、線形計画で各段階の効率値を再計算します。Python 3.13で動作を確認しました。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
curl -fL -o milkProd.csv.gz https://raw.githubusercontent.com/cran/Benchmarking/master/data/milkProd.csv.gz
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python run_dea_experiment.py milkProd.csv.gz
```

`evaluated_producers`は評価対象数、`reversal_count`は削減の取り消しが生じた事業体数です。`mean_increase_percent`は累積削減率の二乗和で測った変更量の平均増加率を表します。
