#!/usr/bin/env python3
"""State Street SPDR 全ETFの分配金履歴xlsxから指定ティッカーを抽出。使い方: fetch_spdr.py SPYD [件数]
標準ライブラリのみ(xlsxをzip+XMLで直接パース)。"""
import sys, io, zipfile, re, urllib.request, xml.etree.ElementTree as ET
URL = "https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx"
tick = sys.argv[1]; n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
data = urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "haito-dashboard research 82706991hiroto@gmail.com"}), timeout=90).read()
z = zipfile.ZipFile(io.BytesIO(data))
ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
ss = [("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"]))) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns)]
wb = ET.fromstring(z.read("xl/workbook.xml"))
print("sheets:", [s.get("name") for s in wb.find("m:sheets", ns)])
for name in sorted(x for x in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", x)):
    rows = []
    for r in ET.fromstring(z.read(name)).iter("{%s}row" % ns["m"]):
        vals = []
        for c in r.findall("m:c", ns):
            v = c.find("m:v", ns)
            vals.append(ss[int(v.text)] if c.get("t") == "s" and v is not None else (v.text if v is not None else ""))
        rows.append(vals)
    print(name, len(rows), "rows; header:", rows[:3])
    hits = [r for r in rows if tick in r]
    for r in hits[:n]: print(r)
