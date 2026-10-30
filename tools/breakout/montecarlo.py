#!/usr/bin/env python3
"""資金管理ルール(1銘柄=資産の1/5、損切り−8〜−10%)の数字の検算。

勝率と平均利益・平均損失を決めて取引を並べ替え、資産の推移・最大DD・連敗の分布を見る。
株価データは使わない。「1勝4敗でもトータルで勝てる」に必要な条件を確かめるためのもの。

  python3 tools/breakout/montecarlo.py
  python3 tools/breakout/montecarlo.py --win 0.3 --avg-win 0.25 --avg-loss 0.09
"""
import argparse
import numpy as np


def simulate(p, w, l, frac, n, paths, rng):
    win = rng.random((paths, n)) < p
    # 勝ち負けの大きさにもばらつきを持たせる(利益は指数分布、損失は損切り幅の近くに集まる)
    gain = rng.exponential(w, (paths, n))
    loss = -np.clip(rng.normal(l, l * 0.25, (paths, n)), 0, None)
    r = np.where(win, gain, loss)
    eq = np.cumprod(1 + frac * r, axis=1)
    dd = (eq / np.maximum.accumulate(eq, axis=1) - 1).min(axis=1)
    streak = np.zeros(paths, int)
    cur = np.zeros(paths, int)
    for k in range(n):
        cur = np.where(~win[:, k], cur + 1, 0)
        streak = np.maximum(streak, cur)
    return eq[:, -1], dd, streak


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--win", type=float)
    ap.add_argument("--avg-win", type=float, default=0.25)
    ap.add_argument("--avg-loss", type=float, default=0.09, help="損切り−10%%でも滑り・早めの撤退で平均はこのくらい")
    ap.add_argument("--frac", type=float, default=0.2, help="1銘柄の比率(1/5)")
    ap.add_argument("--trades", type=int, default=100)
    ap.add_argument("--paths", type=int, default=20000)
    ap.add_argument("--cost", type=float, default=0.004, help="往復コスト")
    a = ap.parse_args()
    rng = np.random.default_rng(0)
    w, l = a.avg_win - a.cost, a.avg_loss + a.cost

    print(f"平均利益 {a.avg_win:.0%} / 平均損失 {a.avg_loss:.0%} / 往復コスト {a.cost:.1%} / "
          f"1銘柄 {a.frac:.0%} / {a.trades}取引 × {a.paths}通り")
    print(f"損益分岐の勝率 = 損失÷(利益+損失) = {l / (w + l):.1%}\n")
    print("勝率  期待値/回  100取引後(中央)  損した確率  最大DD(中央)  DD-20%超の確率  最大連敗(中央/90%)")
    for p in ([a.win] if a.win else [0.2, 0.25, 0.3, 0.35, 0.4, 0.45]):
        fin, dd, st = simulate(p, w, l, a.frac, a.trades, a.paths, rng)
        ev = p * w - (1 - p) * l
        print(f"{p:4.0%}  {ev:+8.1%}  {np.median(fin):12.2f}倍  {np.mean(fin < 1):9.0%}  "
              f"{np.median(dd):10.0%}  {np.mean(dd < -0.2):13.0%}  {np.median(st):8.0f} / {np.percentile(st, 90):.0f}")

    print("\n「1勝4敗(勝率20%)で勝つ」のに必要な平均利益÷平均損失(コスト込み)")
    for p in [0.2, 0.25, 0.3, 0.35, 0.4]:
        print(f"  勝率{p:.0%}: 損益比 {(1 - p) / p:.2f} 倍超 → 平均損失 {l:.1%} なら平均利益 {(1 - p) / p * l + a.cost:.1%} 超")


if __name__ == "__main__":
    main()
