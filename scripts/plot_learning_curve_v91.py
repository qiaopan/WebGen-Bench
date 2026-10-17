import json, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
A="archive/phase2-webgen-2026-10/"; E="outputs/experiment/"
def scores(d):
    r={}
    for line in open(d+"/progress.jsonl"):
        e=json.loads(line); fn=[c for c in e.get("evaluation") or [] if c.get("outcome")!="scored" and c.get("check")!="appearance"]
        if fn: r[e["task_id"]]=(sum((c["outcome"]=="passed")+0.5*(c["outcome"]=="partial") for c in fn),len(fn))
    return r
NM=("No Memory",A+"cluster_nomem_webgenlm7b_r1","#8a8a85","-")
LEFT=[NM,("Text memory",A+"cluster_longmem_v4_webgenlm7b_r1","#eb6834","-"),
      ("Code memory (whole-file)",A+"cluster_longmem_v7_webgenlm7b_r1","#2a78d6","-"),
      ("Code memory (fragments), run 1",A+"cluster_manifest_longmem_v9_1_webgenlm7b","#2e9e5b","-")]
RIGHT=[NM,("Fixed code prefix",E+"cluster_fixed_prefix_v9_1_webgenlm7b","#7b3fb5","--"),
      ("Code memory (fragments), run 1",A+"cluster_manifest_longmem_v9_1_webgenlm7b","#2e9e5b","-"),
      ("Code memory (fragments), run 2",E+"cluster_manifest_longmem_v9_1_webgenlm7b_r2","#0b5d32","-.")]
S={d:scores(d) for _,d,_,_ in LEFT+RIGHT}
order=[t for t in dict.fromkeys(json.loads(l)["task_id"] for l in open(LEFT[3][1]+"/progress.jsonl")) if all(t in S[d] for _,d,_,_ in LEFT+RIGHT)]
fig,axes=plt.subplots(1,2,figsize=(11,4),sharey=True)
for ax,title,arms in ((axes[0],"Memory designs",LEFT),(axes[1],"Fixed prefix and repeat run",RIGHT)):
    ends=[]
    for name,d,color,ls in arms:
        v=[S[d][t] for t in order]; y=[100*sum(a for a,_ in v[:i+1])/sum(n for _,n in v[:i+1]) for i in range(len(v))]
        ax.plot(range(1,len(v)+1),y,color=color,linewidth=2,linestyle=ls,label=name); ends.append([y[-1],y[-1],len(v)])
    ends.sort()
    for i in range(1,len(ends)): ends[i][1]=max(ends[i][1],ends[i-1][1]+3.5)
    for y,ly,x in ends: ax.annotate(f"{y:.1f}%",(x,y),xytext=(x+1.5,ly),textcoords="data",color="#333",fontsize=9,va="center")
    ax.axvline(30,color="#bbb",linewidth=1,linestyle="--"); ax.text(30.5,3,"task 30",color="#777",fontsize=8)
    ax.set_title(title,fontsize=11,loc="left"); ax.set_xlabel("Task position (execution order)")
    ax.grid(axis="y",color="#e5e5e2",linewidth=0.8); ax.spines[["top","right"]].set_visible(False)
    ax.legend(frameon=False,loc="upper right",fontsize=8.5)
axes[0].set_ylabel("Cumulative accuracy (%)"); axes[0].set_ylim(0,85)
fig.suptitle(f"WebGen-Bench, WebGen-LM-7B, manifest order, n={len(order)} tasks",fontsize=10,x=0.01,ha="left",color="#555")
fig.tight_layout(); fig.savefig(sys.argv[1],dpi=200); print(len(order))
