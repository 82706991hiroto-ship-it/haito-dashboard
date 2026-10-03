#!/usr/bin/env python3
"""直近に提出された有価証券報告書で、index.html の内蔵データ(CODE_INFO_MAP)を新しい期に進める。

毎月 GitHub Actions(.github/workflows/edinet-monthly.yml)で動かす。手元で試すときは:

  EDINET_API_KEY=... python3 tools/edinet/monthly.py --days 45 [--dry-run]

- 1株配当: 新しい期の配当を先頭に足す。有報の前期・前々期の値が今の系列と合うときだけ足し、
  分割で倍率がずれていれば今の系列を割り戻してからつなぐ。合わなければ有報の5期分に置き換える。
- 配当性向: 当期の値に置き換える。
- 新しく上場した会社: EDINETコードリストの社名・業種と、決算月(中間配当があればその月も)で足す。
- どの有報まで取り込んだかは tools/edinet/state.json(証券コード → 期末日)に残す。

出典: EDINET(公共データ利用規約 PDL1.0)。
"""
import argparse, csv, datetime as dt, io, json, os, re, sys, zipfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_history as fh  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE = os.path.join(ROOT, "tools", "edinet", "state.json")
MANUAL = os.path.join(ROOT, "data", "manual-dividends.json")
MAX_PERIODS = 35  # 自動は最大14期。手で足した過去の分も含めて残す上限
CODELIST = "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip"


def close(a, b):
    return abs(a - b) <= max(0.02 * abs(b), 0.011)


def recent_filings(days):
    """直近 days 日に提出された有報(証券コードのあるもの)。同じ会社は新しい期の1本だけ。"""
    today = dt.date.today()
    dates = [today - dt.timedelta(days=i) for i in range(days)]
    dates = [d.isoformat() for d in dates if d.weekday() < 5]

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
                    if code not in by or (x["periodEnd"], x["submitDateTime"]) > (by[code]["periodEnd"], by[code]["submitDateTime"]):
                        by[code] = x
    return by


def parse(text):
    """配当と株数(fetch_history と同じ読み方)に、当期の配当性向と中間配当を足す。"""
    base = fh.parse_csv(text)
    extra = {}
    for r in csv.reader(io.StringIO(text), delimiter="\t"):
        if len(r) >= 9 and r[0] in ("jpcrp_cor:PayoutRatioSummaryOfBusinessResults",
                                    "jpcrp_cor:InterimDividendPaidPerShareSummaryOfBusinessResults"):
            extra[(r[0].split(":")[1], r[2])] = r[8]

    def cur(el):
        for ctx in ("CurrentYearDuration_NonConsolidatedMember", "CurrentYearDuration"):
            try:
                return float(str(extra.get((el, ctx), "")).replace(",", ""))
            except ValueError:
                continue
        return None

    base["payout"] = cur("PayoutRatioSummaryOfBusinessResults")
    base["interim"] = cur("InterimDividendPaidPerShareSummaryOfBusinessResults")
    return base


def download(doc_id):
    r = fh.get(fh.API + "/documents/" + doc_id, {"type": 5})
    if r is None or r.content[:2] != b"PK":
        return None
    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        name = next(n for n in z.namelist() if re.search(r"XBRL_TO_CSV/jpcrp.*asr.*\.csv$", n))
        return parse(z.read(name).decode("utf-16"))
    except (StopIteration, zipfile.BadZipFile, UnicodeDecodeError):
        return None


def new_series(parsed):
    """有報1本の1株配当を、新しい順・当期の株数基準で(fetch_history の build と同じ切り方)。"""
    if not parsed.get("fyend"):
        return []
    return fh.build_code([parsed])


