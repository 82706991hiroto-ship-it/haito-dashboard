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
RATIO_SPLIT = re.compile(r"1株(?:につき|当たり)[、,]?\s*(\d[\d,]*(?:\.\d+)?)株|1株を(\d[\d,]*)株に")
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


OTHER = re.compile(r"(?:\(株\)|株式会社|㈱)[^、。\n]{0,30}は、|[^、。\n]{1,30}(?:\(株\)|株式会社|㈱|銀行|ホールディングス|グループ|フィナンシャル)は、")


def other_company(text, pos):
    """pos の「株式分割」が、当社ではない会社(持っている他社の株など)の話か。
    同じ文の中で、分割より前に「(株)○○は、」「○○銀行は、」のような他社の主語があり「当社」が無ければ他社とみる。
    特定投資株式・保有目的の注記の中の文も他社とみる"""
    start = max(text.rfind("。", 0, pos), text.rfind("\n", 0, pos), text.rfind("\"", 0, pos)) + 1
    sent = text[start:pos]
    if re.search(r"特定投資株式|保有目的|純投資", text[max(0, pos - 400):pos]):
        return True
    return bool(OTHER.search(sent)) and "当社" not in sent


def find_splits(text):
    """本文から分割・併合を拾い {効力発生日: 比率} で返す。比率は 1株→N株 のN(併合は 1/N)。

    有報・半期報告書は同じ分割を何か所にも書くので、いちばん多く出てくる日付を効力発生日とする
    (配当の効力発生日や総会の日が近くに書かれていても取り違えないように)。
    """
    votes = {}
    for m in re.finditer(r"株式分割|株式併合", text):
        w0 = max(0, m.start() - 300)
        win = text[w0: m.end() + 900]
        merge = m.group(0) == "株式併合"
        ratios = []
        for r in (RATIO_MERGE if merge else RATIO_SPLIT).finditer(win):
            v = float((r.group(1) or r.group(2) if not merge else r.group(1)).replace(",", ""))
            if merge:
                v = round(1 / v, 6) if v > 1 else 0
            if v and v != 1 and 0 < v <= 1000:
                ratios.append((r.start(), v))
        if not ratios:
            continue
        # 吸収分割・子会社など、当社ではない会社の株式分割の話は除く
        if re.search(r"吸収分割|新設分割|会社分割|承継会社|子会社|完全親会社", text[max(0, m.start() - 200): m.end() + 60]):
            continue
        # 持っている他社の株(政策保有株式・特定投資株式)の注記にある、その会社の分割は除く
        # 例:「(株)滋賀銀行は、2026年4月1日付で普通株式1株につき5株の割合で株式分割を行っており」
        if other_company(text, m.start()):
            continue
        for pat in (LABELED, INLINE):
            for d in pat.finditer(win):
                if pat is LABELED and "配当" in win[max(0, d.start() - 40): d.start()]:
                    continue  # 「配当の効力発生日」
                if other_company(text, w0 + d.start()):
                    continue  # 日付のある文が他社の話
                try:
                    day = dt.date(int(d.group(1)), int(d.group(2)), int(d.group(3))).isoformat()
                except ValueError:
                    continue
                # 比率は、その日付にいちばん近いもの(後ろを少し優先)。窓の中の別の分割の比率と取り違えないように
                ratio = min(ratios, key=lambda r: abs(r[0] - d.end()) if r[0] >= d.end() else (d.start() - r[0]) * 1.5)[1]
                v = votes.setdefault((day, ratio), 0)
                votes[(day, ratio)] = v + (2 if pat is INLINE else 1)
    if not votes:
        return {}
    # 日付ごとに票を数え、いちばん多いもの(と、それに迫る別の分割)を残す
    best = max(votes.values())
    out = {day: ratio for (day, ratio), v in votes.items() if v >= max(2, best * 0.5)}
    # 票の少ない日付も含めた全部(期中の分割と同じものかを見分けるのに使う)
    out["_all"] = sorted([day, ratio] for (day, ratio) in votes)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--cache", help="読んだ書類ごとの結果を残すフォルダ(やり直しのとき読み直さない)")
    ap.add_argument("--verify", action="store_true", help="splits.json の EDINET から拾った分割を、出典の書類で見直す(書き換えない)")
    a = ap.parse_args()
    if a.verify:
        return verify()

    html = open(HTML, encoding="utf-8").read()
    info = json.loads(re.search(r"var CODE_INFO_MAP = (\{.*?\});\n", html).group(1))
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    splits = json.load(open(SPLITS, encoding="utf-8"))

    docs = filings(a.days)
    # 最新の有報の期末より後に出た書類だけ(それより前の分割は有報の配当にもう反映されている)
    todo = []
    for x in docs:
        code = x["secCode"][:4].upper()
        fy = state.get(code)
        if code not in info or not fy:
            continue
        sub = (x.get("submitDateTime") or "")[:10]
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
            # 同じ書類に、同じ比率の分割が最新の有報の期末以前の日付でも書かれていれば、その期の有報で反映済みの分割。
            # 後の日付は読み違い(例: ヨドコウ 2025-07-01 の1株→5株を 2026-04-01 と拾い、二重に割り戻した)とみて足さない
            inside = {r for d, r in (got.get("_all") or got.items()) if d <= state[code]}
            for day, ratio in got.items():
                if day.startswith("_") or day <= state[code]:
                    continue
                if ratio in inside:
                    print("期中の分割と同じ比率なので見送り(手で確認):", code, day, ratio, x["docID"], flush=True)
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
                # 有報のEPS・BPSが分割後の株数かどうかは会社によって違うので、ここでは決めない
                # (チェックシートの側で、1株配当÷EPSと配当性向を比べて判断する)

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


