#!/usr/bin/env python3
"""Global X ファンドページ(Next.js)に埋め込まれた分配金履歴JSONを抽出。使い方: fetch_globalx.py qyld [件数]"""
import sys, re, json, urllib.request
t = sys.argv[1].lower(); n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
url = f"https://www.globalxetfs.com/funds/{t}"
h = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "haito-dashboard research 82706991hiroto@gmail.com"}), timeout=60).read().decode("utf-8", "replace")
h = h.replace('\\"', '"')
rows = {}
for m in re.finditer(r'\{"amount":[^{}]*\}', h):
    try: d = json.loads(m.group(0))
    except Exception: continue
    rows[(d["ex_date"], d.get("payable_date"))] = d
rows = sorted(rows.values(), key=lambda d: d["ex_date"], reverse=True)
print(url, len(rows), "rows")
for d in rows[:n]: print(d)