def merge(old, new, known):
    """今の系列 old(新しい順)に、有報の系列 new(新しい順)をつなぐ。(結果, どうしたか) を返す。

    known: この有報より前の期まで取り込み済みと分かっているか(state.json にある)。
    分からないときは、もう取り込み済み(先頭2期が一致)かどうかを先に見る。
    """
    if not new:
        return old, "配当なし"
    if not old:
        return new, "新規"
    if not known and len(new) >= 2 and len(old) >= 2 and close(new[0], old[0]) and close(new[1], old[1]):
        return old, "取り込み済み"
    if len(new) >= 2:
        k = new[1] / old[0] if old[0] else None
        if k and close(new[1], old[0]):
            k = 1.0
        else:
            f = fh.snap(1 / k) if k else None
            k = 1 / f if f and f != 1.0 else None
        if k:
            scaled = [round(v * k, 2) for v in old]
            if len(new) < 3 or len(scaled) < 2 or close(new[2], scaled[1]):
                return [new[0]] + scaled, "1期追加" if k == 1.0 else "分割を割り戻して1期追加"
    return new, "食い違いのため有報の%d期分に置き換え" % len(new)


def code_list():
    try:
        import requests
        r = requests.get(CODELIST, timeout=90)
    except Exception:
        r = None
    if r is None or r.status_code != 200 or r.content[:2] != b"PK":
        print("EDINETコードリストを取得できませんでした。新規上場の会社は社名・業種が分からないので来月に回します")
        return {}
    z = zipfile.ZipFile(io.BytesIO(r.content))
    text = z.read(next(n for n in z.namelist() if n.lower().endswith(".csv"))).decode("cp932")
    rows = list(csv.reader(io.StringIO(text)))
    head = next(i for i, r in enumerate(rows) if "証券コード" in r)
    h = rows[head]
    ic, iname, isec = h.index("証券コード"), h.index("提出者名"), h.index("提出者業種")
    out = {}
    for r in rows[head + 1:]:
        if len(r) > max(ic, iname, isec) and r[ic].strip():
            out[r[ic].strip()[:4].upper()] = (r[iname].strip(), r[isec].strip())
    return out


def short_name(n):
    return re.sub(r"^株式会社|株式会社$", "", n.strip()).strip()


def months_of(fyend, interim):
    m = int(fyend[5:7])
    ms = [m]
    if interim and interim > 0:
        ms.append((m + 5) % 12 + 1)
    return sorted(ms)


def fy_key(s):
    """「2011-03」「2011/3」「2011年3月」などを「2011-03」に"""
    m = re.match(r"^\s*(\d{4})\D+(\d{1,2})", str(s))
    return "%s-%02d" % (m.group(1), int(m.group(2))) if m else None


