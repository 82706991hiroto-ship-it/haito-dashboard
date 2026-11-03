"""予想。過去レース結果CSV(履歴)に、予想したいレースの出走表(finish空欄)を足したCSVを渡す。

使い方: python predict.py data/with_entries.csv --race R01500 [--model model.pkl]
"""
import argparse, json, pickle
import pandas as pd
from features import build


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--race", help="race_id。省略すると finish が空欄のレース全部")
    ap.add_argument("--model", default="model.pkl")
    ap.add_argument("--json", help="画面用のJSONを書き出す先(例: predictions.json)")
    ap.add_argument("--last", type=int, help="--race省略時、実績ありの直近Nレースを対象にする(動作確認用)")
    a = ap.parse_args()
    m = pickle.load(open(a.model, "rb"))
    df = build(pd.read_csv(a.csv))
    if a.race:
        tgt = df[df["race_id"] == a.race]
    elif a.last:
        tgt = df[df["race_id"].isin(df["race_id"].drop_duplicates().tail(a.last))]
    else:
        tgt = df[df["finish"].isna()]
    if tgt.empty:
        raise SystemExit("予想対象のレースが見つかりません")
    tgt = tgt.assign(p=m["model"].predict_proba(tgt[m["cols"]])[:, 1])
    tgt["p"] = tgt["p"] / tgt.groupby("race_id")["p"].transform("sum")
    if a.json:
        races = []
        for rid, g in tgt.groupby("race_id", sort=True):
            g = g.sort_values("p", ascending=False)
            has_odds = "odds" in g and g["odds"].notna().all()
            races.append({
                "race_id": rid, "date": str(g["date"].iloc[0].date()), "distance": int(g["distance"].iloc[0]),
                "surface": str(g["surface"].iloc[0]), "going": str(g["going"].iloc[0]),
                "horses": [{
                    "frame": int(r["frame"]), "name": str(r.get("horse_name", r["horse_id"])),
                    "jockey": str(r["jockey"]), "p": round(float(r["p"]), 4),
                    "odds": float(r["odds"]) if has_odds else None,
                    "finish": int(r["finish"]) if pd.notna(r["finish"]) else None,
                } for _, r in g.iterrows()]})
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"races": races}, f, ensure_ascii=False)
        print(f"{len(races)}レース -> {a.json}")
        return
    for rid, g in tgt.groupby("race_id"):
        print(f"\n== {rid} ==")
        g = g.sort_values("p", ascending=False)
        for _, r in g.iterrows():
            name = r.get("horse_name", r["horse_id"])
            ev = f"  期待値 {r['p'] * r['odds']:.2f}" if "odds" in g and pd.notna(r.get("odds")) else ""
            print(f"{int(r['frame']):>2}枠 {name:<8} 勝率 {r['p']:.1%}{ev}")


if __name__ == "__main__":
    main()
