#!/usr/bin/env python3
"""companyfacts から 'Dividend' を含むタグ一覧と最新期間を表示。使い方: sec_tags.py KO"""
import sys, json, urllib.request
UA = "haito-dashboard research 82706991hiroto@gmail.com"
def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60))
cik = {v["ticker"]: v["cik_str"] for v in get("https://www.sec.gov/files/company_tickers.json").values()}
t = sys.argv[1]
d = get("https://data.sec.gov/api/xbrl/companyfacts/CIK%010d.json" % cik[t])
for ns, tags in d["facts"].items():
    for tag, v in tags.items():
        if "ividend" in tag and "USD/shares" in v["units"]:
            rows = v["units"]["USD/shares"]
            print(ns, tag, len(rows), "latest end:", max(r["end"] for r in rows))