def apply_manual(info, state):
    """data/manual-dividends.json の過去の1株配当を、自動の記録の古い側につなぐ。何度動かしても同じ結果になる。"""
    if not os.path.exists(MANUAL):
        return {}
    data = json.load(open(MANUAL, encoding="utf-8"))
    log = {}
    for code, entry in data.items():
        if code.startswith("_"):
            continue
        code = code.strip().upper()
        divs = {fy_key(k): float(v) for k, v in ((entry or {}).get("配当") or {}).items() if fy_key(k) and v not in (None, "")}
        v = info.get(code)
        if not divs or not v or len(v) < 4 or not v[3] or not state.get(code):
            log.setdefault("自動の記録か決算期が分からず見送り", []).append(code)
            continue
        y, mth = int(state[code][:4]), int(state[code][5:7])
        labels = ["%d-%02d" % (y - i, mth) for i in range(len(v[3]))]  # 新しい順
        bad = [k for k, val in zip(labels, v[3]) if k in divs and not close(divs[k], val)]
        if bad:
            log.setdefault("自動の記録と食い違い(%s)のため見送り" % ",".join(bad), []).append(code)
            continue
        added, odd = 0, None
        oy = y - len(v[3])
        while "%d-%02d" % (oy, mth) in divs and len(v[3]) < MAX_PERIODS:
            val = divs["%d-%02d" % (oy, mth)]
            newer = v[3][-1]
            # 隣の期と5倍以上違うのは、分割の割り戻し忘れなどの入力ミスとみなして止める
            if newer > 0 and val > 0 and not (0.2 <= val / newer <= 5):
                odd = "%d-%02d" % (oy, mth)
                break
            v[3].append(round(val, 2))
            oy -= 1
            added += 1
        older = [k for k in divs if k < "%d-%02d" % (oy + 1, mth)]
        if odd:
            log.setdefault("隣の期と大きく違うので止めた(分割調整を確認)", []).append("%s(%s)" % (code, odd))
        elif added:
            log.setdefault("過去の配当を足した", []).append("%s(+%d期)" % (code, added))
        elif older:
            log.setdefault("自動の記録の一番古い期(%s)の1つ前から続けて書いてください" % labels[-1], []).append(code)
        else:
            log.setdefault("反映済み", []).append(code)
    return log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--html", default=os.path.join(ROOT, "index.html"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--manual-only", action="store_true", help="EDINETは見ず、手で足した過去の配当だけ反映する")
    a = ap.parse_args()

    html = open(a.html, encoding="utf-8").read()
    m = re.search(r"var CODE_INFO_MAP = (\{.*?\});\n", html)
    info = json.loads(m.group(1))
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}

    filings = {} if a.manual_only else recent_filings(a.days)
    todo = [(c, x) for c, x in filings.items()
            if re.match(r"^[1-9][0-9A-Z]{3}$", c) and state.get(c, "") < x["periodEnd"]]
    print("有報", len(filings), "件のうち、未取り込みの期", len(todo), "件", flush=True)
    names = code_list() if any(c not in info for c, _ in todo) else {}
    if any(c not in info for c, _ in todo) and not names:
        todo = [(c, x) for c, x in todo if c in info]

    log = {}
    with ThreadPoolExecutor(4) as ex:
        for (code, x), parsed in zip(todo, ex.map(lambda t: download(t[1]["docID"]), todo)):
            if not parsed or not parsed.get("fyend"):
                log.setdefault("解析できず", []).append(code)
                continue
            new = new_series(parsed)
            v = info.get(code)
            if v is None:
                name, sector = names.get(code, (x.get("filerName") or "", ""))
                if not sector:
                    log.setdefault("業種が分からず見送り", []).append(code)
                    continue
                v = info[code] = [short_name(name), sector, months_of(parsed["fyend"], parsed.get("interim"))]
                log.setdefault("新規上場", []).append(code)
            old = v[3] if len(v) > 3 and isinstance(v[3], list) else []
            # 前は配当を入れていなかった銘柄(無配・分割の混在年など)は、新しい有報で配当があれば入れる
            merged, how = merge(old, new, code in state)
            if merged:
                if len(v) < 3:
                    v.append(months_of(parsed["fyend"], parsed.get("interim")))
                while len(v) < 5:
                    v.append(None)
                v[3] = merged[:MAX_PERIODS]
                if parsed.get("payout") is not None:
                    v[4] = round(parsed["payout"], 3)
                elif v[4] is None:
                    v[4] = 0
            log.setdefault(how, []).append(code)
            state[code] = x["periodEnd"]

    for how, codes in apply_manual(info, state).items():
        log.setdefault("手入力: " + how, []).extend(codes)
    for how, codes in sorted(log.items()):
        print("%s: %d社 %s%s" % (how, len(codes), " ".join(codes[:30]), " …" if len(codes) > 30 else ""))
    if a.dry_run:
        return
    body = json.dumps(info, ensure_ascii=False, separators=(",", ":"))
    html = html[:m.start(1)] + body + html[m.end(1):]
    open(a.html, "w", encoding="utf-8").write(html)
    with open(STATE, "w") as f:
        json.dump(dict(sorted(state.items())), f, separators=(",", ":"))
        f.write("\n")


if __name__ == "__main__":
    main()
