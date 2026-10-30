#!/usr/bin/env python3
"""J-Quants API(V2)から全銘柄の日足とTOPIXを取って、backtest.py の入力CSVにする。

日付ごとに全銘柄を取るので、その日に上場していた銘柄(のちの上場廃止を含む)がそろう。
取得結果は日付ごとにキャッシュし、途中で止まっても続きから取れる。
J-Quantsの規約でデータの再配布は禁止。出力はリポジトリに入れないこと。

  JQUANTS_API_KEY=... python3 tools/breakout/fetch_jquants.py --from 2016-01-01 --cache /tmp/jq --out /tmp/jq
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

BASE = "https://api.jquants.com/v2"
# V2の短い列名 → backtest.py の列名(調整後の値を使う)
COLS = {"Date": "Date", "Code": "Code", "AdjO": "Open", "AdjH": "High", "AdjL": "Low",
        "AdjC": "Close", "AdjVo": "Volume"}
TOPIX_PATHS = ["/indices/bars/daily/topix", "/indices/topix"]


def get(path, params, key, wait):
    out, page = [], None
    while True:
        q = dict(params, **({"pagination_key": page} if page else {}))
        req = urllib.request.Request(f"{BASE}{path}?{urllib.parse.urlencode(q)}", headers={"x-api-key": key})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    body = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 or e.code >= 500:
                    time.sleep(wait * 10 * (attempt + 1))
                    continue
                raise SystemExit(f"{path} {q}: HTTP {e.code} {e.read()[:300]!r}")
        else:
            raise SystemExit(f"{path} {q}: 再試行しても取れない")
        out += body.get("data", [])
        page = body.get("pagination_key")
        time.sleep(wait)
        if not page:
            return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="start", required=True)
    p.add_argument("--to", dest="end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    p.add_argument("--cache", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--wait", type=float, default=1.0, help="1回ごとに待つ秒数(プランの上限に合わせる)")
    a = p.parse_args()
    key = os.environ.get("JQUANTS_API_KEY")
    if not key:
        raise SystemExit("環境変数 JQUANTS_API_KEY がない")
    os.makedirs(os.path.join(a.cache, "daily"), exist_ok=True)
    os.makedirs(a.out, exist_ok=True)

    days = pd.bdate_range(a.start, a.end)
    for i, d in enumerate(days):
        f = os.path.join(a.cache, "daily", d.strftime("%Y%m%d") + ".json")
        if os.path.exists(f):
            continue
        rows = get("/equities/bars/daily", {"date": d.strftime("%Y-%m-%d")}, key, a.wait)
        with open(f, "w") as fh:
            json.dump(rows, fh)
        if i % 50 == 0:
            print(d.date(), len(rows), "件", flush=True)

    frames = []
    for name in sorted(os.listdir(os.path.join(a.cache, "daily"))):
        rows = json.load(open(os.path.join(a.cache, "daily", name)))
        if rows:
            frames.append(pd.DataFrame(rows))
    df = pd.concat(frames)
    missing = [c for c in COLS if c not in df.columns]
    if missing:
        raise SystemExit(f"列がない: {missing} / ある列: {list(df.columns)}")
    df = df[list(COLS)].rename(columns=COLS)
    df["Date"] = pd.to_datetime(df.Date)
    df = df[(df.Date >= a.start) & (df.Date <= a.end)].sort_values(["Code", "Date"])
    df.to_csv(os.path.join(a.out, "quotes.csv"), index=False)
    print("quotes.csv", df.Code.nunique(), "銘柄", len(df), "行")

    for path in TOPIX_PATHS:
        try:
            rows = get(path, {"from": a.start, "to": a.end}, key, a.wait)
        except SystemExit as e:
            print("TOPIX", path, "→", e)
            continue
        t = pd.DataFrame(rows)
        close = "C" if "C" in t.columns else "Close"
        t[["Date", close]].rename(columns={close: "Close"}).to_csv(os.path.join(a.out, "topix.csv"), index=False)
        print("topix.csv", len(t), "行")
        break


if __name__ == "__main__":
    main()
