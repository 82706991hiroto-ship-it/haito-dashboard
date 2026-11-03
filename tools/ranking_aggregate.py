#!/usr/bin/env python3
"""みんなのランキングの集計(1日1回 GitHub Actions で動かす)。

Firebase の poll/{uid}(参加した端末が送った国内株のコードの一覧)を全部読み、銘柄ごとの人数を数えて
data/ranking.json に書く。アプリはこのファイルを1回読むだけなので、人数が増えても Firebase の読み込みは
「1日1回 × 参加者の数」で済む。

- 人数が MIN_PEOPLE 人に満たない銘柄は書かない(少人数だと誰の保有か推測できてしまうため)
- 90日送ってこない端末は数えない(使わなくなった端末)
- 鍵(サービスアカウントのJSON)は GitHub の Secrets の FIREBASE_SA に入れる。無ければ何もしないで終わる

  FIREBASE_SA='{...}' python3 tools/ranking_aggregate.py
"""
import datetime as dt, json, os, re, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "ranking.json")
MIN_PEOPLE = 10
ACTIVE_DAYS = 90
TOP = 30
CODE = re.compile(r"^[1-9][0-9A-Z]{3}$")


def access_token(sa):
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    cred = service_account.Credentials.from_service_account_info(sa, scopes=["https://www.googleapis.com/auth/datastore"])
    cred.refresh(Request())
    return cred.token


def read_all(project, database, token):
    import requests
    url = "https://firestore.googleapis.com/v1/projects/%s/databases/%s/documents/poll" % (project, database)
    docs, page = [], None
    while True:
        params = {"pageSize": 300}
        if page:
            params["pageToken"] = page
        r = requests.get(url, params=params, headers={"Authorization": "Bearer " + token}, timeout=60)
        r.raise_for_status()
        j = r.json()
        docs += j.get("documents", [])
        page = j.get("nextPageToken")
        if not page:
            return docs


def codes_of(field):
    vals = (field or {}).get("arrayValue", {}).get("values", [])
    out = set()
    for v in vals[:300]:
        c = str(v.get("stringValue", "")).strip().upper()
        if CODE.match(c):
            out.add(c)
    return out


def count(docs, now_ms):
    held, watch, n = {}, {}, 0
    for d in docs:
        f = d.get("fields", {})
        t = int(f.get("t", {}).get("integerValue", "0") or 0)
        if now_ms - t > ACTIVE_DAYS * 86400000:
            continue
        n += 1
        for c in codes_of(f.get("h")):
            held[c] = held.get(c, 0) + 1
        for c in codes_of(f.get("w")):
            watch[c] = watch.get(c, 0) + 1
    return n, held, watch


def top(m):
    rows = [[c, k] for c, k in m.items() if k >= MIN_PEOPLE]
    rows.sort(key=lambda x: (-x[1], x[0]))
    return rows[:TOP]


def build(n, held, watch, prev, today):
    """past: 週に1回の記録(人数が MIN_PEOPLE 以上の銘柄だけ)。rising: 7日以上前の記録より買い増し候補の人数が増えた銘柄"""
    past = [p for p in (prev.get("past") or []) if p.get("d")]
    if not past or (dt.date.fromisoformat(today) - dt.date.fromisoformat(past[-1]["d"])).days >= 7:
        past.append({"d": today, "w": {c: k for c, k in watch.items() if k >= MIN_PEOPLE}})
    past = past[-8:]
    base = next((p for p in past if (dt.date.fromisoformat(today) - dt.date.fromisoformat(p["d"])).days >= 7), None)
    rising = []
    if base:
        for c, k in watch.items():
            if k >= MIN_PEOPLE and k - base["w"].get(c, 0) > 0:
                rising.append([c, k - base["w"].get(c, 0), k])
        rising.sort(key=lambda x: (-x[1], -x[2], x[0]))
    return {"built": today, "n": n, "min": MIN_PEOPLE, "held": top(held), "watch": top(watch),
            "rising": rising[:TOP], "since": base["d"] if base else "", "past": past}


def main():
    raw = os.environ.get("FIREBASE_SA", "").strip()
    if not raw:
        print("FIREBASE_SA が無いので集計しません")
        return 0
    sa = json.loads(raw)
    project = os.environ.get("FIREBASE_PROJECT") or sa.get("project_id")
    database = os.environ.get("FIREBASE_DATABASE") or "(default)"
    docs = read_all(project, database, access_token(sa))
    n, held, watch = count(docs, int(time.time() * 1000))
    try:
        prev = json.load(open(OUT, encoding="utf-8"))
    except (OSError, ValueError):
        prev = {}
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()
    out = build(n, held, watch, prev, today)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("参加", n, "人 ・ 表示できる銘柄: 保有", len(out["held"]), "・ 買い増し候補", len(out["watch"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
