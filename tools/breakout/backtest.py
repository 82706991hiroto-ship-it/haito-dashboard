#!/usr/bin/env python3
"""新高値ブレイク手法(kenmo式・DUKE。式)の価格・出来高部分のバックテスト。

業績条件(増収率・増益率・ROE・経常利益)は時点データが要るためここでは扱わない。
検証するのは「52週高値ブレイク+出来高急増で買い、−8%/−10%で損切り、
+20%で建値へ引き上げ、ボックス割れ・トレーリングで手仕舞う」という売買ルールの部分。

入力: 日足CSV(1ファイルに全銘柄。列 Date, Code, Open, High, Low, Close, Volume)。
      J-Quants の daily_quotes の形式なら AdjustmentOpen などの調整後の列を優先して使う。
      上場廃止銘柄も含めないと生存者バイアスで成績が良く出る。

  python3 tools/breakout/backtest.py quotes.csv --index topix.csv
  python3 tools/breakout/backtest.py quotes.csv --compare     # 主なルール違いを並べる
"""
import argparse
import numpy as np
import pandas as pd


def load_quotes(path):
    df = pd.read_csv(path, dtype={"Code": str}, parse_dates=["Date"])
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        adj = "Adjustment" + col
        if adj in df.columns:
            df[col] = df[adj]
    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    df = df[(df.Open > 0) & (df.Close > 0)]
    return {code: g.sort_values("Date").set_index("Date")[["Open", "High", "Low", "Close", "Volume"]]
            for code, g in df.groupby("Code")}


def load_index_filter(path, ma=200):
    """指数の終値が ma 日移動平均より上の日を True(相場環境のゲート)。"""
    df = pd.read_csv(path, parse_dates=["Date"]).sort_values("Date").set_index("Date")
    return df.Close > df.Close.rolling(ma).mean()


def find_signals(df, a, rng=None):
    """シグナル日(終値で52週高値を更新し、出来高が平均の vol_mult 倍以上)のインデックスとブレイク水準。"""
    h, c, v = df.High, df.Close, df.Volume
    level = h.rolling(a.lookback).max().shift(1)
    vavg = v.rolling(a.vol_avg).mean().shift(1)
    turnover = (c * v).rolling(25).mean()
    ok = turnover >= a.min_turnover
    if rng is not None:
        # 比較用: 同じ出口ルールで、ブレイクと無関係な日にランダムに入る
        sig = ok & level.notna() & pd.Series(rng.random(len(df)) < a.random_rate, index=df.index)
        level = c
    else:
        sig = ok & (c > level) & (v >= a.vol_mult * vavg)
    idx, last = [], -10**9
    for i in np.flatnonzero(sig.to_numpy()):
        if i - last > a.cooldown:  # 連続したシグナルは最初の1回だけ
            idx.append(i)
        last = i
    return idx, level.to_numpy()


def simulate_trade(o, h, l, c, v, i, level, a):
    n = len(c)
    if a.entry == "confirm":
        # kenmo式: 翌日のチャートを見てから。翌日が大陰線+出来高増ならダマシとして見送る
        d = i + 1
        if d >= n - 1:
            return None
        if c[d] < o[d] and (o[d] - c[d]) / o[d] >= a.fake_body and v[d] > v[i]:
            return "fake"
        ie = d + 1
    else:
        ie = i + 1  # DUKE。式: 翌営業日の寄付成行
    if ie >= n:
        return None
    px = o[ie]
    stop = px * (1 - a.stop)
    be = False
    pending = False
    for j in range(ie, n):
        if pending:
            return ie, j, o[j], "box"
        if l[j] <= stop:
            fill = stop if j == ie else min(o[j], stop)
            return ie, j, fill, ("stop" if not be else "trail")
        if c[j] >= px * (1 + a.be_trigger):
            be = True
            stop = max(stop, px)
        if be and a.trail > 0 and j - ie + 1 >= a.trail:
            stop = max(stop, l[j - a.trail + 1:j + 1].min())
        if a.box_exit and c[j] < level * (1 - a.box_buf):
            pending = True
    return ie, n - 1, c[n - 1], "open"


