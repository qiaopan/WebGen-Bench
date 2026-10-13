import json
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
E="archive/phase2-webgen-2026-10/"
ARMS=[("No Memory (baseline)","cluster_nomem_webgenlm7b_r1","#8a8a85","-"),
("Checklist only (ablation, no memory)","cluster_checklist_only_v7_webgenlm7b_r1","#2e9e6b","--"),
("v4: checklist + text memory","cluster_longmem_v4_webgenlm7b_r1","#eb6834","-"),
("v7: checklist + text + code pool","cluster_longmem_v7_webgenlm7b_r1","#2a78d6","-")]
def scores(d):
    r={}
    for l in open(E+d+"/progress.jsonl"):
        e=json.loads(l); fn=[c for c in e.get("evaluation") or [] if c.get("outcome")!="scored" and c.get("check")!="appearance"]
        if fn: r[e["task_id"]]=sum((c["outcome"]=="passed")+0.5*(c["outcome"]=="partial") for c in fn)/len(fn)
    return r
S={n:scores(d) for n,d,_,_ in ARMS}
order=[t for t in dict.fromkeys(json.loads(l)["task_id"] for l in open(E+ARMS[3][1]+"/progress.jsonl")) if all(t in S[n] for n,*_ in ARMS)]
fig,axes=plt.subplots(1,2,figsize=(13,4.6),sharey=True)
for ax,title,fn in ((axes[0],"Cumulative accuracy",lambda v,i:sum(v[:i+1])/(i+1)),(axes[1],"Rolling accuracy (last 10 tasks)",lambda v,i:sum(v[max(0,i-9):i+1])/len(v[max(0,i-9):i+1]))):
    ends=[]
    for n,_,c,ls in ARMS:
        v=[S[n][t] for t in order]; y=[100*fn(v,i) for i in range(len(v))]
        ax.plot(range(1,len(v)+1),y,color=c,lw=2.2 if "v7" in n else 1.8,ls=ls,label=n); ends.append([y[-1],y[-1],len(v),c])
    ends.sort(key=lambda e:e[0])
    for i in range(1,len(ends)): ends[i][1]=max(ends[i][1],ends[i-1][1]+3.5)
    for y,ly,x,c in ends: ax.annotate(f"{y:.1f}%",(x,y),xytext=(x+1.5,ly),color=c,fontsize=10,va="center",fontweight="bold")
    ax.axvline(30,color="#bbb",lw=1,ls=":"); ax.text(30.5,3,"task 30",color="#777",fontsize=9)
    ax.set_title(title,fontsize=12,loc="left"); ax.set_xlabel("Task position (execution order)")
    ax.grid(axis="y",color="#e5e5e2",lw=.8); ax.spines[["top","right"]].set_visible(False); ax.set_xlim(0,112)
axes[0].set_ylabel("Functional accuracy (%)"); axes[0].set_ylim(0,85)
h,l=axes[0].get_legend_handles_labels(); fig.legend(h,l,loc="lower center",ncol=4,frameon=False,fontsize=10.5)
fig.tight_layout(rect=(0,0.08,1,1)); fig.savefig("/private/tmp/claude-501/-Users-ma-Downloads-792-webgen/3e206315-6f8a-4da4-b95f-95ebdadf4f3f/scratchpad/curve4.png",dpi=200); print(len(order))
# ablation bar
fig,(a1,a2)=plt.subplots(1,2,figsize=(13,4.6),gridspec_kw={"width_ratios":[1.6,1]})
names=["No Memory","Checklist only","Checklist + memory (v7)"]; cols=["#8a8a85","#2e9e6b","#2a78d6"]
acc=[28.5,31.8,40.0]; zero=[30,18,13]
b=a1.bar(names,acc,color=cols,width=.55)
for r,v in zip(b,acc): a1.text(r.get_x()+r.get_width()/2,v+1,f"{v:.1f}%",ha="center",fontsize=12,fontweight="bold")
def br(x1,x2,y,t):
    a1.plot([x1,x1,x2,x2],[y-1,y,y,y-1],color="#14213D",lw=1.2); a1.text((x1+x2)/2,y+1,t,ha="center",fontsize=10.5)
br(0,1,37,"+3.4  CI [−2.2, 8.7]  n.s."); br(1,2,47,"+8.1  CI [2.9, 13.2]  significant")
a1.set_ylim(0,55); a1.set_ylabel("Functional accuracy (%)"); a1.set_title("Accuracy (101 tasks, paired by task)",loc="left",fontsize=12)
b=a2.bar(names,zero,color=cols,width=.55)
for r,v in zip(b,zero): a2.text(r.get_x()+r.get_width()/2,v+.6,str(v),ha="center",fontsize=12,fontweight="bold")
a2.set_ylim(0,36); a2.set_title("Zero-score tasks (lower is better)",loc="left",fontsize=12)
for a in (a1,a2):
    a.spines[["top","right"]].set_visible(False); a.grid(axis="y",color="#e5e5e2",lw=.8); a.set_axisbelow(True); a.tick_params(axis="x",labelsize=10)
fig.tight_layout(); fig.savefig("/private/tmp/claude-501/-Users-ma-Downloads-792-webgen/3e206315-6f8a-4da4-b95f-95ebdadf4f3f/scratchpad/abl.png",dpi=200)
