#!/usr/bin/env python3
"""決算の途中で決まった株式分割・併合を、EDINETの半期報告書・有報の注記から見つけて data/splits.json に足す。

内蔵データの1株配当は有報から作るので、期の途中で分割した会社は次の有報が出るまで分割前の値のまま残る。
半期報告書(と有報)の「重要な後発事象」「1株当たり情報」には分割の比率と効力発生日が書かれるので、
各社の最新の有報の期末より後に効力が出る分割を拾う。

  EDINET_API_KEY=... python3 tools/edinet/splits_scan.py --days 45            # 見つけたものを表示
  EDINET_API_KEY=... python3 tools/edinet/splits_scan.py --days 45 --write    # data/splits.json に足す
"""
import argparse, datetime as dt, io, json, os, re, sys, unicodedata, zipfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_history as fh  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE = os.path.join(ROOT, "tools", "edinet", "state.json")
SPLITS = os.path.join(ROOT, "data", "splits.json")
HTML = os.path.join(ROOT, "index.html")

DATE = r"(\d{4})年(\d{1,2})月(\d{1,2})日(?:\([^)]{1,3}\))?"
# 効力発生日の書き方は2通りだけを拾う(取締役会の日・基準日などを取り違えないように)
#  ・「効力発生日 2026年7月1日」
#  ・「2026年7月1日付で(普通株式1株につき2株の割合で)株式分割」「2026年7月1日を効力発生日として…株式分割」
LABELED = re.compile(r"効力発生日[\s::]{0,3}" + DATE)
INLINE = re.compile(DATE + r"(?:付で|付けで|をもって|を効力発生日として|を効力発生日とし)[^。]{0,40}?(?:株式分割|株式併合|1株につき|株を1株に)")
RATIO_SPLIT = re.compile(r"1株につき[、,]?\s*(\d+(?:\.\d+)?)株")
RATIO_MERGE = re.compile(r"(\d+)株を1株に(?:併合|株式併合)")


def filings(days):
    """直近 days 日に提出された有報・半期報告書(証券コードのあるもの)。"""
    today = dt.date.today()
    dates = [(today - dt.timedelta(days=i)).isoformat() for i in range(days)]

    def one(d):
        r = fh.get(fh.API + "/documents.json", {"date": d, "type": 2})
        return (r.json().get("results") or []) if r is not None else []

    out = []
    with ThreadPoolExecutor(4) as ex:
        for rows in ex.map(one, dates):
            for x in rows:
                if (x.get("docTypeCode") in ("120", "160") and x.get("ordinanceCode") == "010" and x.get("secCode")
                        and x.get("csvFlag") == "1" and x.get("withdrawalStatus") == "0"):
                    out.append(x)
    return out


def text_of(doc_id):
    r = fh.get(fh.API + "/documents/" + doc_id, {"type": 5})
    if r is None or r.content[:2] != b"PK":
        return ""
    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        parts = [z.read(n).decode("utf-16") for n in z.namelist()
                 if n.endswith(".csv") and "/jpcrp" in n]
    except (zipfile.BadZipFile, UnicodeDecodeError):
        return ""
    return unicodedata.normalize("NFKC", "\n".join(parts))


