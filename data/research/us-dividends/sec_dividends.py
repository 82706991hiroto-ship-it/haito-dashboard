#!/usr/bin/env python3
"""SEC EDGAR companyconcept から1株配当(宣言額)を取得。使い方: sec_dividends.py NVDA KO"""
import sys, json, urllib.request
UA = "haito-dashboard research 82706991hiroto@gmail.com"
def get(url):
    r = urllib.request.Request(url, headers={"User-Agent": UA})
    return json.load(urllib.request.urlopen(r, timeout=30))
tick = get("https://www.sec.gov/files/company_tickers.json")
cik = {v["ticker"]: v["cik_str"] for v in tick.values()}
for t in sys.argv[1:]:
    c = "%010d" % cik[t]
    for tag in ("CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"):
        try:
            d = get(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{c}/us-gaap/{tag}.json")
        except Exception as e:
            print(t, tag, "ERR", e); continue
        rows = d["units"]["USD/shares"]
        rows = [r for r in rows if r.get("form") in ("10-K", "10-Q")]
        rows.sort(key=lambda r: (r["end"], r["start"] if "start" in r else ""))
        print(f"== {t} {tag} ({len(rows)} rows) last 14")
        for r in rows[-14:]:
            print(r.get("start"), r["end"], r["val"], r["form"], r.get("fp"), r["filed"], r["accn"])
