#!/usr/bin/env python3
"""Vanguard ETF商品ページが内部で呼ぶJSON(/vmf/api/<TICKER>/distribution)から直近の分配金を取得。
使い方: fetch_vanguard.py VYM VIG   ※返るのは直近6回分のみ。"""
import sys, json, urllib.request
for t in sys.argv[1:]:
    url = f"https://investor.vanguard.com/vmf/api/{t.upper()}/distribution"
    d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "haito-dashboard research 82706991hiroto@gmail.com", "Accept": "application/json"}), timeout=60))["divCapGain"]
    print(url, d["distributionFrequency"])
    for r in d["item"]: print(r["recordDate"][:10], r["payableDate"][:10], r["perShareAmount"], r["type"])
