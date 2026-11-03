"""学習と評価。新しい期間をテストにして、1着確率の精度と回収率を見る。

使い方: python train.py data/sample.csv [--use-odds] [--test-ratio 0.2]
"""
import argparse, pickle
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss
from features import build, xcols


def race_normalize(df, p):
    s = pd.Series(p, index=df.index)
    return s / s.groupby(df["race_id"]).transform("sum")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--use-odds", action="store_true", help="オッズも特徴量に入れる(入れないと穴馬探しの検証がしやすい)")
    ap.add_argument("--test-ratio", type=float, default=0.2)
    ap.add_argument("--out", default="model.pkl")
    a = ap.parse_args()

    df = build(pd.read_csv(a.csv))
    df = df[df["finish"].notna()].reset_index(drop=True)
    cut = df["date"].quantile(1 - a.test_ratio)
    tr, te = df[df["date"] < cut], df[df["date"] >= cut]
    cols = xcols(a.use_odds)
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, categorical_features="from_dtype",
                                         random_state=0)
    clf.fit(tr[cols], tr["win"])
    te = te.assign(p=race_normalize(te, clf.predict_proba(te[cols])[:, 1]))

    base = np.full(len(te), tr["win"].mean())
    print(f"学習 {len(tr)}頭 / テスト {len(te)}頭 (境界 {cut.date()})")
    print(f"logloss  モデル {log_loss(te['win'], te['p']):.4f}  /  全馬同確率 {log_loss(te['win'], base):.4f}")
    top = te.loc[te.groupby("race_id")["p"].idxmax()]
    print(f"本命(予想1位)の的中率 {top['win'].mean():.1%}  (ランダムなら約{(1 / te['field_size']).groupby(te['race_id']).first().mean():.1%})")
    if "odds" in te:
        ret = (top["win"] * top["odds"]).mean()
        print(f"本命単勝を毎回100円買った回収率 {ret:.1%}  ※100%未満が普通。サンプル数が少ないとブレる")
        te["ev"] = te["p"] * te["odds"]
        pick = te[te["ev"] > 1.2]
        if len(pick):
            print(f"期待値>1.2の馬を買った回収率 {(pick['win'] * pick['odds']).mean():.1%} ({len(pick)}点)")
    with open(a.out, "wb") as f:
        pickle.dump({"model": clf, "cols": cols, "use_odds": a.use_odds}, f)
    print(f"保存 -> {a.out}")


if __name__ == "__main__":
    main()
