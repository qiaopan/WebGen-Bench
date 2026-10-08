"""Rolling-10 per-task accuracy gap to No Memory (v7 - NM, v4 - NM) by v7 execution order.
Accuracy = (passed + 0.5 partial) / checks, appearance row excluded; gap in percentage points."""
import json, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
E = "outputs/experiment/"
NM = "cluster_nomem_webgenlm7b_r1"
ARMS = [("v7 − No Memory", "cluster_longmem_v7_webgenlm7b_r1", "#2a78d6"),
        ("v4 − No Memory", "cluster_longmem_v4_webgenlm7b_r1", "#eb6834")]
def scores(d):
    r = {}
    for line in open(E + d + "/progress.jsonl"):
        e = json.loads(line); fn = [c for c in e.get("evaluation") or [] if c.get("outcome") != "scored" and c.get("check") != "appearance"]
        if fn: r[e["task_id"]] = sum((c["outcome"] == "passed") + 0.5 * (c["outcome"] == "partial") for c in fn) / len(fn)
    return r
base = scores(NM); S = {d: scores(d) for _, d, _ in ARMS}
order = [t for t in dict.fromkeys(json.loads(l)["task_id"] for l in open(E + ARMS[0][1] + "/progress.jsonl")) if t in base and all(t in S[d] for _, d, _ in ARMS)]
fig, ax = plt.subplots(figsize=(11, 4.6))
ax.axhline(0, color="#555", linewidth=1, linestyle="--")
for x, lab in ((30, "tasks 1–30 | 31–60"), (60, "31–60 | 61–101")):
    ax.axvline(x, color="#bbb", linewidth=1); ax.text(x + 0.8, 37, lab, color="#777", fontsize=8)
ends = []
for name, d, color in ARMS:
    g = [100 * (S[d][t] - base[t]) for t in order]
    y = [sum(g[max(0, i - 9):i + 1]) / len(g[max(0, i - 9):i + 1]) for i in range(len(g))]
    ax.plot(range(1, len(y) + 1), y, color=color, linewidth=2, label=name); ends.append([y[-1], y[-1], name])
ends.sort()
for i in range(1, len(ends)):
    ends[i][1] = max(ends[i][1], ends[i - 1][1] + 4)
for y, ly, name in ends:
    ax.annotate(f"{y:+.1f} pp", (len(order), y), xytext=(len(order) + 1.5, ly), textcoords="data", color="#333", fontsize=9, va="center")
ax.set_ylim(-40, 40); ax.set_xlim(0, len(order) + 9)
ax.set_xlabel("Task position (execution order)"); ax.set_ylabel("Gap to No Memory (percentage points)")
ax.set_title("Rolling 10-task accuracy gap to No Memory (positive = Long Memory better)", fontsize=11, loc="left")
ax.grid(axis="y", color="#e5e5e2", linewidth=0.8); ax.spines[["top", "right"]].set_visible(False)
ax.legend(frameon=False, loc="lower left")
fig.text(0.01, 0.01, f"WebGen-Bench, WebGen-LM-7B, single run, n={len(order)} tasks", fontsize=8, color="#777")
fig.tight_layout(); out = sys.argv[1] if len(sys.argv) > 1 else "docs/reports/gap_curve_v4_v7.png"
fig.savefig(out, dpi=200); print(out, len(order))
