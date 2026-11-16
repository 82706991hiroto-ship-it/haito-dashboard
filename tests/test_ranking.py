#!/usr/bin/env python3
"""みんなのランキングの集計(tools/ranking_aggregate.py)の点検。 python3 tests/test_ranking.py"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import ranking_aggregate as ra

NOW = int(time.time() * 1000)


def doc(h, w, t=NOW):
    arr = lambda xs: {"arrayValue": {"values": [{"stringValue": c} for c in xs]}}
    return {"fields": {"h": arr(h), "w": arr(w), "t": {"integerValue": str(t)}}}


docs = [doc(["8058", "2914"], ["9433"]) for _ in range(12)] + [doc(["7203", "bad", "8058", "8058"], []) for _ in range(3)] \
    + [doc(["1111"], [], NOW - 100 * 86400000)]
n, held, watch = ra.count(docs, NOW)
assert n == 15, n                                   # 90日送ってこない端末は数えない
assert held == {"8058": 15, "2914": 12, "7203": 3}  # コードの形でないもの・同じ端末の重複は数えない
out = ra.build(n, held, watch, {"past": [{"d": "2026-10-20", "w": {"9433": 5}}]}, "2026-11-03")
assert out["held"] == [["8058", 15], ["2914", 12]]   # 10人未満(7203)は出さない
assert out["watch"] == [["9433", 12]]
assert out["rising"] == [["9433", 7, 12]] and out["since"] == "2026-10-20"
assert len(out["past"]) == 2
out2 = ra.build(n, held, watch, {"past": out["past"]}, "2026-11-05")
assert len(out2["past"]) == 2                        # 記録は週に1回だけ足す
print("OK: ランキングの集計の点検をすべて通過")