def run_trades(quotes, a, idx_ok=None, seed=None):
    rng = np.random.default_rng(seed) if seed is not None else None
    trades, fakes, filtered = [], 0, 0
    for code, df in quotes.items():
        if len(df) < a.lookback + 2:
            continue
        sigs, level = find_signals(df, a, rng)
        o, h, l, c, v = (df[k].to_numpy() for k in ["Open", "High", "Low", "Close", "Volume"])
        dates = df.index
        for i in sigs:
            if idx_ok is not None:
                ok = idx_ok.asof(dates[i])
                if not ok:
                    filtered += 1
                    continue
            r = simulate_trade(o, h, l, c, v, i, level[i], a)
            if r is None:
                continue
            if r == "fake":
                fakes += 1
                continue
            ie, ix, fill, why = r
            ret = fill * (1 - a.cost) / (o[ie] * (1 + a.cost)) - 1
            trades.append(dict(code=code, signal=dates[i], entry=dates[ie], exit=dates[ix],
                               entry_px=o[ie], exit_px=fill, ret=ret, reason=why, days=ix - ie))
    t = pd.DataFrame(trades)
    return t, fakes, filtered


def trade_stats(t):
    if t.empty:
        return {}
    w, lo = t.ret[t.ret > 0], t.ret[t.ret <= 0]
    streak = best = 0
    for r in t.sort_values("entry").ret:
        streak = streak + 1 if r <= 0 else 0
        best = max(best, streak)
    return {
        "取引数": len(t),
        "勝率": len(w) / len(t),
        "平均利益": w.mean() if len(w) else 0.0,
        "平均損失": lo.mean() if len(lo) else 0.0,
        "損益比": (w.mean() / -lo.mean()) if len(w) and len(lo) and lo.mean() < 0 else float("nan"),
        "期待値/回": t.ret.mean(),
        "PF": w.sum() / -lo.sum() if lo.sum() < 0 else float("inf"),
        "保有日数(中央)": t.days.median(),
        "最大連敗": best,
        "最大の負け": t.ret.min(),
    }


def portfolio(t, quotes, a, seed=0):
    """最大 max_pos 銘柄、1銘柄=その時点の資産÷max_pos。日々の終値で時価評価する。"""
    if t.empty:
        return None
    rng = np.random.default_rng(seed)
    t = t.assign(_r=rng.random(len(t))).sort_values(["entry", "_r"]).reset_index(drop=True)
    dates = sorted(set().union(*[df.index for df in quotes.values()]))
    dates = [d for d in dates if t.entry.min() <= d <= t.exit.max()]
    by_entry = {d: g for d, g in t.groupby("entry")}
    close = {code: quotes[code].Close for code in t.code.unique()}
    cash, pos, curve, taken = 1.0, [], [], 0
    equity = 1.0
    for d in dates:
        # 手仕舞い(当日に約定)
        keep = []
        for p in pos:
            if p["exit"] == d:
                cash += p["units"] * p["exit_px"] * (1 - a.cost)
            else:
                keep.append(p)
        pos = keep
        # 新規(寄付で約定。投資上限は前日の資産で計算し直す)
        for _, tr in by_entry.get(d, pd.DataFrame()).iterrows():
            if len(pos) >= a.max_pos or any(p["code"] == tr.code for p in pos):
                continue
            alloc = min(equity / a.max_pos, cash)
            if alloc <= 0:
                continue
            units = alloc / (tr.entry_px * (1 + a.cost))
            cash -= alloc
            pos.append(dict(code=tr.code, units=units, exit=tr.exit, exit_px=tr.exit_px))
            taken += 1
            if tr.exit == d:  # 当日中の損切り
                cash += units * tr.exit_px * (1 - a.cost)
                pos.pop()
        equity = cash + sum(p["units"] * close[p["code"]].asof(d) for p in pos)
        curve.append((d, equity))
    s = pd.Series(dict(curve))
    years = (s.index[-1] - s.index[0]).days / 365.25
    dd = s / s.cummax() - 1
    yearly = s.groupby(s.index.year).last() / s.groupby(s.index.year).first() - 1
    return {"最終資産(倍)": s.iloc[-1], "年率": s.iloc[-1] ** (1 / years) - 1 if years > 0 else 0,
            "最大DD": dd.min(), "採用取引": taken, "年別": yearly}


def fmt(stats):
    pct = {"勝率", "平均利益", "平均損失", "期待値/回", "最大の負け", "年率", "最大DD"}
    out = []
    for k, val in stats.items():
        if k == "年別":
            continue
        if k in pct:
            out.append(f"{k} {val:+.1%}" if k != "勝率" else f"{k} {val:.1%}")
        elif isinstance(val, float):
            out.append(f"{k} {val:.2f}")
        else:
            out.append(f"{k} {val}")
    return " / ".join(out)


VARIANTS = [
    ("DUKE: 翌日寄付・−10%・ボックス割れ", dict(entry="next_open", stop=0.10, box_exit=True)),
    ("DUKE: ボックス割れ判定なし", dict(entry="next_open", stop=0.10, box_exit=False)),
    ("kenmo: 翌日確認・−8%", dict(entry="confirm", stop=0.08, box_exit=False)),
    ("kenmo: 翌日確認・−8%・ボックス割れ", dict(entry="confirm", stop=0.08, box_exit=True)),
    ("出来高条件なし(1.0倍)", dict(entry="next_open", stop=0.10, box_exit=True, vol_mult=0.0)),
]


def parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("quotes")
    p.add_argument("--index", help="指数の日足CSV(Date, Close)。終値が200日線より上の日だけ新規に入る")
    p.add_argument("--entry", choices=["next_open", "confirm"], default="next_open")
    p.add_argument("--stop", type=float, default=0.10, help="損切り幅(0.10=−10%%)")
    p.add_argument("--be-trigger", type=float, default=0.20, help="この上昇で損切りを建値へ")
    p.add_argument("--trail", type=int, default=20, help="建値引き上げ後、直近N日安値をトレーリング(0で無効)")
    p.add_argument("--box-exit", action=argparse.BooleanOptionalAction, default=True,
                   help="終値がブレイク前の高値(元のボックス上限)を割ったら翌日寄付で売る")
    p.add_argument("--box-buf", type=float, default=0.03, help="ボックス割れとみなす余裕")
    p.add_argument("--lookback", type=int, default=250)
    p.add_argument("--vol-avg", type=int, default=50)
    p.add_argument("--vol-mult", type=float, default=2.0)
    p.add_argument("--fake-body", type=float, default=0.03, help="ダマシとみなす陰線の実体(始値比)")
    p.add_argument("--cooldown", type=int, default=20, help="同じ銘柄の次のシグナルまで空ける日数")
    p.add_argument("--min-turnover", type=float, default=5e7, help="25日平均売買代金の下限(円)")
    p.add_argument("--cost", type=float, default=0.002, help="片道の手数料+スリッページ")
    p.add_argument("--max-pos", type=int, default=5)
    p.add_argument("--random-trials", type=int, default=20, help="ランダム入りの比較の回数")
    p.add_argument("--compare", action="store_true", help="主なルール違いを並べて出す")
    p.add_argument("--trades-out", help="取引一覧をCSVに書き出す")
    return p


def report(name, quotes, a, idx_ok):
    t, fakes, filtered = run_trades(quotes, a, idx_ok)
    st = trade_stats(t)
    pf = portfolio(t, quotes, a)
    print(f"\n■ {name}")
    if not st:
        print("  取引なし")
        return t
    extra = []
    if a.entry == "confirm":
        extra.append(f"ダマシで見送り {fakes}")
    if idx_ok is not None:
        extra.append(f"相場ゲートで見送り {filtered}")
    print("  取引単位: " + fmt(st) + (" / " + " / ".join(extra) if extra else ""))
    print("  出口内訳: " + ", ".join(f"{k} {n}" for k, n in t.reason.value_counts().items()))
    if pf:
        print("  5銘柄運用: " + fmt(pf))
        print("  年別: " + " ".join(f"{y}:{r:+.0%}" for y, r in pf["年別"].items()))
    return t


def main():
    a = parser().parse_args()
    quotes = load_quotes(a.quotes)
    idx_ok = load_index_filter(a.index) if a.index else None
    print(f"{len(quotes)}銘柄 / 期間 {min(d.index[0] for d in quotes.values()).date()}〜"
          f"{max(d.index[-1] for d in quotes.values()).date()} / 片道コスト {a.cost:.2%}")

    runs = [("指定ルール", {})]
    if a.compare:
        runs += VARIANTS
    for name, over in runs:
        b = argparse.Namespace(**{**vars(a), **over})
        t = report(name, quotes, b, idx_ok)
        if name == "指定ルール":
            main_t, main_a = t, b
    if a.trades_out and not main_t.empty:
        main_t.to_csv(a.trades_out, index=False)

    # ブレイクで入ること自体に意味があるか: 同じ出口でランダムな日に入った場合と比べる
    if main_t.empty or a.random_trials <= 0:
        return
    eligible = sum(max(len(df) - a.lookback, 0) for df in quotes.values())
    main_a.random_rate = len(main_t) / max(eligible, 1)
    exp = []
    for s in range(a.random_trials):
        rt, _, _ = run_trades(quotes, main_a, idx_ok, seed=s)
        if not rt.empty:
            exp.append(rt.ret.mean())
    if exp:
        exp = np.array(exp)
        real = main_t.ret.mean()
        print(f"\n■ ランダム入り(同じ出口ルール, {len(exp)}回)")
        print(f"  期待値/回 平均 {exp.mean():+.2%}(範囲 {exp.min():+.2%}〜{exp.max():+.2%})"
              f" → ブレイク入りは {real:+.2%}。ランダムを上回った割合 {np.mean(real > exp):.0%}")


if __name__ == "__main__":
    main()
