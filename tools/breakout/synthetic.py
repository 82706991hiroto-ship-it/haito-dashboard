#!/usr/bin/env python3
"""backtest.py の検算用に、合成の日足CSVを作る。

  --momentum 0   : ただのランダムウォーク(どんな売買ルールでも期待値はほぼ −コスト になるはず)
  --momentum 0.003: 時々「出来高を伴って上昇が続く局面」を混ぜる(ブレイク手法が効くはずの世界)

  python3 tools/breakout/synthetic.py out.csv --stocks 300 --momentum 0
"""
import argparse
import numpy as np
import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out")
    p.add_argument("--stocks", type=int, default=300)
    p.add_argument("--days", type=int, default=2450)
    p.add_argument("--vol", type=float, default=0.022, help="日々の値動きの大きさ")
    p.add_argument("--momentum", type=float, default=0.0, help="上昇局面の1日あたりのドリフト")
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args()
    rng = np.random.default_rng(a.seed)
    dates = pd.bdate_range("2015-01-05", periods=a.days)
    rows = []
    for k in range(a.stocks):
        # t分布(自由度4)の分散は2なので √2 で割って日次の標準偏差を vol にそろえ、
        # 価格の期待値が増えも減りもしないよう vol²/2 を引く
        r = rng.standard_t(4, a.days) * a.vol / np.sqrt(2) - a.vol ** 2 / 2
        vmult = np.ones(a.days)
        if a.momentum:
            i = 300
            while i < a.days:
                i += int(rng.integers(150, 600))
                n = int(rng.integers(40, 160))
                r[i:i + n] += a.momentum
                vmult[i:i + 5] *= 3.0
                vmult[i:i + n] *= 1.3
                i += n
        close = 1000 * np.exp(np.cumsum(r))
        gap = rng.normal(0, a.vol / 3, a.days)
        open_ = np.r_[1000, close[:-1]] * np.exp(gap)
        hi = np.maximum(open_, close) * np.exp(np.abs(rng.normal(0, a.vol / 2, a.days)))
        lo = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0, a.vol / 2, a.days)))
        vol = 1e5 * vmult * np.exp(rng.normal(0, 0.3, a.days)) * (1 + 20 * np.abs(r))
        rows.append(pd.DataFrame({"Date": dates, "Code": f"S{k:04d}", "Open": open_, "High": hi,
                                  "Low": lo, "Close": close, "Volume": vol.round()}))
    pd.concat(rows).to_csv(a.out, index=False, float_format="%.2f")
    print(a.out, a.stocks, "銘柄")


if __name__ == "__main__":
    main()
