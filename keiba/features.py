"""特徴量づくり。過去の成績は「そのレースより前」だけで集計し、未来の情報を混ぜない。"""
import numpy as np
import pandas as pd

CAT = ["sex", "surface", "going", "jockey"]
NUM = ["frame", "age", "weight_carried", "body_weight", "distance", "field_size",
       "frame_rel", "prev_runs", "prev_win_rate", "prev_top3_rate", "prev_avg_rank_pct",
       "days_since_last", "jockey_win_rate"]
REQUIRED = ["race_id", "date", "horse_id", "jockey", "frame", "age", "sex",
            "weight_carried", "body_weight", "distance", "surface", "going"]


def build(df: pd.DataFrame) -> pd.DataFrame:
    """df: 過去レース+予想したいレースを全部まとめたもの(finishは予想分のみ空欄でよい)。"""
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"CSVに必要な列がありません: {missing}")
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date", "race_id"]).reset_index(drop=True)
    if "finish" not in df:
        df["finish"] = np.nan
    df["field_size"] = df.groupby("race_id")["horse_id"].transform("count")
    df["frame_rel"] = df["frame"] / df["field_size"]
    done = df["finish"].notna()
    df["win"] = (df["finish"] == 1).astype(float).where(done)
    df["top3"] = (df["finish"] <= 3).astype(float).where(done)
    df["rank_pct"] = (df["finish"] / df["field_size"]).where(done)

    for col, name in [("win", "prev_win_rate"), ("top3", "prev_top3_rate"), ("rank_pct", "prev_avg_rank_pct")]:
        s = df[col].fillna(0)
        cum = s.groupby(df["horse_id"]).cumsum() - s
        cnt = done.astype(int).groupby(df["horse_id"]).cumsum() - done.astype(int)
        df[name] = cum / cnt.replace(0, np.nan)
        df["prev_runs"] = cnt
    last = df.groupby("horse_id")["date"].shift(1)
    df["days_since_last"] = (df["date"] - last).dt.days
    s = df["win"].fillna(0)
    cum = s.groupby(df["jockey"]).cumsum() - s
    cnt = done.astype(int).groupby(df["jockey"]).cumsum() - done.astype(int)
    df["jockey_win_rate"] = cum / cnt.replace(0, np.nan)
    for c in CAT:
        df[c] = df[c].astype("category")
    return df


def xcols(use_odds: bool):
    return CAT + NUM + (["odds"] if use_odds else [])
