# 競馬予想ツール(機械学習・たたき台)

過去のレース結果CSVから、各馬の1着確率をレースごとに出す。配当ダッシュボード本体とは独立。

```bash
pip install -r requirements.txt
python make_sample_data.py data/sample.csv     # 架空データ(動作確認用)
python train.py data/sample.csv [--use-odds]   # 学習+評価(新しい期間をテストに)
python predict.py data/sample.csv --race R01499
```

## 画面で見る
```bash
python predict.py data/sample.csv --last 12 --json predictions.json   # 出走表の予想なら --json だけ
python -m http.server 8000     # → http://localhost:8000/ を開く
```
`index.html` が同じ場所の `predictions.json`(なければ `sample_predictions.json`)を読みます。「予想JSONを開く」で任意のファイルも読めます。

## 実データを取り込む
```bash
python import_csv.py raw.csv data/real.csv          # 列名を自動で対応づけ(cp932も可)
python import_csv.py raw.csv data/real.csv --map "date=開催日,finish=着順"   # 手で指定
python train.py data/real.csv --use-odds
```

## CSVの列
必須: `race_id,date,horse_id,jockey,frame,age,sex,weight_carried,body_weight,distance,surface,going`
任意: `horse_name,odds`(あると期待値を出す)、`finish`(着順。予想したいレースは空欄)

予想するときは、過去結果のCSVの末尾に出走表(finish空欄)を足して渡す。

## 注意
- サンプルは架空データなので、出る的中率・回収率に意味はない。実データで必ず検証する。
- 過去成績は「そのレースより前」だけで集計している(未来の情報の混入を防ぐ)。
- 回収率は控除率(約20〜25%)があるため、100%超えは簡単には出ない。
- 実データの入手(利用規約に沿った形)は未決定。
