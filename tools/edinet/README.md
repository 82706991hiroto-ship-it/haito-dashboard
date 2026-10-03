# 1株配当の長期履歴(EDINET)

`index.html` の `CODE_INFO_MAP[code][3]` は、1株配当を新しい順に並べた配列。
`fetch_history.py` で、有価証券報告書から最大14期分(EDINETの保存期間の上限)に延ばす。
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

- 1社につき、最新・期末が4年前・8年前・9年前の有報を1本ずつ取る(9年前がEDINETで取れる最古)。各有報に5期分の1株配当と発行済株式数が載る。
- 1本の中では、株数の比をきりのいい倍率に寄せ、分割の前後で配当が倍率ぶん下がっていれば割り戻す
  (過去期を修正済みで載せている会社はそのまま)。
- 有報どうしは重なる1期で倍率を合わせる。合わなければ古い有報はつながない。
- 期の途中で分割した年(中間は分割前・期末は分割後の混在。トヨタ148円など)は、
  株数が跳ねた期の近くで40%を超えて下がっていれば、その年より古い期を外す。
- 3倍を超える増配は上場前の年度の混入とみなし、それより古い期を外す。
- `apply` は、既存の値(直近3期)と一致する銘柄だけを延ばす。一致しない銘柄は既存のまま。

2026年9月の実行結果: 2,207銘柄を3期より長く延長(うち887銘柄が14期)。直近が既存の値と食い違う銘柄は据え置き。それより前の推移は IR BANK へのリンクで補う。

## 毎週の更新(GitHub Actions)

`.github/workflows/edinet-monthly.yml` が毎週月曜に `monthly.py` を動かし、変わっていればコミットして公開する。
Actions の画面の「Run workflow」から手動でも動かせる(見る日数も指定可)。

- 直近45日に提出された有報のうち、`state.json`(証券コード → 取り込んだ有報の期末日)より新しい期のものだけ読む。
- 1株配当は新しい期を先頭に足す。有報の前期・前々期が今の系列と合うときだけつなぎ、分割で倍率がずれていれば割り戻す。
  合わなければ有報の5期分(`build_code` と同じ切り方)に置き換える。配当性向は当期の値にする。
- 内蔵データに無い証券コード(新規上場など)は、EDINETコードリストの社名・業種で足す。リストが取れない月は翌月に回す。
- リポジトリの Secrets に `EDINET_API_KEY` が必要。

`state.json` の初期値は、2026年9月にチェックシート(ir-check)の数字を同じ有報から作ったときの期末日で、
内蔵の1株配当の直近2期が一致した銘柄だけ埋めた。

`fetch_history.py` の長期履歴の作り直し(数年に一度でよい)は、これまでどおり手で行う。

## 出典表示

EDINET(公共データ利用規約 PDL1.0)。フッターの出典と加工の明示は既存のままでよい。