def find_splits(text):
    """本文から分割・併合を拾い {効力発生日: 比率} で返す。比率は 1株→N株 のN(併合は 1/N)。

    有報・半期報告書は同じ分割を何か所にも書くので、いちばん多く出てくる日付を効力発生日とする
    (配当の効力発生日や総会の日が近くに書かれていても取り違えないように)。
    """
    votes = {}
    for m in re.finditer(r"株式分割|株式併合", text):
        win = text[max(0, m.start() - 300): m.end() + 900]
        rs, rm = RATIO_SPLIT.search(win), RATIO_MERGE.search(win)
        if m.group(0) == "株式分割" and rs:
            ratio = float(rs.group(1))
        elif m.group(0) == "株式併合" and rm and float(rm.group(1)) > 1:
            ratio = round(1 / float(rm.group(1)), 6)
        else:
            continue
        if ratio == 1 or ratio <= 0 or ratio > 100:
            continue
        for pat in (LABELED, INLINE):
            for d in pat.finditer(win):
                if pat is LABELED and "配当" in win[max(0, d.start() - 40): d.start()]:
                    continue  # 「配当の効力発生日」
                try:
                    day = dt.date(int(d.group(1)), int(d.group(2)), int(d.group(3))).isoformat()
                except ValueError:
                    continue
                v = votes.setdefault((day, ratio), 0)
                votes[(day, ratio)] = v + (2 if pat is INLINE else 1)
    if not votes:
        return {}
    # 日付ごとに票を数え、いちばん多いもの(と、それに迫る別の分割)を残す
    best = max(votes.values())
    return {day: ratio for (day, ratio), v in votes.items() if v >= max(2, best * 0.5)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--cache", help="読んだ書類ごとの結果を残すフォルダ(やり直しのとき読み直さない)")
    a = ap.parse_args()

    html = open(HTML, encoding="utf-8").read()
    info = json.loads(re.search(r"var CODE_INFO_MAP = (\{.*?\});\n", html).group(1))
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    splits = json.load(open(SPLITS, encoding="utf-8"))

    docs = filings(a.days)
    # 最新の有報の期末より後に出た書類だけ(それより前の分割は有報の配当にもう反映されている)
    todo, asr_day = [], {}
    for x in docs:
        code = x["secCode"][:4].upper()
        fy = state.get(code)
        if code not in info or not fy:
            continue
        sub = (x.get("submitDateTime") or "")[:10]
        if x["docTypeCode"] == "120" and (x.get("periodEnd") or "") == fy:
            asr_day[code] = sub
        if sub > fy:
            todo.append((code, x))
    print("有報・半期報告書", len(docs), "件のうち、最新の有報の期末より後に出た", len(todo), "件を読みます", flush=True)

    def scan(doc_id):
        path = a.cache and os.path.join(a.cache, doc_id + ".json")
        if path and os.path.exists(path):
            return json.load(open(path))
        try:
            got = find_splits(text_of(doc_id))
        except Exception as e:  # 1件の読み違いで全体を止めない
            print("読めず", doc_id, e, flush=True)
            return {}
        if path:
            json.dump(got, open(path, "w"))
        return got

    if a.cache:
        os.makedirs(a.cache, exist_ok=True)
    hits = {}
    with ThreadPoolExecutor(4) as ex:
        for (code, x), got in zip(todo, ex.map(lambda t: scan(t[1]["docID"]), todo)):
            for day, ratio in got.items():
                if day <= state[code]:
                    continue
                cur = splits.get(code)
                known = [e.get("効力発生日") for e in (cur if isinstance(cur, list) else [cur]) if isinstance(e, dict)]
                if day in known or (code, day) in hits:
                    continue
                kind = "有報" if x["docTypeCode"] == "120" else "半期報告書"
                hits[(code, day)] = {
                    "名前": info[code][0], "効力発生日": day, "比率": int(ratio) if ratio == int(ratio) else ratio,
                    "出典": "EDINET %s %s(%s提出)の注記" % (kind, x["docID"], (x.get("submitDateTime") or "")[:10]),
                }
                # 効力発生が最新の有報の提出より前なら、その有報のEPS・BPSはもう分割後の株数で計算されている
                if asr_day.get(code) and day <= asr_day[code]:
                    hits[(code, day)]["EPS調整済"] = True

    for (code, day), e in sorted(hits.items()):
        print("%s %s %s 1株→%s株  %s" % (code, e["名前"], day, e["比率"], e["出典"]))
    print("新しく見つかった分割・併合", len(hits), "件")
    if not a.write or not hits:
        return
    # 1社1件の書き方に合わせる(同じ会社に既にあるときは見送って知らせる)
    added = 0
    for (code, day), e in sorted(hits.items()):
        if code in splits:
            print("既に別の分割が入っているので手で確認:", code, day)
            continue
        splits[code] = e
        added += 1
    head = {k: v for k, v in splits.items() if k.startswith("_")}
    body = {k: v for k, v in splits.items() if not k.startswith("_")}
    lines = ["{"] + ["  %s: %s," % (json.dumps(k, ensure_ascii=False), json.dumps(v, ensure_ascii=False)) for k, v in list(head.items()) + list(body.items())]
    lines[-1] = lines[-1].rstrip(",")
    open(SPLITS, "w", encoding="utf-8").write("\n".join(lines) + "\n}\n")
    print("data/splits.json に", added, "件足しました")


if __name__ == "__main__":
    main()
