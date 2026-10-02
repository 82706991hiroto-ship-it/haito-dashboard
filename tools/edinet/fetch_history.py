#!/usr/bin/env python3
"""EDINET の有価証券報告書から、1株配当の長期系列(約13期)を作る。

有報の「主要な経営指標等の推移」には5期分の1株配当と発行済株式数が載る。
1社につき、最新・4年前・8年前・9年前の有報を1本ずつ取り、重なる期で倍率を合わせてつなぐ。

  EDINET_API_KEY=... python3 tools/edinet/fetch_history.py --cache DIR list
  EDINET_API_KEY=... python3 tools/edinet/fetch_history.py --cache DIR fetch
  python3 tools/edinet/fetch_history.py --cache DIR build --out history.json
  python3 tools/edinet/fetch_history.py --cache DIR apply --history history.json --html index.html

出典: EDINET(公共データ利用規約 PDL1.0)。
"""
import argparse, csv, datetime as dt, io, json, os, re, sys, time, zipfile
from concurrent.futures import ThreadPoolExecutor

import requests

API = "https://api.edinet-fsa.go.jp/api/v2"
RELS = ["CurrentYear", "Prior1Year", "Prior2Year", "Prior3Year", "Prior4Year"]
NICE = [1.1, 1.2, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 15, 20, 25, 30, 40, 50, 100]

# 最新・4年前・8年前・9年前の有報を拾うための提出日の範囲
WINDOWS = {
    "latest": ("2025-06-01", None),
    "back4": ("2021-06-01", "2022-12-31"),
    "back8": ("2017-06-01", "2018-12-31"),
    # EDINETは約10年で書類を消すので、9年前の有報で取れるのはこのあたりまで
    "back9": ("2016-10-01", "2017-12-31"),
}


def key():
    k = os.environ.get("EDINET_API_KEY")
    if not k:
        sys.exit("EDINET_API_KEY が設定されていません")
    return k


def get(url, params, tries=5):
    params = dict(params, **{"Subscription-Key": key()})
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=90)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(2 ** i)
    return None


def days(start, end):
    d = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end) if end else dt.date.today()
    while d <= e:
        if d.weekday() < 5:
            yield d.isoformat()
        d += dt.timedelta(days=1)


# ---------- list: 日付ごとの書類一覧から有価証券報告書を集める ----------
def cmd_list(cache):
    os.makedirs(os.path.join(cache, "lists"), exist_ok=True)
    dates = sorted({d for s, e in WINDOWS.values() for d in days(s, e)})

    def one(d):
        path = os.path.join(cache, "lists", d + ".json")
        if os.path.exists(path):
            return
        r = get(API + "/documents.json", {"date": d, "type": 2})
        rows = (r.json().get("results") or []) if r is not None else []
        keep = [
            {k: x[k] for k in ("docID", "secCode", "filerName", "periodEnd", "submitDateTime")}
            for x in rows
            if x.get("docTypeCode") == "120" and x.get("ordinanceCode") == "010"
            and x.get("secCode") and x.get("csvFlag") == "1" and x.get("withdrawalStatus") == "0"
        ]
        with open(path, "w") as f:
            json.dump(keep, f, ensure_ascii=False)

    with ThreadPoolExecutor(6) as ex:
        for i, _ in enumerate(ex.map(one, dates)):
            if i % 100 == 0:
                print("list", i, "/", len(dates), flush=True)


def load_lists(cache):
    out = []
    for fn in sorted(os.listdir(os.path.join(cache, "lists"))):
        with open(os.path.join(cache, "lists", fn)) as f:
            out.extend(json.load(f))
    return out


def code_of(sec):
    return sec[:4].upper()


def select(cache):
    """銘柄ごとに、最新の有報と、その期末から4年前・8年前・9年前の期末の有報を選ぶ。"""
    by = {}
    for x in load_lists(cache):
        if not x.get("periodEnd"):
            continue
        by.setdefault(code_of(x["secCode"]), []).append(x)
    picks = {}
    for code, docs in by.items():
        docs.sort(key=lambda x: (x["periodEnd"], x["submitDateTime"]))
        latest = docs[-1]
        if latest["periodEnd"] < "2025-01-01":
            continue
        le = dt.date.fromisoformat(latest["periodEnd"])
        chosen = [latest]
        for back in (4, 8, 9):
            target = le.replace(year=le.year - back) if not (le.month == 2 and le.day == 29) else le.replace(year=le.year - back, day=28)
            cands = [x for x in docs if abs((dt.date.fromisoformat(x["periodEnd"]) - target).days) <= 20]
            if not cands:
                break
            chosen.append(cands[-1])
        picks[code] = chosen
    return picks


