#!/usr/bin/env python3
"""Invesco公式サイトのフロントが使うJSON API(dng-api)から分配金履歴を取得。使い方: fetch_invesco.py QQQ [件数]"""
import sys, json, urllib.request
UA = "haito-dashboard research 82706991hiroto@gmail.com"
CUSIP = {"QQQ": "46090E103"}  # 商品ページの productMetaData.cusip (idType=cusip)
t = sys.argv[1].upper(); n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
url = f"https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/{CUSIP[t]}/distribution?idType=cusip&productType=ETF"
d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60))
print(url)
for r in d["distributions"][:n]:
    print(r["exDate"], r["payDate"], r["distributionAmountPerUnit"])
