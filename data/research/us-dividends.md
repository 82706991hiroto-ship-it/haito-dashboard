# 米国株・ETF 年間配当 自動取得の下調べ

調査日: 2026-10-07 / ブランチ: research-dividends
スクリプトと生出力: `data/research/us-dividends/`(Python標準ライブラリのみ。`python3 -I <script>` で実行)

使った情報源は SEC EDGAR と各運用会社の公式サイトだけです。Yahoo Finance、Nasdaq.com、Seeking Alpha、株探、IR BANK などのまとめサイトは取得にも比較にも使っていません。

## 結論(先に)

| 対象 | 技術的に機械取得できるか | 規約上、自動取得+公開サイト掲載してよいか |
|---|---|---|
| NVDA, KO など個別株 (SEC EDGAR) | できる(JSON API) | **可**。SEC は公共情報として転載自由(出典明記を推奨)。ただし User-Agent の申告と 10 req/秒以下が条件 |
| VYM, VIG (Vanguard) | できる(JSON)。ただし直近6回分だけ | **不可(許諾がない)**。「個人の非商用利用」ライセンスのみ |
| HDV (iShares) | できる(商品ページ埋め込みデータ) | **不可**。robot/spider の使用と「公開目的での再利用」が明文で禁止 |
| SPYD (State Street SPDR) | できる(全ETFの履歴xlsx) | **不可**。個人用プリントアウトと社内用コピー以外の複製・再配布を禁止 |
| QQQ (Invesco) | できる(JSON API)。ただし素のブラウザ風 User-Agent は 406 で弾かれる | **不可**。data mining / robots / 自動アクセス装置を明文で禁止 |
| QYLD (Global X) | できる(ページ埋め込みJSON) | **未確認(安全側で不可扱い)**。米国サイトの利用規約ページを取得できなかった |

- 個別株は SEC の API だけで規約上もきれいに自動化できます。
- ETF は 5 社すべて技術的には取得できます。しかし規約上、自動取得して公開サイトに載せてよいと確認できたのは 1 社もありません。
- 規約の読みは私の解釈で、法的助言ではありません。確実にするなら各社へ書面で問い合わせるのが安全です。

---

## 1. SEC EDGAR(個別株)

**取得URL**
- `https://www.sec.gov/files/company_tickers.json` : ティッカーからCIKへの対応表
- `https://data.sec.gov/api/xbrl/companyconcept/CIK{10桁}/us-gaap/CommonStockDividendsPerShareDeclared.json`
- `https://data.sec.gov/api/xbrl/companyconcept/CIK{10桁}/us-gaap/CommonStockDividendsPerShareCashPaid.json`
- `https://data.sec.gov/api/xbrl/companyfacts/CIK{10桁}.json` : 全タグ。ここから「Dividend」を含む使用中タグを探せます

**取得方法**
- 形式は JSON(単位 `USD/shares`)。
- 必須ヘッダは `User-Agent: 会社名/アプリ名 連絡先メール`(SEC の例は `Sample Company Name AdminContact@<domain>.com`)。
- 実際に叩いた値は 200 OK で返りました(NVDA の declared、KO の companyfacts)。
- 宣言なしの素のUAは `www.sec.gov` の HTML ページで 403 を受けます。申告 UA を付けると通ります。

**確認した値**(`us-dividends/sec_output.txt`、`sec_dividends.py` / `sec_tags.py`)

NVDA(会計年度は1月末締め)は `...Declared` タグを使います。期間は各提出書類の `start`/`end` です。

| 期間 | 1株配当(USD) | 備考 |
|---|---|---|
| FY2025(2024-01-29〜2025-01-26) | 0.034 | 10-K |
| 2025-01-27〜2025-04-27 | 0.01 | Q1 |
| 2025-04-28〜2025-07-27 | 0.01 | Q2 |
| 2025-07-28〜2025-10-26 | 0.01 | Q3 |
| FY2026(2025-01-27〜2026-01-25) | 0.04 | 10-K。Q4 は 0.04 − 0.03 = 0.01 と引き算で出す |
| 2026-01-26〜2026-04-26 | 0.01 | Q1 |
| 2026-04-27〜2026-07-26 | **0.25** | Q2 |
| 2026-01-26〜2026-07-26 | **0.26** | 6か月累計 |