# ---------- fetch: 選んだ有報のCSVから配当と株数を抜き出す ----------
def parse_csv(text):
    rows = csv.reader(io.StringIO(text), delimiter="\t")
    vals = {}
    fyend = None
    for r in rows:
        if len(r) < 9:
            continue
        el, ctx, v = r[0], r[2], r[8]
        if el == "jpdei_cor:CurrentFiscalYearEndDateDEI":
            fyend = v
        elif el in ("jpcrp_cor:DividendPaidPerShareSummaryOfBusinessResults",
                    "jpcrp_cor:InterimDividendPaidPerShareSummaryOfBusinessResults",
                    "jpcrp_cor:TotalNumberOfIssuedSharesSummaryOfBusinessResults"):
            vals[(el.split(":")[1], ctx)] = v

    def num(s):
        try:
            return float(str(s).replace(",", ""))
        except ValueError:
            return None

    def pick(el, rel, kind):
        for ctx in (rel + kind + "_NonConsolidatedMember", rel + kind):
            if (el, ctx) in vals:
                return num(vals[(el, ctx)])
        return None

    periods = []
    for i, rel in enumerate(RELS):
        periods.append({
            "back": i,
            "dps": pick("DividendPaidPerShareSummaryOfBusinessResults", rel, "Duration"),
            "shares": pick("TotalNumberOfIssuedSharesSummaryOfBusinessResults", rel, "Instant"),
            "interim": pick("InterimDividendPaidPerShareSummaryOfBusinessResults", rel, "Duration"),
        })
    return {"fyend": fyend, "periods": periods}


def cmd_fetch(cache):
    os.makedirs(os.path.join(cache, "docs"), exist_ok=True)
    picks = select(cache)
    ids = sorted({d["docID"] for docs in picks.values() for d in docs})
    print("companies", len(picks), "documents", len(ids), flush=True)

    def one(doc_id):
        path = os.path.join(cache, "docs", doc_id + ".json")
        if os.path.exists(path):
            return
        r = get(API + "/documents/" + doc_id, {"type": 5})
        out = {"error": "download"}
        if r is not None and r.content[:2] == b"PK":
            try:
                z = zipfile.ZipFile(io.BytesIO(r.content))
                name = next(n for n in z.namelist() if re.search(r"XBRL_TO_CSV/jpcrp.*asr.*\.csv$", n))
                out = parse_csv(z.read(name).decode("utf-16"))
            except (StopIteration, zipfile.BadZipFile, UnicodeDecodeError):
                out = {"error": "parse"}
        with open(path, "w") as f:
            json.dump(out, f)

    with ThreadPoolExecutor(6) as ex:
        for i, _ in enumerate(ex.map(one, ids)):
            if i % 250 == 0:
                print("fetch", i, "/", len(ids), flush=True)


# ---------- build: 株式分割を割り戻して1本の系列にする ----------
def snap(ratio):
    """発行済株式数の比を、きりのいい分割倍率に寄せる。寄らなければ None。"""
    if ratio is None or ratio <= 0:
        return None
    if abs(ratio - 1) <= 0.05:
        return 1.0
    for n in NICE:
        if abs(ratio / n - 1) <= 0.06:
            return float(n)
    return None


def within_filing(periods):
    """1本の有報の5期分を、その有報の当期の株数基準にそろえる(古い順のリストを返す)。

    過去期の1株配当は、分割前の実額のまま載っている会社と、分割を反映して修正済みの会社がある。
    株数が増えた期の前後で配当がほぼ倍率ぶん下がっていれば実額とみなして割り戻し、
    下がっていなければ修正済みとみなしてそのまま使う。
    """
    ps = sorted(periods, key=lambda p: -p["back"])  # 古い順
    vals = [p["dps"] for p in ps]
    shares = [p["shares"] for p in ps]
    # 期の途中で分割した年は、中間配当が分割前・期末配当が分割後の株数で払われ、年間の値が混ざる。
    # 中間配当が分割前の水準(前期の年間配当の半分前後)なら、中間配当を倍率で割り戻して期末と足す
    mixed = [False] * len(ps)
    for t in range(1, len(ps)):
        it = ps[t].get("interim")
        f = snap(shares[t] / shares[t - 1]) if shares[t] and shares[t - 1] else 1.0
        if (f and f >= 1.5 and it and vals[t] and vals[t - 1] and 0 < it < vals[t]
                and it / vals[t - 1] > 0.5 / f ** 0.5):
            vals[t] = round(it / f + (vals[t] - it), 2)
            mixed[t] = True
    out = [None] * len(ps)
    factor = 1.0
    out[-1] = vals[-1]
    for t in range(len(ps) - 2, -1, -1):
        if vals[t] is None or vals[t + 1] is None:
            break
        f = snap(shares[t + 1] / shares[t]) if shares[t] and shares[t + 1] else 1.0
        if f is None:
            break  # 株数が不自然に動いた(合併・併合など)ので、ここより古い期は使わない
        if f > 1 and vals[t] > 0 and (mixed[t + 1] or vals[t + 1] / vals[t] < 0.75):
            factor *= f
        out[t] = vals[t] / factor
    return [(p["back"], v, s) for p, v, s in zip(ps, out, shares)]


def fy_key(fyend, back):
    d = dt.date.fromisoformat(fyend)
    return "%04d-%02d" % (d.year - back, d.month)


