"""他所のレース結果CSVを、このツールの形式に変換する。

使い方:
  python import_csv.py raw.csv data/real.csv                 # 列名を自動で推測
  python import_csv.py raw.csv data/real.csv --map "date=開催日,finish=着順"   # 手で指定(自動より優先)
推測できない必須列があれば、一覧を出して止まる。エンコードは utf-8 / cp932 を自動で試す。
"""
import argparse
import pandas as pd

# このツールの列名: 他所でよくある列名の候補(小文字・空白除去で比較)
ALIASES = {
    "race_id": ["race_id", "raceid", "レースid", "レースコード"],
    "date": ["date", "日付", "開催日", "年月日", "race_date"],
    "horse_id": ["horse_id", "horseid", "馬id", "血統登録番号", "horse_name", "馬名", "horse"],
    "horse_name": ["horse_name", "馬名", "horse"],
    "jockey": ["jockey", "jockey_name", "騎手", "騎手名"],
    "frame": ["frame", "枠番", "枠", "wakuban", "gate", "bracket"],
    "age": ["age", "馬齢", "年齢", "齢"],
    "sex": ["sex", "性別", "性"],
    "weight_carried": ["weight_carried", "斤量", "jockey_weight", "burden_weight"],
    "body_weight": ["body_weight", "馬体重", "weight", "horse_weight"],
    "distance": ["distance", "距離", "course_length"],
    "surface": ["surface", "芝・ダート", "芝ダート", "コース", "track_type", "course_type"],
    "going": ["going", "馬場", "馬場状態", "track_condition", "ground_state"],
    "odds": ["odds", "単勝オッズ", "単勝", "win_odds"],
    "finish": ["finish", "着順", "着", "rank", "finishing_position", "order_of_finish"],
}
REQUIRED = ["race_id", "date", "horse_id", "jockey", "frame", "age", "sex",
            "weight_carried", "body_weight", "distance", "surface", "going"]


def norm(s):
    return str(s).strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def read(path):
    for enc in ("utf-8-sig", "cp932"):
        try:
            return pd.read_csv(path, encoding=enc, low_memory=False)
        except UnicodeDecodeError:
            continue
    raise SystemExit("文字コードを判定できませんでした")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--map", default="", help="新=元 をカンマ区切りで。例: date=開催日,finish=着順")
    a = ap.parse_args()
    df = read(a.src)
    by_norm = {norm(c): c for c in df.columns}
    mapping = {}
    for kv in filter(None, a.map.split(",")):
        k, v = kv.split("=", 1)
        if v not in df.columns:
            raise SystemExit(f"--map の列 '{v}' がCSVにありません")
        mapping[k] = v
    used = set(mapping.values())
    for new, cands in ALIASES.items():
        if new in mapping:
            continue
        for c in cands:
            src = by_norm.get(norm(c))
            if src and src not in used:
                mapping[new] = src; used.add(src); break
    # race_id が無ければ 日付+開催場+R のような列から作れないので、あるものだけで案内
    print("対応づけ:")
    for k in ALIASES:
        print(f"  {k:<15} <- {mapping.get(k, '(なし)')}")
    missing = [c for c in REQUIRED if c not in mapping]
    if missing:
        print("\n足りない必須列:", missing)
        print("元CSVの列:", list(df.columns))
        raise SystemExit("--map で指定してください")
    out = pd.DataFrame({k: df[v] for k, v in mapping.items()})
    out["finish"] = pd.to_numeric(out.get("finish"), errors="coerce") if "finish" in out else None
    if "horse_id" in out and "horse_name" not in out:
        out["horse_name"] = out["horse_id"]
    for c in ("frame", "age", "weight_carried", "body_weight", "distance", "odds"):
        if c in out:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    n0 = len(out)
    out = out.dropna(subset=["frame", "age", "distance", "date"])
    # 中止・除外など着順が数字でない行は学習に使えないので除く(出走表の予想用行は finish 空欄のまま残る)
    print(f"\n{n0}行 -> {len(out)}行 (必須の数値が欠けた行を除外)")
    out.to_csv(a.dst, index=False)
    print(f"保存 -> {a.dst}")


if __name__ == "__main__":
    main()
