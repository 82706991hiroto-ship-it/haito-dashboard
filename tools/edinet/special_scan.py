#!/usr/bin/env python3
"""記念配当・特別配当を有価証券報告書の注記から拾い、data/special-dividends.json に残す。

有報の「主要な経営指標等の推移」には「第45期の1株当たり配当額には記念配当10円を含んでおります」のような注記がある。
内蔵の1株配当は記念配当込みの実績なので、そのままだと翌期に「減配」に見えてしまう。
その期の1株配当に占める割合で残し(株式分割をまたいでも使えるように)、HAITO は普通配当で増配・減配を判断する。

  EDINET_API_KEY=... python3 tools/edinet/special_scan.py --days 45          # 見つけたものを表示
  EDINET_API_KEY=... python3 tools/edinet/special_scan.py --days 45 --write  # data/special-dividends.json に足す
"""
import argparse, datetime as dt, io, json, os, re, sys, unicodedata, zipfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_history as fh  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "special-dividends.json")
HTML = os.path.join(ROOT, "index.html")

AMOUNT = re.compile(r"(記念配当|特別配当)[^0-9。]{0,8}?(\d+(?:\.\d+)?)円")


def filings(days):
    today = dt.date.today()
    dates = [(today - dt.timedelta(days=i)).isoformat() for i in range(days)]

    def one(d):
        r = fh.get(fh.API + "/documents.json", {"date": d, "type": 2})
        return (r.json().get("results") or []) if r is not None else []

    by = {}
    with ThreadPoolExecutor(4) as ex:
        for rows in ex.map(one, dates):
            for x in rows:
                if (x.get("docTypeCode") == "120" and x.get("ordinanceCode") == "010" and x.get("secCode")
                        and x.get("csvFlag") == "1" and x.get("withdrawalStatus") == "0" and x.get("periodEnd")):
                    code = x["secCode"][:4].upper()
                    if code not in by or x["periodEnd"] > by[code]["periodEnd"]:
                        by[code] = x
    return by


def read(doc_id):
    r = fh.get(fh.API + "/documents/" + doc_id, {"type": 5})
    if r is None or r.content[:2] != b"PK":
        return None
    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        name = next(n for n in z.namelist() if re.search(r"XBRL_TO_CSV/jpcrp.*asr.*\.csv$", n))
        return z.read(name).decode("utf-16")
    except (StopIteration, zipfile.BadZipFile, UnicodeDecodeError):
        return None


def specials(raw, latest_no, fyend):
    """{"YYYY-MM": {"額": 円, "割合": 1株配当に占める割合}} を返す。"""
    parsed = fh.parse_csv(raw)
    text = unicodedata.normalize("NFKC", raw)
    out = {}
    # 「第45期の1株当たり配当額(78円)には記念配当10円を含んで…」の形だけを拾う(表の見出しの期番号と取り違えないように)
    for m in re.finditer(r"第(\d+)期(?:の|における)?1株当たり配当額([^。]{0,80})", text):
        amts = [float(x) for _, x in AMOUNT.findall(m.group(2))]
        if not amts:
            continue
        back = latest_no - int(m.group(1))
        if not (0 <= back < len(parsed["periods"])):
            continue
        dps = parsed["periods"][back]["dps"]
        amt = sum(amts)
        if not dps or not (0 < amt < dps):
            continue
        y, mm = int(fyend[:4]) - back, int(fyend[5:7])
        out["%d-%02d" % (y, mm)] = {"額": amt, "割合": round(amt / dps, 4)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    html = open(HTML, encoding="utf-8").read()
    info = json.loads(re.search(r"var CODE_INFO_MAP = (\{.*?\});\n", html).group(1))
    data = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    docs = {c: x for c, x in filings(a.days).items() if c in info}
    print("有報", len(docs), "件を読みます", flush=True)

    def one(item):
        code, x = item
        m = re.search(r"第(\d+)期", x.get("docDescription") or "")
        if not m:
            return code, x, {}
        raw = read(x["docID"])
        if not raw:
            return code, x, {}
        try:
            return code, x, specials(raw, int(m.group(1)), x["periodEnd"])
        except Exception as e:  # 1件の読み違いで全体を止めない
            print("読めず", code, e, flush=True)
            return code, x, {}

    found = 0
    with ThreadPoolExecutor(4) as ex:
        for code, x, sp in ex.map(one, sorted(docs.items())):
            if not sp:
                continue
            cur = data.setdefault(code, {"名前": info[code][0], "期": {}})
            for k, v in sp.items():
                if cur["期"].get(k, {}).get("割合") != v["割合"]:
                    v["出典"] = "EDINET 有報 %s" % x["docID"]
                    cur["期"][k] = v
                    found += 1
                    print(code, info[code][0], k, "%s円(%.0f%%)" % (v["額"], v["割合"] * 100))
    print("記念配当・特別配当", found, "件")
    if a.write:
        data = dict(sorted(data.items()))
        lines = ["{"] + ["  %s: %s," % (json.dumps(k, ensure_ascii=False), json.dumps(v, ensure_ascii=False)) for k, v in data.items()]
        lines[-1] = lines[-1].rstrip(",")
        open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n}\n")


if __name__ == "__main__":
    main()
