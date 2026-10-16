import json,random,os,sys
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
def P(d):
    for b in ("outputs/experiment/","archive/phase2-webgen-2026-10/"):
        if os.path.exists(b+d+"/progress.jsonl"): return b+d
def sc(d):
    r={}
    for l in open(P(d)+"/progress.jsonl"):
        x=json.loads(l); fn=[c for c in x.get("evaluation") or [] if c.get("outcome")!="scored" and c.get("check")!="appearance"]
        if fn: r[x["task_id"]]=(sum(c["outcome"]=="passed" for c in fn)+.5*sum(c["outcome"]=="partial" for c in fn),len(fn))
    return r
NM1=sc("cluster_nomem_webgenlm7b_r1")
O=[("Manifest","cluster_nomem_webgenlm7b_r1","cluster_longmem_v7_webgenlm7b_r1","cluster_manifest_longmem_v9_1_webgenlm7b","manifest"),
("Seed 11 (blocks)","cluster_order_blocks11_nomem","cluster_order_blocks11_longmem_v7","cluster_order_blocks11_longmem_v9_1",None),
("Seed 29 (random)","cluster_order_random29_nomem","cluster_order_random29_longmem_v7","cluster_order_random29_longmem_v9_1",None),
("Seed 47 (blocks)","cluster_order_blocks47_nomem",None,"cluster_order_blocks47_longmem_v9_1",None),
("Interleaved","cluster_order_interleave_nomem",None,"cluster_order_interleave_longmem_v9_1",None)]
man=json.load(open("archive/phase2-webgen-2026-10/cluster_manifest_longmem_v9_1_webgenlm7b/task-order.json"))["task_ids"] if os.path.exists("archive/phase2-webgen-2026-10/cluster_manifest_longmem_v9_1_webgenlm7b/task-order.json") else [json.loads(l)["task_id"] for l in open(P("cluster_longmem_v7_webgenlm7b_r1")+"/progress.jsonl")]
acc=lambda s,ts:100*sum(s[t][0] for t in ts)/sum(s[t][1] for t in ts)
def ci(d):
    random.seed(0); bs=sorted(sum(random.choice(d) for _ in d)/len(d) for _ in range(10000)); return 100*sum(d)/len(d),100*bs[250],100*bs[9750]
fig,axs=plt.subplots(1,5,figsize=(20,3.8),sharey=True)
for ax,(name,nm,v7,v9,_) in zip(axs,O):
    N=sc(nm); fill=0
    for t,v in NM1.items():
        if t not in N: N[t]=v; fill+=1
    V9=sc(v9); V7=sc(v7) if v7 else {}
    order=json.load(open(P(v9)+"/task-order.json"))["task_ids"] if os.path.exists(P(v9)+"/task-order.json") else man
    ts=[t for t in order if t in V9]
    z=lambda s:sum(s[t][0]==0 for t in ts)
    row=f"{name:18s} n={len(ts):3d} NMfill={fill:3d} NM {acc(N,ts):5.1f} z{z(N):2d}"
    if V7: row+=f" | v7 {acc(V7,ts):5.1f} z{z(V7):2d} d={ci([V7[t][0]/V7[t][1]-N[t][0]/N[t][1] for t in ts])}"
    d9=[V9[t][0]/V9[t][1]-N[t][0]/N[t][1] for t in ts]
    row+=f" | v9.1 {acc(V9,ts):5.1f} z{z(V9):2d} d=%+.1f [%.1f, %.1f]"%ci(d9)
    if V7: row+=" | v9.1-v7 %+.1f [%.1f, %.1f]"%ci([V9[t][0]/V9[t][1]-V7[t][0]/V7[t][1] for t in ts])
    print(row)
    def roll(dd): return [100*sum(dd[max(0,i-9):i+1])/len(dd[max(0,i-9):i+1]) for i in range(len(dd))]
    x=range(1,len(ts)+1)
    if V7: ax.plot(x,roll([V7[t][0]/V7[t][1]-N[t][0]/N[t][1] for t in ts]),color="#eb6834",lw=1.8,label="v7 − No Memory")
    ax.plot(x,roll(d9),color="#2a78d6",lw=2.2,label="v9.1 − No Memory")
    ax.axhline(0,color="#999",lw=1); ax.set_title(f"{name} (n={len(ts)})",fontsize=11,loc="left")
    ax.set_xlabel("Task position"); ax.grid(axis="y",color="#e5e5e2"); ax.spines[["top","right"]].set_visible(False)
axs[0].set_ylabel("Rolling-10 accuracy gap (points)"); axs[0].legend(frameon=False,fontsize=9,loc="lower left")
fig.tight_layout(); fig.savefig(sys.argv[1],dpi=180)
