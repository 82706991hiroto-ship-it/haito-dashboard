"""予想。過去レース結果CSV(履歴)に、予想したいレースの出走表(finish空欄)を足したCSVを渡す。

使い方: python predict.py data/with_entries.csv --race R01500 [--model model.pkl]
"""
import argparse, pickle
import pandas as pd
from features import build


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--race", help="race_id。省略すると finish が空欄のレース全部")
    ap.add_argument("--model", default="model.pkl")
    a = ap.parse_args()
    m = pickle.load(open(a.model, "rb"))
    df = build(pd.read_csv(a.csv))
    tgt = df[df["race_id"] == a.race] if a.race else df[df["finish"].isna()]
    if tgt.empty:
        raise SystemExit("予想対象のレースが見つかりません")
    tgt = tgt.assign(p=m["model"].predict_proba(tgt[m["cols"]])[:, 1])
    tgt["p"] = tgt["p"] / tgt.groupby("race_id")["p"].transform("sum")
    for rid, g in tgt.groupby("race_id"):
        print(f"\n== {rid} ==")
        g = g.sort_values("p", ascending=False)
        for _, r in g.iterrows():
            name = r.get("horse_name", r["horse_id"])
            ev = f"  期待値 {r['p'] * r['odds']:.2f}" if "odds" in g and pd.notna(r.get("odds")) else ""
            print(f"{int(r['frame']):>2}枠 {name:<8} 勝率 {r['p']:.1%}{ev}")


if __name__ == "__main__":
    main()
