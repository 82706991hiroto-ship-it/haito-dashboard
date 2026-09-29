# 1株配当の長期履歴(EDINET)

`index.html` の `CODE_INFO_MAP[code][3]` は、1株配当を新しい順に並べた配列。
`fetch_history.py` で、有価証券報告書から約13期分(直近の期から12年前まで)に延ばす。
画面側(`dividendStreak`)は配列の長さに合わせて「◯期連続増配」を出す。

## 必要なもの

- ネットワーク: `api.edinet-fsa.go.jp` への接続許可
- APIキー: 環境変数 `EDINET_API_KEY`(EDINET API v2 の Subscription-Key)

## 手順

```sh
C=/tmp/edcache   # 取得結果の置き場(リポジトリには入れない)
python3 tools/edinet/fetch_history.py --cache $C list    # 書類一覧(約1,200営業日、数分)
python3 tools/edinet/fetch_history.py --cache $C fetch   # 有報のCSV(約1万件、45分ほど)
python3 tools/edinet/fetch_history.py --cache $C build --out $C/history.json
python3 tools/edinet/fetch_history.py --cache $C apply --history $C/history.json --html index.html
```

EDINETは提出から約10年で書類を消すため、提出日の範囲(`WINDOWS`)は毎年1年ずつ進める。

## つなぎ方

- 1社につき、最新・期末が4年前・8年前の有報を1本ずつ取る。各有報に5期分の1株配当と発行済株式数が載る。
- 1本の中では、株数の比をきりのいい倍率に寄せ、分割の前後で配当が倍率ぶん下がっていれば割り戻す
  (過去期を修正済みで載せている会社はそのまま)。
- 有報どうしは重なる1期で倍率を合わせる。合わなければ古い有報はつながない。
- 期の途中で分割した年(中間は分割前・期末は分割後の混在。トヨタ148円など)は、
  株数が跳ねた期の近くで40%を超えて下がっていれば、その年より古い期を外す。
- 3倍を超える増配は上場前の年度の混入とみなし、それより古い期を外す。
- `apply` は、既存の値(直近3期)と一致する銘柄だけを延ばす。一致しない銘柄は既存のまま。

2026年9月の実行結果: 2,207銘柄を延長(うち約1,100銘柄が13期)、184銘柄は不一致で据え置き。

## 出典表示

EDINET(公共データ利用規約 PDL1.0)。フッターの出典と加工の明示は既存のままでよい。
