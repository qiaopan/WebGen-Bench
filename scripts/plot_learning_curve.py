"""Learning curve: cumulative and rolling-10 functional accuracy by task position (v7 execution order),
No Memory vs Long Memory v4 vs v7. Accuracy = (passed + 0.5 partial) / checks, appearance row excluded."""
import json, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
E = "outputs/experiment/"
ARMS = [("No Memory", "cluster_nomem_webgenlm7b_r1", "#8a8a85"),
        ("Text memory", "cluster_longmem_v4_webgenlm7b_r1", "#eb6834"),
        ("Code memory (whole-file)", "cluster_longmem_v7_webgenlm7b_r1", "#2a78d6")]
def scores(d):
    r = {}
    for line in open(E + d + "/progress.jsonl"):
        e = json.loads(line); fn = [c for c in e.get("evaluation") or [] if c.get("outcome") != "scored" and c.get("check") != "appearance"]
        if fn: r[e["task_id"]] = sum((c["outcome"] == "passed") + 0.5 * (c["outcome"] == "partial") for c in fn) / len(fn)
    return r
S = {name: scores(d) for name, d, _ in ARMS}
order = [t for t in dict.fromkeys(json.loads(l)["task_id"] for l in open(E + ARMS[2][1] + "/progress.jsonl")) if all(t in S[n] for n, _, _ in ARMS)]
fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
for ax, title, fn in ((axes[0], "Cumulative accuracy", lambda v, i: sum(v[:i + 1]) / (i + 1)),
                      (axes[1], "Rolling accuracy (last 10 tasks)", lambda v, i: sum(v[max(0, i - 9):i + 1]) / len(v[max(0, i - 9):i + 1]))):
    ends = []
    for name, _, color in ARMS:
        v = [S[name][t] for t in order]; y = [100 * fn(v, i) for i in range(len(v))]
        ax.plot(range(1, len(v) + 1), y, color=color, linewidth=2, label=name); ends.append([y[-1], y[-1], len(v)])
    ends.sort()
    for i in range(1, len(ends)):  # keep end labels at least 3.5 points apart
        ends[i][1] = max(ends[i][1], ends[i - 1][1] + 3.5)
    for y, ly, x in ends:
        ax.annotate(f"{y:.1f}%", (x, y), xytext=(x + 1.5, ly), textcoords="data", color="#333", fontsize=9, va="center")
    ax.axvline(30, color="#bbb", linewidth=1, linestyle="--"); ax.text(30.5, 3, "task 30", color="#777", fontsize=8)
    ax.set_title(title, fontsize=11, loc="left"); ax.set_xlabel("Task position (execution order)")
    ax.grid(axis="y", color="#e5e5e2", linewidth=0.8); ax.spines[["top", "right"]].set_visible(False)
axes[0].set_ylabel("Functional accuracy (%)"); axes[0].set_ylim(0, 85); axes[0].legend(frameon=False, loc="upper left")
fig.suptitle(f"WebGen-Bench, WebGen-LM-7B, single run, n={len(order)} tasks", fontsize=10, x=0.01, ha="left", color="#555")
fig.tight_layout(); out = sys.argv[1] if len(sys.argv) > 1 else "docs/reports/learning_curve_v4_v7.png"
fig.savefig(out, dpi=200); print(out, len(order))