def verify():
    """EDINETの注記から拾った分割を出典の書類で読み直し、同じ比率の分割が期末以前の日付でも書かれているもの
    (期中の分割を後の日付と読み違えた疑い)を一覧にする。"""
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    splits = json.load(open(SPLITS, encoding="utf-8"))
    rows = []
    for code, e in splits.items():
        if code.startswith("_") or not isinstance(e, dict):
            continue
        m = re.search(r"EDINET \S+ (S100[0-9A-Z]{4})", e.get("出典") or "")
        if m:
            rows.append((code, e, m.group(1)))
    print("EDINETの注記から拾った分割", len(rows), "件を読み直します", flush=True)
    with ThreadPoolExecutor(4) as ex:
        texts = list(ex.map(lambda t: text_of(t[2]), rows))
    res = [find_splits(t) for t in texts]
    bad = 0
    for (code, e, doc), got, text in zip(rows, res, texts):
        fy = state.get(code) or ""
        cands = got.get("_all") or []
        day, ratio = e["効力発生日"], float(e["比率"])
        if not text:
            mark = "読めず"
        elif [day, ratio] in cands:
            mark = "ok"
        elif any(r == ratio and d <= fy for d, r in cands):
            mark = "期中の分割(二重の割り戻し)"
        elif any(d == day for d, r in cands):
            mark = "比率違い"
        else:
            mark = "根拠なし(他社の分割の可能性)"
        if mark != "ok":
            bad += 1
        print("%s %s %s %s 1株→%s株 期末%s %s 当社の候補%s" % (mark, code, e.get("名前"), day, e["比率"], fy, doc, cands), flush=True)
        if mark != "ok":
            # 判断の材料に、当社の分割として書かれた文を出しておく(同じ文は1回だけ)
            seen = set()
            for m2 in re.finditer(r"[^。\n\"]{0,160}(?:株式分割|株式併合)[^。\n\"]{0,160}", text):
                t = re.sub(r"\s+", " ", m2.group(0)).strip()
                if re.search(r"\d{4}年\d{1,2}月\d{1,2}日", t) and t not in seen and len(seen) < 4 and not other_company(text, m2.end() - 1):
                    seen.add(t)
                    print("    「" + t + "」", flush=True)
    print("疑わしいもの", bad, "件")


if __name__ == "__main__":
    main()
