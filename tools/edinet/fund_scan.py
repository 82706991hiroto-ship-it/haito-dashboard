#!/usr/bin/env python3
"""投資信託の分配金を、EDINETの有価証券報告書・半期報告書(内国投資信託受益証券)の「分配の推移」から読み、
data/fund-distributions.json に残す。HAITOは取り込んだ投資信託をファンド名で照らし合わせて、分配金を自動で入れる。

運用会社のサイトは規約で機械的な取得を認めていないことが多いので使わない。EDINETは公式に機械取得が認められている。
有報は半年ごと・決算から約3か月後なので、値は数か月遅れになる(手で入れた値があればHAITOはそちらを優先する)。

  EDINET_API_KEY=... python3 tools/edinet/fund_scan.py --days 45            # 直近の提出分を足す
  EDINET_API_KEY=... python3 tools/edinet/fund_scan.py --days 400 --cache DIR  # 最初の1回(1年分)
"""
import argparse, datetime as dt, io, json, os, re, sys, unicodedata, zipfile, csv
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_history as fh  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "fund-distributions.json")
DATE = r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日"
ROW = re.compile(DATE + r"\s*[～~〜\-－]\s*" + DATE + r"\s*([0-9]+(?:\.[0-9]+)?|―|－|-)")


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
                if (x.get("ordinanceCode") == "030" and x.get("docTypeCode") in ("120", "160") and x.get("fundCode")
                        and x.get("csvFlag") == "1" and x.get("withdrawalStatus") == "0"):
                    key = (x["fundCode"], x["docTypeCode"])
                    if key not in by or (x.get("periodEnd") or "", x["submitDateTime"]) > (by[key].get("periodEnd") or "", by[key]["submitDateTime"]):
                        by[key] = x
    return by


def read(doc_id):
    """(ファンド名, [(期間の終わり, 1万口あたりの分配金)])"""
    r = fh.get(fh.API + "/documents/" + doc_id, {"type": 5})
    if r is None or r.content[:2] != b"PK":
        return None
    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        name = next(n for n in z.namelist() if re.search(r"XBRL_TO_CSV/jpsps.*\.csv$", n))
        rows = list(csv.reader(io.StringIO(z.read(name).decode("utf-16")), delimiter="\t"))
    except (StopIteration, zipfile.BadZipFile, UnicodeDecodeError):
        return None
    facts = {row[0].split(":")[-1]: row[8] for row in rows if len(row) > 8}
    fund = unicodedata.normalize("NFKC", facts.get("FundNameInJapaneseDEI") or facts.get("FundNameCoverPage") or "").strip()
    text = unicodedata.normalize("NFKC", facts.get("HistoricalRecordsOfProfitDistributionTextBlock") or "")
    text = re.sub(r"\s+", " ", text)
    # 表の見出しの単位: 「1口当たり」なら1万倍、「1万口当たり」はそのまま
    per10k = 1 if re.search(r"1万口当たり|10,?000口当たり|1万口当り", text) else 10000 if re.search(r"1口当たり|1口当り", text) else None
    out = []
    for m in ROW.finditer(text):
        v = m.group(7)
        try:
            end = dt.date(int(m.group(4)), int(m.group(5)), int(m.group(6))).isoformat()
        except ValueError:
            continue
        amt = 0.0 if v in ("―", "－", "-") else float(v)
        if per10k is None:
            continue
        out.append((end, round(amt * per10k, 4)))
    return fund, out, per10k


def annual(rows):
    """一番新しい期の終わりから1年の分配金の合計(1万口あたり)と、その期間"""
    if not rows:
        return None
    rows = sorted(set(rows))
    last = dt.date.fromisoformat(rows[-1][0])
    start = last - dt.timedelta(days=365)
    yr = [(e, a) for e, a in rows if dt.date.fromisoformat(e) > start]
    # 1年分そろっていない(設定から1年未満)なら、出さない
    first = dt.date.fromisoformat(rows[0][0])
    if (last - first).days < 300 and len(rows) < 2:
        return None
    return round(sum(a for _, a in yr), 2), (start + dt.timedelta(days=1)).isoformat(), last.isoformat()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--cache", help="書類ごとの読み取り結果を残すフォルダ")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    data = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    docs = filings(a.days)
    todo = sorted(docs.values(), key=lambda x: x["submitDateTime"])
    if a.limit:
        todo = todo[-a.limit:]
    print("投資信託の有報・半期報告書", len(todo), "件を読みます", flush=True)
    if a.cache:
        os.makedirs(a.cache, exist_ok=True)

    def one(x):
        path = a.cache and os.path.join(a.cache, x["docID"] + ".json")
        if path and os.path.exists(path):
            return x, json.load(open(path))
        try:
            got = read(x["docID"])
        except Exception as e:  # 1件の読み違いで全体を止めない
            print("読めず", x["docID"], e, flush=True)
            return x, None
        if path and got:
            json.dump(got, open(path, "w"), ensure_ascii=False)
        return x, got

    n = 0
    with ThreadPoolExecutor(4) as ex:
        for x, got in ex.map(one, todo):
            if not got or not got[0] or not got[1]:
                continue
            fund, rows, _ = got
            # 上場投信(ETF)は1口が1株にあたり、分配金の桁が違う。HAITOでは株として扱うので入れない
            if re.search(r"^上場|ETF|上場投信", fund) or any(v > 20000 for _, v in rows):
                continue
            cur = data.get(x["fundCode"]) or {"名前": fund, "推移": []}
            # 有報と半期報告書の推移をつなぐ(同じ期の終わりは新しい書類の値で)
            hist = {e: amt for e, amt in cur.get("推移", [])}
            hist.update({e: amt for e, amt in rows})
            cur["名前"] = fund
            cur["推移"] = sorted([e, v] for e, v in hist.items())[-24:]
            yr = annual([tuple(r) for r in cur["推移"]])
            if yr:
                cur["年間"], cur["から"], cur["まで"] = yr
            cur["出典"] = "EDINET %s %s" % ("有報" if x["docTypeCode"] == "120" else "半期報告書", x["docID"])
            data[x["fundCode"]] = cur
            n += 1
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("{\n" + ",\n".join("  %s: %s" % (json.dumps(k), json.dumps(v, ensure_ascii=False, separators=(",", ":"))) for k, v in sorted(data.items())) + "\n}\n")
    print("分配金を読んだファンド", n, "/ 全", len(data))


if __name__ == "__main__":
    main()
