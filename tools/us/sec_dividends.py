#!/usr/bin/env python3
"""米国の個別株の年間1株配当を、SEC EDGAR の公式API(XBRL companyfacts)から取り、
index.html の US_DIV_MAP に書き込む。毎週の自動更新(GitHub Actions)から呼ぶ。

- 使うのは最新の10-Kに載っている会計年度ごとの1株配当(宣言額 Declared、なければ支払額 CashPaid)。
  最新の10-Kは過去の年度も分割を反映した値で載せ直しているので、最新の10-Kの分だけを使う。
- SECのアクセスルール: User-Agent に連絡先を書く、10回/秒以下。
  https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- SECの情報は公共情報で、出典を書けば転載できる(https://www.sec.gov/privacy)。
"""
import argparse, datetime as dt, json, os, re, sys, time
import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UA = "HAITO dividend dashboard (personal, non-commercial) 82706991hiroto@gmail.com"
TAGS = ("CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid")


def get(url, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"}, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    return None


def days(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def annual_series(facts):
    """会計年度ごとの1株配当(新しい順)と、最新の期末日を返す。"""
    gaap = (facts or {}).get("facts", {}).get("us-gaap", {})
    best = None
    for tag in TAGS:
        rows = (gaap.get(tag, {}).get("units", {}) or {}).get("USD/shares", [])
        # 1年分(10-K、期間がほぼ1年)の値だけ
        rows = [r for r in rows if r.get("form") in ("10-K", "10-K/A") and r.get("start")
                and 330 <= days(r["start"], r["end"]) <= 400]
        if not rows:
            continue
        latest = max(rows, key=lambda r: (r["filed"], r["end"]))
        # 最新の10-K(同じ提出番号)に載っている年度だけを使う
        same = {}
        for r in rows:
            if r["accn"] == latest["accn"]:
                same[r["end"]] = r["val"]
        series = [round(float(same[k]), 4) for k in sorted(same, reverse=True)]
        cand = (max(same), series)
        if best is None or cand[0] > best[0]:
            best = cand
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default=os.path.join(ROOT, "index.html"))
    ap.add_argument("--tickers", default=os.path.join(ROOT, "data", "us-tickers.json"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    tickers = json.load(open(a.tickers, encoding="utf-8"))["tickers"]
    index = get("https://www.sec.gov/files/company_tickers.json")
    if not index:
        print("SECのティッカー一覧が取れませんでした", file=sys.stderr)
        sys.exit(1)
    cik = {v["ticker"].upper(): v["cik_str"] for v in index.values()}

    out, miss = {}, []
    for t in tickers:
        c = cik.get(t.upper())
        if not c:
            miss.append(t + "(CIKなし)")
            continue
        time.sleep(0.15)
        facts = get("https://data.sec.gov/api/xbrl/companyfacts/CIK%010d.json" % c)
        s = annual_series(facts)
        if not s or not s[1]:
            miss.append(t)
            continue
        out[t.upper()] = {"fy": s[0], "d": s[1][:5]}
    print("取得: %d銘柄 / 取れなかった: %s" % (len(out), " ".join(miss) or "なし"))
    for t in list(out)[:8]:
        print(" ", t, out[t])
    if a.dry_run:
        return
    html = open(a.html, encoding="utf-8").read()
    body = json.dumps(dict(sorted(out.items())), ensure_ascii=False, separators=(",", ":"))
    html, n = re.subn(r"var US_DIV_MAP = \{.*?\};\n", lambda _: "var US_DIV_MAP = %s;\n" % body, html, count=1)
    if n != 1:
        print("index.html に US_DIV_MAP が見つかりません", file=sys.stderr)
        sys.exit(1)
    open(a.html, "w", encoding="utf-8").write(html)


if __name__ == "__main__":
    main()
