# 1株配当の長期履歴(10年前後)を作る

`index.html` の `CODE_INFO_MAP[code][3]` は、1株配当を新しい順に並べた配列。
今は直近の有価証券報告書1本から最大3期分しか入っていない。これを10〜15期に延ばす。
画面側(`dividendStreak`)は配列の長さに合わせて判定するので、データを差し替えるだけで
「◯期連続増配」が延びる。

## 必要なもの

- ネットワーク: `api.edinet-fsa.go.jp` への接続許可(クラウド環境の設定)
- APIキー: 環境変数 `EDINET_API_KEY`(EDINET API v2 の Subscription-Key)

## 方針

- 有報の「主要な経営指標等の推移」には5期分の1株配当が載る。
  2026年・2021年・2016年ごろ提出の有報を1社3本ずつ取れば、約15期分をつなげられる
  (約3,900社 × 3本 ≒ 1.2万件)。
- 書類一覧: `GET /api/v2/documents.json?date=YYYY-MM-DD&type=2&Subscription-Key=…`
  を日付ごとに回し、`docTypeCode == "120"`(有価証券報告書)を集める。
  3月決算の提出が集中する6月下旬を中心に、各年の全期間を回す。
- 本文: `GET /api/v2/documents/{docID}?type=5`(XBRLをCSVにしたzip)。
  経営指標の1株配当(`DividendPaidPerShareSummaryOfBusinessResults`)と
  発行済株式総数(`TotalNumberOfIssuedSharesSummaryOfBusinessResults`)を、
  `CurrentYearDuration` 〜 `Prior4YearDuration` の各コンテキスト(個別)から読む。
  要素名・コンテキスト名は実データで要確認。

## 年をつなぐときの注意(既存の取り込みと同じ扱い)

- 株式分割: 発行済株式数の比を、きりのいい倍率(1.5, 2, 3, 5, 10…)に寄せて割り戻す。
- 期の途中の分割でその年度が分割前後の混在になる場合は、その期を捨てる。
- 前年比が −40% より大きく減る、または3倍を超えて増える年があれば、それより古い期は捨てる
  (上場前の年度や株式併合の混入)。
- 2本の有報で重なる期の値が食い違うときは、新しい有報の値を採る。

## 出典表示

EDINET(公共データ利用規約 PDL1.0)。フッターの出典と加工の明示は既存のままでよい。
