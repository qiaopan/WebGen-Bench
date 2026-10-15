"""One figure for the task-order experiments: per order, the rolling-10 per-task accuracy gap to the No Memory
run of the same order, for each memory version, in execution order.

    python scripts/plot_order_gaps.py OUT.png ORDER_NAME:NM_DIR:LABEL=LM_DIR[,LABEL=LM_DIR] ...
Directories hold progress.jsonl and task-order.json (e.g. archive/phase2-webgen-2026-10/<run>).
"""
import json, sys
from pathlib import Path
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

def scores(d):
    r = {}
    for line in open(Path(d) / "progress.jsonl"):
        x = json.loads(line); fn = [c for c in x.get("evaluation") or [] if c.get("outcome") != "scored"]
        if fn: r[x["task_id"]] = (sum(c["outcome"] == "passed" for c in fn) + .5 * sum(c["outcome"] == "partial" for c in fn)) / len(fn)
    return r

out, panels = sys.argv[1], sys.argv[2:]
colors = {"Code memory (v7)": "#E07B39", "Final (v9.1)": "#2A78D6"}
fig, axes = plt.subplots(len(panels), 1, figsize=(8, 2.6 * len(panels)), sharex=True, squeeze=False)
for ax, spec in zip(axes[:, 0], panels):
    name, nm, lms = spec.split(":", 2)
    N = scores(nm)
    for item in lms.split(","):
        label, lm = item.split("=")
        L = scores(lm); order = json.load(open(Path(lm) / "task-order.json"))["task_ids"]
        g = [100 * (L[t] - N[t]) for t in order if t in L and t in N]
        roll = [sum(g[i - 9:i + 1]) / 10 for i in range(9, len(g))]
        ax.plot(range(10, len(g) + 1), roll, color=colors.get(label, None), lw=2, label=label)
    ax.axhline(0, color="#888", lw=1, ls=":"); ax.set_title(name, fontsize=10, loc="left")
    ax.set_ylabel("gap (points)"); ax.grid(alpha=.25)
axes[0, 0].legend(fontsize=9, loc="upper left")
axes[-1, 0].set_xlabel("execution order (task position)")
fig.tight_layout(); fig.savefig(out, dpi=200)
