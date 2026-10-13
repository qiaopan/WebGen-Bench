"""Paired analysis of one task-order experiment (Long Memory vs No Memory, alternating pairs), plus a rolling-10
gap plot. Accuracy = (passed + 0.5 partial) / checks, appearance row excluded, pooled over checks.

    python scripts/analyze_order_run.py LM_DIR NM_DIR [--plot OUT.png --title T] [--extra NAME=DIR ...]
"""
import argparse, json, random, sys
from pathlib import Path
ap = argparse.ArgumentParser(); ap.add_argument("lm"); ap.add_argument("nm")
ap.add_argument("--plot"); ap.add_argument("--title", default=""); ap.add_argument("--extra", nargs="*", default=[])
a = ap.parse_args()
E = Path("outputs/experiment")
def scores(d):
    r = {}
    for line in open(E / d / "progress.jsonl"):
        x = json.loads(line); fn = [c for c in x.get("evaluation") or [] if c.get("outcome") != "scored" and c.get("check") != "appearance"]
        if fn: r[x["task_id"]] = (sum(c["outcome"] == "passed" for c in fn) + .5 * sum(c["outcome"] == "partial" for c in fn), len(fn))
    return r
def scaffold(d, t):
    sites = [p for p in (E / d / "tasks" / t).glob("*/extracted/*/package.json") if "node_modules" not in p.parts]
    if not sites: return None
    v = {p.name for p in sites[0].parent.rglob("*.vue") if "node_modules" not in p.parts}
    return bool(v) and v <= {"App.vue", "HelloWorld.vue"}
L, N = scores(a.lm), scores(a.nm)
order = json.load(open(E / a.lm / "task-order.json"))["task_ids"]
ts = [t for t in order if t in L and t in N]
acc = lambda s, x: 100 * sum(s[t][0] for t in x) / sum(s[t][1] for t in x)
def ci(d):
    random.seed(0); bs = sorted(sum(random.choice(d) for _ in d) / len(d) for _ in range(10000))
    return 100 * sum(d) / len(d), 100 * bs[250], 100 * bs[9750]
d = [L[t][0] / L[t][1] - N[t][0] / N[t][1] for t in ts]
m, lo, hi = ci(d)
out = {"n": len(ts), "nm": round(acc(N, ts), 1), "lm": round(acc(L, ts), 1), "diff": round(m, 1), "ci": [round(lo, 1), round(hi, 1)],
       "win_lose_tie": [sum(x > 0 for x in d), sum(x < 0 for x in d), sum(x == 0 for x in d)],
       "zero_nm_lm": [sum(N[t][0] == 0 for t in ts), sum(L[t][0] == 0 for t in ts)],
       "first30_nm_lm": [round(acc(N, ts[:30]), 1), round(acc(L, ts[:30]), 1)],
       "rest_nm_lm": [round(acc(N, ts[30:]), 1), round(acc(L, ts[30:]), 1)] if ts[30:] else None,
       "scaffold_nm_lm": [sum(bool(scaffold(a.nm, t)) for t in ts), sum(bool(scaffold(a.lm, t)) for t in ts)]}
for e in a.extra:
    name, dd = e.split("="); X = scores(dd); c = [t for t in ts if t in X]
    dx = [X[t][0] / X[t][1] - L[t][0] / L[t][1] for t in c]; mx, lx, hx = ci(dx)
    out[name] = {"n": len(c), "nm": round(acc(N, c), 1), "lm": round(acc(L, c), 1), name: round(acc(X, c), 1),
                 "minus_lm": [round(mx, 1), round(lx, 1), round(hx, 1)], "zero": sum(X[t][0] == 0 for t in c),
                 "scaffold": sum(bool(scaffold(dd, t)) for t in c)}
print(json.dumps(out, ensure_ascii=False))
if a.plot:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    g = [100 * x for x in d]; y = [sum(g[i - 9:i + 1]) / 10 for i in range(9, len(g))]  # full windows only
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.axhline(0, color="#555", linewidth=1, linestyle="--"); ax.axvline(30, color="#bbb", linewidth=1)
    ax.plot(range(10, len(g) + 1), y, color="#2a78d6", linewidth=2, label="Long Memory (v7) − No Memory")
    ax.text(len(g) + 1, y[-1], f"{y[-1]:+.1f}", color="#2a78d6", va="center", fontsize=9)
    ax.set_xlabel("execution order (task position)"); ax.set_ylabel("rolling-10 accuracy gap (points)")
    ax.set_title(a.title, fontsize=11); ax.legend(loc="lower right", frameon=False)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    fig.tight_layout(); fig.savefig(a.plot, dpi=160)
