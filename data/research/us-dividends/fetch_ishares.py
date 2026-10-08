#!/usr/bin/env python3
"""iShares商品ページ内に埋め込まれた分配金テーブル(performance.distributions.table)を抽出。
使い方: fetch_ishares.py 239563 ishares-core-high-dividend-etf [件数]"""
import sys, re, html, json, urllib.request
pid, slug = sys.argv[1], sys.argv[2]; n = int(sys.argv[3]) if len(sys.argv) > 3 else 8
url = f"https://www.ishares.com/us/products/{pid}/{slug}"
req = urllib.request.Request(url, headers={"User-Agent": "haito-dashboard research 82706991hiroto@gmail.com"})
t = html.unescape(urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace"))
i = t.find('"fullName":"performance.distributions.table"')
seg = t[i:i + 60000]
cols = {}
for m in re.finditer(r'"fullName":"performance\.distributions\.table\.(\w+)".*?"formattedValue":(\[.*?\])', seg):
    cols.setdefault(m.group(1), json.loads(m.group(2)))
print(url, "columns:", list(cols))
for k in range(n):
    print({c: v[k] for c, v in cols.items() if k < len(v)})