def build_code(docs_parsed):
    """最新→4年前→8年前の順に並んだ解析結果から、新しい順の系列を作る。"""
    series = {}  # fy -> value (最新の有報の株数基準)
    shares = {}  # fy -> その期末の発行済株式数(生の値)
    for i, doc in enumerate(docs_parsed):
        if not doc or doc.get("error") or not doc.get("fyend"):
            break
        rows = within_filing(doc["periods"])
        vals = {fy_key(doc["fyend"], back): v for back, v, _ in rows if v is not None}
        for back, _, sh in rows:
            shares.setdefault(fy_key(doc["fyend"], back), sh)
        if not vals:
            break
        if i == 0:
            series.update(vals)
            continue
        # 重なる期(この有報の当期)で、新しい有報の値に倍率を合わせる
        overlap = fy_key(doc["fyend"], 0)
        a, b = series.get(overlap), vals.get(overlap)
        if not a or not b:
            break
        k = a / b
        if abs(k - 1) <= 0.02:
            k = 1.0
        else:
            inv = snap(1 / k)
            if inv is None or inv == 1.0:
                break  # 重なる期の値が食い違うので、古い有報はつながない
            k = 1 / inv
        for fy, v in vals.items():
            if fy < overlap:
                series[fy] = v * k
    keys = sorted(series, reverse=True)
    # 期が1年ずつ並んでいない(決算期変更など)ところで切る
    out = []
    for j, fy in enumerate(keys):
        if j > 0:
            y0, m0 = map(int, keys[j - 1].split("-"))
            y1, m1 = map(int, fy.split("-"))
            if (y0 - y1) * 12 + (m0 - m1) != 12:
                break
        out.append(round(series[fy], 2))
    # 期の途中で分割した年は、中間(分割前)と期末(分割後)の混ざった値になる(トヨタ148円など)。
    # 株数が跳ねた期の前後1期以内で40%を超えて下がっていたら、その混在年より古い期を外す。
    def split_near(j):
        for a in range(max(1, j - 1), min(len(keys), j + 2)):
            s_new, s_old = shares.get(keys[a - 1]), shares.get(keys[a])
            if s_new and s_old:
                f = snap(s_new / s_old)
                if f is None or f > 1:
                    return True
        return False
    for j in range(1, len(out)):
        if out[j] > 0 and out[j - 1] / out[j] < 0.6 and split_near(j):
            out = out[:j]
            break
    # 3倍を超える増配は上場前の年度などの混入とみなし、それより古い期を外す
    for j in range(1, len(out)):
        if out[j] > 0 and out[j - 1] / out[j] > 3:
            out = out[:j]
            break
    return out


def cmd_build(cache, out_path):
    picks = select(cache)
    result = {}
    for code, docs in picks.items():
        parsed = []
        for d in docs:
            path = os.path.join(cache, "docs", d["docID"] + ".json")
            parsed.append(json.load(open(path)) if os.path.exists(path) else None)
        s = build_code(parsed)
        if s:
            result[code] = s
    with open(out_path, "w") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    lens = {}
    for s in result.values():
        lens[len(s)] = lens.get(len(s), 0) + 1
    print("codes", len(result), "lengths", dict(sorted(lens.items())))


# ---------- apply: index.html の CODE_INFO_MAP に長い系列を入れる ----------
def cmd_apply(history_path, html_path):
    hist = json.load(open(history_path))
    html = open(html_path, encoding="utf-8").read()
    m = re.search(r"var CODE_INFO_MAP = (\{.*?\});\n", html)
    info = json.loads(m.group(1))
    stats = {"extended": 0, "kept_mismatch": 0, "added": 0, "no_history": 0}
    for code, v in info.items():
        new = hist.get(code)
        if not new or len(new) < 2:
            stats["no_history"] += 1
            continue
        old = v[3] if len(v) > 3 and isinstance(v[3], list) else None
        if old:
            # 既存の取り込み(分割の個別対応済み)と重なる期が一致するときだけ延ばす
            ok = len(new) >= len(old) and all(
                abs(a - b) <= max(0.02 * abs(b), 0.011) for a, b in zip(new, old))
            if not ok:
                stats["kept_mismatch"] += 1
                continue
            if len(new) > len(old):
                stats["extended"] += 1
            v[3] = new
        else:
            # 既存の取り込みで配当を入れなかった銘柄(無配・分割の混在年など)には足さない
            stats["added"] += 0
    body = json.dumps(info, ensure_ascii=False, separators=(",", ":"))
    html = html[:m.start(1)] + body + html[m.end(1):]
    open(html_path, "w", encoding="utf-8").write(html)
    print(stats)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("cmd", choices=["list", "fetch", "build", "apply"])
    ap.add_argument("--out", default="history.json")
    ap.add_argument("--history", default="history.json")
    ap.add_argument("--html", default="index.html")
    a = ap.parse_args()
    if a.cmd == "list":
        cmd_list(a.cache)
    elif a.cmd == "fetch":
        cmd_fetch(a.cache)
    elif a.cmd == "build":
        cmd_build(a.cache, a.out)
    else:
        cmd_apply(a.history, a.html)


if __name__ == "__main__":
    main()
