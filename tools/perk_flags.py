#!/usr/bin/env python3
"""index.html の PERK_INFO(株主優待の有無と年間の目安。EDINETの有報「株主に対する特典」から作成)を
perks/flags.json に書き出す。チェックシート(../ir-check/)が優待の有無を出すときに読む。

  python3 tools/perk_flags.py
"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
m = re.search(r"var PERK_INFO = (\{.*?\});", src)
info = json.loads(m.group(1))
out = os.path.join(ROOT, "perks", "flags.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(info, f, ensure_ascii=False, separators=(",", ":"))
print(len(info), "社 →", out)
