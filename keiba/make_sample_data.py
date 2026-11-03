"""動作確認用の架空レース結果CSVを作る(実データではない)。

使い方: python make_sample_data.py data/sample.csv
"""
import sys
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
N_HORSES, N_RACES = 300, 1500
horses = pd.DataFrame({
    "horse_id": [f"H{i:04d}" for i in range(N_HORSES)],
    "ability": rng.normal(0, 1, N_HORSES),
    "sex": rng.choice(["牡", "牝", "セ"], N_HORSES, p=[.5, .4, .1]),
    "base_age": rng.integers(3, 8, N_HORSES),
})
jockeys = [f"J{i:02d}" for i in range(30)]
jock_skill = dict(zip(jockeys, rng.normal(0, .4, 30)))

rows = []
for r in range(N_RACES):
    date = pd.Timestamp("2022-01-01") + pd.Timedelta(days=int(r * 1000 / N_RACES))
    n = int(rng.integers(8, 17))
    field = horses.sample(n, random_state=int(rng.integers(1 << 30)))
    dist = int(rng.choice([1200, 1600, 2000, 2400]))
    surface = str(rng.choice(["芝", "ダート"]))
    going = str(rng.choice(["良", "稍重", "重", "不良"], p=[.6, .2, .12, .08]))
    jk = rng.choice(jockeys, n)
    frame = rng.permutation(n) + 1
    strength = (field.ability.values
                + np.array([jock_skill[j] for j in jk])
                - 0.03 * np.abs(frame - n / 2)
                + rng.normal(0, 1.0, n))
    finish = (-strength).argsort().argsort() + 1
    # オッズは「見えている能力」から作る(的中のしやすさを反映しつつ穴も出る)
    p = np.exp(field.ability.values + np.array([jock_skill[j] for j in jk]))
    p = p / p.sum()
    odds = np.round(0.8 / p * rng.uniform(.85, 1.15, n), 1).clip(1.1)
    for i in range(n):
        rows.append(dict(
            race_id=f"R{r:05d}", date=date.date(), horse_id=field.horse_id.values[i],
            horse_name=f"馬{field.horse_id.values[i][1:]}", jockey=jk[i],
            frame=int(frame[i]), age=int(field.base_age.values[i]), sex=field.sex.values[i],
            weight_carried=float(rng.choice([54, 55, 56, 57, 58])),
            body_weight=int(rng.normal(480, 25)), distance=dist, surface=surface,
            going=going, odds=odds[i], finish=int(finish[i]),
        ))
out = sys.argv[1] if len(sys.argv) > 1 else "data/sample.csv"
import os; os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
pd.DataFrame(rows).to_csv(out, index=False)
print(f"{len(rows)}行 -> {out}")
