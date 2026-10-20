#!/usr/bin/env python3
"""有価証券報告書の決算期間(EDINETの書類一覧の periodStart / periodEnd)から、12か月でない期を探す。

持株会社を作った最初の期(半年など)や、決算期を変えた年(9か月・15か月など)は、1株配当も
その長さのぶんだけ少なく(多く)なる。そのまま比べると「増配」「減配」「連続増配の途切れ」に見えるので、
data/irregular-periods.json に残し、index.html の IRREG_MAP(内蔵の1株配当の何期前か)に書く。
画面側は、その期を増配・減配・連続増配の判断から外す(配当の値は変えない)。

  EDINET_API_KEY=... python3 tools/edinet/period_scan.py            # 約10年分の書類一覧を見る(初回)
  EDINET_API_KEY=... python3 tools/edinet/period_scan.py --days 45  # 直近だけ見て足す(毎週)

書類の中身は読まない(一覧の日付だけ)。出典: EDINET(公共データ利用規約 PDL1.0)。
"""
import argparse, datetime as dt, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_history as fh  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "irregular-periods.json")
STATE = os.path.join(ROOT, "tools", "edinet", "state.json")
# 12か月(365日)からこれだけ外れたら変則の期とみる(うるう年・週末締めの会社のずれは吸収する)
SHORT_DAYS, LONG_DAYS = 340, 390


def period_list(start, end):
    """日付ごとの書類一覧から、有価証券報告書の (コード, 期首, 期末, 提出日時) を集める。
    取れなかった日(混み合い・一時的な失敗)は、間をあけて少ない並列でやり直す。年ごとの件数を出して抜けに気づけるようにする"""
    dates = list(fh.days(start, end))

    def one(d):
        r = fh.get(fh.API + "/documents.json", {"date": d, "type": 2})
        if r is None:
            return d, None
        try:
            j = r.json()
        except ValueError:
            return d, None
        # 混み合っているときは 200 でも本文の status がエラーで results が空になる。保存期間外(404)は「無し」とみる
        st = str((j.get("metadata") or {}).get("status") or "")
        if st == "404":
            return d, []
        rows = j.get("results")
        if st != "200" or rows is None:
            return d, None
        return d, [(x["secCode"][:4].upper(), x.get("periodStart"), x.get("periodEnd"), x.get("submitDateTime") or "")
                   for x in rows
                   if x.get("docTypeCode") == "120" and x.get("ordinanceCode") == "010" and x.get("secCode")
                   and x.get("withdrawalStatus") == "0" and x.get("periodStart") and x.get("periodEnd")]

    got, todo = {}, dates
    for rnd, workers in enumerate((4, 2, 1, 1)):
        failed = []
        with ThreadPoolExecutor(workers) as ex:
            for i, (d, rows) in enumerate(ex.map(one, todo)):
                if rows is None:
                    failed.append(d)
                else:
                    got[d] = rows
                if i % 200 == 0:
                    print("書類一覧(%d回目)" % (rnd + 1), i, "/", len(todo), "取れなかった日", len(failed), flush=True)
        todo = failed
        if not todo:
            break
        time.sleep(30)
    if todo:
        print("取れなかった日", len(todo), "日:", " ".join(todo[:20]), "…" if len(todo) > 20 else "", flush=True)
    per_year = {}
    for d, rows in got.items():
        per_year[d[:4]] = per_year.get(d[:4], 0) + len(rows)
    print("年ごとの有報の件数:", " ".join("%s:%d" % kv for kv in sorted(per_year.items())), flush=True)
    return [x for rows in got.values() for x in rows], todo


def span_days(start, end):
    return (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 1


def merge(data, rows):
    """銘柄ごとに期(期末)を集め、変則の期があれば残す。同じ期末は新しい提出(訂正後)を使う。"""
    by = {}
    for code, s, e, sub in rows:
        if not re.match(r"^[1-9][0-9A-Z]{3}$", code):
            continue
        cur = by.setdefault(code, {}).get(e)
        if not cur or sub > cur[1]:
            by[code][e] = (s, sub)
    for code, periods in by.items():
        old = data.get(code) or {"periods": [], "irregular": []}
        ends = sorted(set(old["periods"]) | set(periods), reverse=True)
        irr = {x["end"]: x for x in old["irregular"]}
        for e, (s, _) in periods.items():
            n = span_days(s, e)
            if n < SHORT_DAYS or n > LONG_DAYS:
                irr[e] = {"start": s, "end": e, "days": n, "months": round(n / 30.44, 1)}
            else:
                irr.pop(e, None)
        if irr:
            data[code] = {"periods": ends, "irregular": sorted(irr.values(), key=lambda x: x["end"], reverse=True)}
        elif code in data:
            del data[code]
    return data


def month_index(d):
    return int(d[:4]) * 12 + int(d[5:7])


def irreg_map(data, state, info):
    """変則の期が、内蔵の1株配当(新しい順)の何番目かを出す。
    書類一覧で見えた期はその並びで数え、それより新しい期(一覧のあとに内蔵データへ入った期)は12か月ずつ数える。"""
    out = {}
    for code, e in data.items():
        fy, v = state.get(code), info.get(code)
        if not fy or not v or len(v) < 4 or not isinstance(v[3], list) or not v[3]:
            continue
        ends = [p for p in e["periods"] if p <= fy]
        if not ends:
            continue
        newer = round((month_index(fy) - month_index(ends[0])) / 12)
        idx = []
        for x in e["irregular"]:
            if x["end"] > fy or x["end"] not in ends:
                continue
            i = newer + ends.index(x["end"])
            if 0 <= i < len(v[3]):
                idx.append(i)
        if idx:
            out[code] = sorted(set(idx))
    return out


def write_irreg_map(html, info, state):
    data = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    body = json.dumps(dict(sorted(irreg_map(data, state, info).items())), ensure_ascii=False, separators=(",", ":"))
    return re.sub(r"var IRREG_MAP = \{.*?\};\n", lambda _: "var IRREG_MAP = %s;\n" % body, html, count=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=0, help="直近この日数だけ見る(0なら約10年分)")
    ap.add_argument("--html", default=os.path.join(ROOT, "index.html"))
    a = ap.parse_args()
    today = dt.date.today()
    start = (today - dt.timedelta(days=a.days)) if a.days else today.replace(year=today.year - 10)
    rows, missing = period_list(start.isoformat(), None)
    print("有報", len(rows), "件", flush=True)
    if a.days == 0 and len(missing) > 20:
        sys.exit("書類一覧が取れなかった日が多すぎるので、書き込まずに終わります(あとでもう一度動かしてください)")
    data = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    data = merge(data, rows)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(data.items())), f, ensure_ascii=False, indent=1)
        f.write("\n")
    html = open(a.html, encoding="utf-8").read()
    m = re.search(r"var CODE_INFO_MAP = (\{.*?\});\n", html)
    info = json.loads(m.group(1))
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    html = write_irreg_map(html, info, state)
    open(a.html, "w", encoding="utf-8").write(html)
    mp = irreg_map(data, state, info)
    print("変則の期がある銘柄", len(data), "社(内蔵データに当てはめたもの", len(mp), "社)")
    for code in list(mp)[:40]:
        print(" ", code, (info.get(code) or [""])[0], mp[code], [x["start"] + "〜" + x["end"] for x in data[code]["irregular"]])


if __name__ == "__main__":
    main()