- 直近の 0.25 / 0.26 は従来の 0.01 から急に増えています。これは SEC のデータそのままの値です。特別配当か増配かは、この調査では確認していません。
- NVDA の `...CashPaid` は 2024-06-28 で止まっています。NVDA は Declared を使います。

KO は `...Declared` が 2018-09-28 で止まっています。現行は `...CashPaid` です(支払ベース)。

| 期間 | 1株配当(USD) |
|---|---|
| 2024-06-29〜2024-09-27 | 0.485 |
| 2024暦年 | 1.94(10-K) |
| 2025-01-01〜2025-03-28 | 0.51 |
| 2025-03-29〜2025-06-27 | 0.51 |
| 2025-06-28〜2025-09-26 | 0.51 |
| 2025暦年 | 2.04(10-K) |
| 2026-01-01〜2026-04-03 | 0.53(最新の 10-Q) |

**規約上の可否: 可**
- 「Information presented on sec.gov is considered public information and may be copied or further distributed by users of the web site without the SEC's permission. Please consider appropriate citation to the SEC as the source.」(https://www.sec.gov/privacy)
- 「Current max request rate: 10 requests/second. … Please declare your user agent in request headers」(https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
- 「The SEC does not allow "unclassified" bots or automated tools to crawl the site.」(https://www.sec.gov/developer)
- 週1回のジョブで数銘柄なら、レート制限にはまず届きません。

**安定性の注意**
- タグは会社ごとにばらばらで、NVDA は Declared、KO は CashPaid です。同じ会社でも年度途中で切り替わることがあります。
- 四半期値は 10-Q にあり、第4四半期は年間値から 9か月累計を引いて自分で算出します。同じ期間が複数の提出書類に再掲され(再提出や遡及修正で値が違うことがある)、重複を `accn` や `filed` で整理する必要があります。
- 株式分割後の遡及修正があります。NVDA の FY2025 が 0.034 なのは分割調整後の値です。
- 配当ゼロや無配の会社はタグ自体がありません。
- `companyconcept` は一度だけ「単位キーはあるが中身が空」の応答を返しました(KO の CashPaid)。同じデータを `companyfacts` で取ると 95 行ありました。実装時は空応答を検知して `companyfacts` に切り替えるか再試行してください。原因は不明です。
- 反映は提出書類の公開後で、権利落ち日とは無関係に遅れます。権利落ち日・支払日は XBRL では取れません(8-K の本文にあります)。
- 「直近12か月」は提出済みの期間から組み立てるため、最新四半期が 10-Q 提出前だと 1 四半期ぶん古くなります。

---

## 2. ETF 運用会社(公式サイト)

どれも公開された「公式ページ/公式ファイル」ですが、公式のデータ配信APIではありません。ページ構造が変わると壊れます。ex-date は米国の T+1 決済以降、record date と同日です。

### 2-1. Vanguard (VYM, VIG)

- **取得URL**: `https://investor.vanguard.com/vmf/api/VYM/distribution`(VIG も同形式)。商品ページ(`https://investor.vanguard.com/investment-products/etfs/profile/vym`)が内部で呼ぶ JSON です。ヘッドレスブラウザの通信ログで特定しました。
- **取得方法**: GET、JSON(`Accept: application/json`)。UA の制限は確認されませんでした。`us-dividends/fetch_vanguard.py`
- **注意**: 商品ページの HTML は VYM では埋め込みデータがあり、VIG では空のシェルでした。HTML スクレイピングは不安定で、JSON を使うほうが安全です。
- **確認した値**(`vanguard_output.txt`)。返るのは直近 **6 回分のみ**で、8 回分は取れません。項目は record date、payable date、1株額です。

| 銘柄 | record date | payable date | 1株(USD) |
|---|---|---|---|
| VYM | 2026-09-18 | 2026-09-22 | 0.8869 |
| VYM | 2026-06-18 | 2026-06-23 | 0.9795 |
| VYM | 2026-03-20 | 2026-03-24 | 0.8617 |
| VYM | 2025-12-19 | 2025-12-23 | 0.9474 |
| VYM | 2025-09-19 | 2025-09-23 | 0.8417 |
| VYM | 2025-06-20 | 2025-06-24 | 0.8617 |
| VIG | 2026-09-28 | 2026-09-30 | 0.9295 |
| VIG | 2026-06-26 | 2026-06-30 | 0.9988 |
| VIG | 2026-03-27 | 2026-03-31 | 0.8334 |
| VIG | 2025-12-22 | 2025-12-24 | 0.8844 |
| VIG | 2025-09-29 | 2025-10-01 | 0.8647 |
| VIG | 2025-06-30 | 2025-07-02 | 0.8712 |

- 直近12か月は4回分で足りますが、前年12か月(さらに4回)には 6 回分では足りません。前年分を取るには、毎週の取得結果を蓄積して履歴ファイルを作る方式が要ります。
- **規約**: 「Vanguard grants you a limited, revocable, nonexclusive, nontransferable license to use, view, store, bookmark, download, display, stream, and print the pages and any content … solely for your personal and noncommercial use or as expressly authorized by Vanguard in writing.」(https://corporate.vanguard.com/content/corporatesite/us/en/corp/terms-of-use.html、investor.vanguard.com を対象に含む)
  - robot / スクレイピングを名指しで禁じる文言は、この規約ページでは見つかりませんでした。
  - ただし許諾は「個人の非商用」に限られます。公開サイトへの掲載は許諾の範囲外と読めます。
  - robots.txt(https://investor.vanguard.com/robots.txt)は `/images/` `/static/` `/404` だけを Disallow しています。
- **安定性**: 内部 API なので予告なく変わり得ます。レスポンスの JSON はこの 1 回しか確認していません。

### 2-2. iShares / BlackRock (HDV)

- **取得URL**: `https://www.ishares.com/us/products/239563/ishares-core-high-dividend-etf`。商品ページに分配金テーブル全履歴が JSON として埋め込まれています(2011年から)。
- **取得方法**: GET。HTML(約1.7MB)中の `performance.distributions.table` を抽出します。CSV 直リンクは見つかりませんでした(`latest-holdings.csv` は保有銘柄用です)。`us-dividends/fetch_ishares.py`
- **確認した値**(`ishares_hdv_output.txt`)。直近8回分は次のとおりです。

| ex-date | 支払日 | 1株(USD) |
|---|---|---|
| 2026-09-16 | 2026-09-21 | 0.055959 |
| 2026-08-19 | 2026-08-24 | 0.104616 |
| 2026-07-15 | 2026-07-20 | 0.087389 |
| 2026-06-15 | 2026-06-18 | 0.185049 |
| 2026-03-17 | 2026-03-20 | 0.168592 |
| 2025-12-16 | 2025-12-19 | 0.250576 |
| 2025-09-16 | 2025-09-19 | 0.189916 |
| 2025-06-16 | 2025-06-20 | 0.182618 |

  - 2026 年の 6〜9 月は月次の頻度で並んでいます。金額も小さく、四半期と月次が混在しています。
  - 値の妥当性(分割調整後か、頻度変更か)は、価格の情報源がない(まとめサイトを使わない条件)ため、検証していません。実装前に iShares 側で確認してください。
- **規約**(https://www.blackrock.com/corporate/compliance/terms-and-conditions)
  - 「Use any robot, spider, intelligent agent, other automatic device, or manual process to search, monitor or copy this Website or the reports, data, information, content … without BlackRock's permission」を禁止行為として列挙しています。
  - 「You may not distribute, modify, transmit, reuse, repost, or use the content of this Website for public or commercial purposes … without BlackRock's written permission.」
  - 「Such content is solely for your personal, non-commercial use.」
  - 自動取得も、公開サイトへの掲載も、許諾なしでは禁止です。**不可**。
  - robots.txt(https://www.ishares.com/robots.txt)は `/search/` などを除いて許可していますが、規約のほうが優先されます。
- **安定性**: 画面用の埋め込みデータなので、構造変更に弱い方式です。

### 2-3. State Street SPDR (SPYD)

- **取得URL**: `https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx`。SPDR 全ETFの履歴が 1 ファイル(約 13,000 行)にあります。配当ページ(https://www.ssga.com/us/en/intermediary/resources/documents/etf-dividend-distributions)からリンクされています。
- **取得方法**: GET、xlsx。列は FUND NAME / TICKER / CUSIP / EX-DATE / RECORD DATE / PAYABLE DATE / DIVIDEND ($) / SHORT TERM CAPITAL GAIN / LONG TERM CAPITAL GAIN / FREQUENCY です。`us-dividends/fetch_spdr.py` は標準ライブラリだけでパースします。
- **確認した値**(`spdr_output.txt`)

| ex-date | 支払日 | 1株(USD) |
|---|---|---|
| 2026-09-21 | 2026-09-23 | 0.517794 |
| 2026-06-22 | 2026-06-24 | 0.542849 |
| 2026-03-23 | 2026-03-25 | 0.449980 |
| 2025-12-22 | 2025-12-24 | 0.549335 |
| 2025-09-22 | 2025-09-24 | 0.488758 |
| 2025-06-23 | 2025-06-25 | 0.500042 |
| 2025-03-24 | 2025-03-26 | 0.418901 |
| 2024-12-20 | 2024-12-24 | 0.546774 |

- 直近12か月は 2.0600、その前の12か月は 1.9545 USD です(ex-date 2025-10-08〜2026-10-07 と 2024-10-08〜2025-10-07 を合計)。
- **規約**(https://www.ssga.com/us/en/footer/terms-and-conditions)
  - 「You may not copy, reproduce, duplicate, modify, adopt or lend, sell, disseminate or otherwise transfer, in whole or in part, any of the information contained in this Site, except for the purpose of accessing the Site and producing print-outs for your own personal use, or making a reasonable number of copies of such pages for internal use within your organization」
  - 「allow or cause any information transmitted from State Street Investment Management's databases … to be published, redistributed or retransmitted for other than use for or on behalf of yourself」
  - 公開サイトへの転載は許諾の範囲外です。**不可**。
  - robots.txt(https://www.ssga.com/robots.txt)は今回のファイルのパスを Disallow していません。
- **安定性**: 配布用の固定パスのファイルで、ETF 向けとしては最も機械処理向きです。

### 2-4. Invesco (QQQ)

- **取得URL**: `https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/46090E103/distribution?idType=cusip&productType=ETF`。QQQ の商品ページ(https://www.invesco.com/us/en/financial-products/etfs/invesco-qqq-trust-series-1.html)の分配金表が呼ぶ JSON です。ページ内の設定から特定しました。
- **取得方法**: GET、JSON。`idType=ticker` では空文字が返り、CUSIP で指定する必要があります(QQQ は `46090E103`)。
- **UA の注意**: `Mozilla/5.0 (X11; Linux x86_64) haito-research` のようなブラウザ風 UA は **HTTP 406** で拒否されました。`haito-dashboard research <連絡先>` のような自己申告 UA や curl 既定 UA では 200 でした。ブラウザ偽装はせず、正直な UA で取得してください。`us-dividends/fetch_invesco.py`
- **確認した値**(`invesco_output.txt`)

| ex-date | 支払日 | 1株(USD) |
|---|---|---|
| 2026-09-21 | 2026-10-08 | 0.75143 |
| 2026-06-22 | 2026-07-10 | 0.81349 |
| 2026-03-23 | 2026-03-27 | 0.73282 |
| 2025-12-22 | 2025-12-31 | 0.79408 |
| 2025-09-22 | 2025-10-31 | 0.69395 |
| 2025-06-23 | 2025-07-31 | 0.59111 |
| 2025-03-24 | 2025-04-30 | 0.71571 |
| 2024-12-23 | 2024-12-31 | 0.83466 |

- 直近12か月は 3.0918、その前の12か月は 2.8354 USD です。
- **規約**(https://www.invesco.com/us/en/resources/terms-of-use.html)
  - 「users and visitors of the Website may not: … Use devices (including software) that are designed to provide repeated automated access to the Website other than those made generally available by Invesco.」
  - 「Resell or provide commercial use of the Website or the content therein, or create any derivative use … ; or use any data mining, robots, or similar data gathering and extraction tools on the Website.」
  - 「Copy, reproduce, republish, upload, post, transmit, or distribute in any way material from the Website in any manner inconsistent with the purposes for which it is offered」
  - 自動取得を明文で禁止しています。**不可**。
- **安定性**: 内部 API で、CUSIP 指定が必要です。ブラウザ風 UA への制限など、挙動が変わり得ます。

### 2-5. Global X (QYLD)

- **取得URL**: `https://www.globalxetfs.com/funds/qyld`。Next.js のページに `distributionHistoryData`(2014年から全履歴、`ex_date` `record_date` `payable_date` `amount` `income_dist_amount`)が埋め込まれています。
- **取得方法**: GET、HTML 内の JSON(`\"` エスケープ)を正規表現で抽出します。`us-dividends/fetch_globalx.py`。未確定の将来分は `amount` が null で返ります。
- **確認した値**(`globalx_output.txt`、月次)

| ex-date | 支払日 | 1株(USD) |
|---|---|---|
| 2026-09-21 | 2026-09-24 | 0.1767 |
| 2026-08-24 | 2026-08-27 | 0.1829 |
| 2026-07-20 | 2026-07-23 | 0.1775 |
| 2026-06-22 | 2026-06-25 | 0.1854 |
| 2026-05-18 | 2026-05-21 | 0.1785 |
| 2026-04-20 | 2026-04-23 | 0.1789 |
| 2026-03-23 | 2026-03-26 | 0.1715 |
| 2026-02-23 | 2026-02-26 | 0.1771 |

  - 直近12か月の合計は 2.13 USD で、件数が 13 件になりました。窓の端か重複かは未確認です。
  - 前の12か月の合計は 2.22 USD です(12 件)。
- **規約**: 米国サイトの利用規約ページを取得できませんでした。`/terms-of-use` `/terms-and-conditions` `/legal` はいずれも 404 で、フッターにもリンクがありません。
  - 欧州サイト(https://www.globalxetfs.eu/terms-of-use)とカナダサイト(https://www.globalx.ca/terms-of-use)は、ここからは 403 で、本文を確認できていません。
  - 検索結果の抜粋に「Any replication, citation, reprinting, transmission or otherwise of Global X – by any means and for any purpose – without permission is prohibited.」という文言がありました(欧州サイトのもの。これは検索抜粋のみで、本文では未確認)。
  - robots.txt(https://www.globalxetfs.com/robots.txt)は全許可(`Disallow:` が空)です。
  - 確認できていないので、安全側で**不可扱い**とします。許諾の問い合わせが必要です。
- **安定性**: Next.js の内部データ形式で、最も壊れやすい方式です。

---

## 3. おすすめの実装方法

1. **個別株は SEC の companyfacts を週次ジョブで取得する**(規約上クリア)。
   - ジョブは申告 UA を付け、リクエストは 1 銘柄あたり 1〜2 回、1 秒以内に 10 回を超えないようにします。
   - 優先度は `CommonStockDividendsPerShareDeclared`、なければ `...CashPaid` です。
   - 四半期値と年間値を期間の長さ(約90日 / 約365日)で判別し、重複(同じ `start`/`end`)は最新の `filed` を採用します。
   - 直近12か月は直近の四半期の積み上げで出します。第4四半期は年間値から 9か月累計を引きます。
   - 前年12か月は、その前の 4 四半期、または前の会計年度の年間値で出します。
   - 空応答は `companyfacts` で再取得します。出力は静的な JSON ファイルに書き、サイトはそれを読むだけにします。
2. **ETF は、今の規約のままでは自動取得・公開しない**のが無難です。
   - 各社に、個人の無料ツールでの利用(分配金の数字だけを自動取得して表示する)について書面で許諾を問い合わせる。許可が出た会社から追加する、という進め方が現実的です。
   - 許諾が出るまでの当面は、**手入力(自分で各社の公式ページを見て更新する)** か、自分の証券会社の配当履歴を使う運用にします。手入力なら自動取得の禁止条項には触れません。ただし「公開サイトに載せる」ことが許諾の範囲外という点は、手入力でも残ります。
   - 公開しない個人用の画面にだけ使うなら、Vanguard の「個人の非商用」ライセンスに近い使い方になります。ただし自動取得そのものを禁じる会社(iShares、Invesco)では、非公開でも自動取得は避けてください。
3. **技術的には**(許諾が得られた場合の構成)、データの取得元は安定度の順に SPDR のxlsx、Vanguard の JSON、Invesco の JSON、iShares の埋め込みデータ、Global X の埋め込みデータです。
   - 取得結果は毎週、履歴ファイル(`data/` の JSON)に追記して蓄積します。Vanguard の 6 回分制限は、蓄積で解消できます。
   - 取得の失敗(HTTP 4xx/5xx、項目欠落、前週から値が大きく変わった場合)では前回値を残し、ジョブを失敗させて通知します。
   - UA は自己申告のものを使い、ブラウザ偽装はしません。
4. **サイトへの表示**では、1株あたりの配当額(USD)・ex-date・支払日、データ源名と取得日を出します。ETF の公式ページの文章や表の体裁そのものは載せません。

## 4. 自動化に使えない銘柄・理由

| 銘柄 | 理由 |
|---|---|
| HDV | iShares/BlackRock の規約が robot/spider を禁止し、公開目的の再利用も禁止(2-2) |
| QQQ | Invesco の規約が data mining / robots / 自動アクセス装置を禁止(2-4) |
| SPYD | State Street の規約が個人用プリントアウトと社内用コピー以外の複製・再配布を禁止(2-3) |
| VYM, VIG | 規約は個人の非商用利用のみを許諾。加えて取得できるのが直近6回分だけで、前年12か月に足りない(2-1) |
| QYLD | 米国の規約を取得できず許諾を確認できない。取得方式も壊れやすい(2-5) |
| 個別株で XBRL に配当タグがない会社 | SEC から取れない。手入力か別の許諾済みデータ源が要る |
| NVDA(参考) | 技術的には取れるが、直近の 0.25 USD(会計 2027 年度第2四半期)が従来の 0.01 から急増しており、特別配当かどうかの確認が要る |

## 付録: 今回の取得の記録

- すべて 1 回ずつの取得で、リクエスト数は少量です。SEC は申告 UA、ETF 各社は申告 UA または汎用 UA で、ブラウザ偽装はしていません(Invesco の 406 を受けた最初の試行だけは `Mozilla/5.0 ... haito-research` という UA でした)。
- Vanguard の JSON エンドポイントを特定するためにヘッドレスブラウザで VIG の商品ページを 1 回読み込みました。
- スクリプトの出力: `sec_output.txt`、`vanguard_output.txt`、`ishares_hdv_output.txt`、`spdr_output.txt`、`invesco_output.txt`、`globalx_output.txt`
