"""Render the publication algorithm flowchart from its diagram specification."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'vendor'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, PathPatch
from matplotlib.path import Path as MPath

OUT=HERE/'figures';OUT.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.fonttype':'none','savefig.facecolor':'white'})
fig,ax=plt.subplots(figsize=(6.8,4.5),dpi=220)
fig.subplots_adjust(left=0,right=1,bottom=0,top=1)
ax.set(xlim=(0,6.8),ylim=(0,4.5));ax.axis('off')
ink='#20313d';blue='#315e78';pale='#eef4f7';warm='#f4f0e7';grey='#59636b';light='#f7f7f7'

def box(x,y,w,h,lines,fill=pale,dashed=False):
    p=FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.025,rounding_size=0.055',lw=.9,ec=grey if dashed else blue,fc=fill,linestyle=(0,(4,3)) if dashed else 'solid',zorder=3)
    ax.add_patch(p)
    n=len(lines)
    for i,txt in enumerate(lines):
        yy=y+h/2+(n-1-2*i)*.082
        ax.text(x+w/2,yy,txt,ha='center',va='center',fontsize=10 if i==0 else 9.5,fontweight='bold' if i==0 else 'normal',color=ink,zorder=4)

def line(points,color=blue,lw=1.05,dashed=False,head=True):
    pp=MPath(points,[MPath.MOVETO]+[MPath.LINETO]*(len(points)-1))
    p=FancyArrowPatch(path=pp,arrowstyle='-|>' if head else '-',mutation_scale=9,lw=lw,color=color,linestyle=(0,(4,3)) if dashed else 'solid',joinstyle='round',capstyle='round',zorder=2)
    ax.add_patch(p)

# Observation and progress state are available before selecting a local policy mode.
box(.25,3.70,1.70,.55,['Received counts','Position and history'])
box(2.30,3.70,2.20,.55,['Regular-edge progress','Elapsed time − free flow'])
box(4.90,3.70,1.65,.55,['Per-mission mode',r'Switch once at $D>\gamma$'])
line([(1.975,3.975),(2.265,3.975)])
line([(4.525,3.975),(4.865,3.975)])

# Branches are the two modes of the same route and control system.
box(.60,2.62,2.60,.68,['Selective joint choice','Finite routes × actions','Time band, then burden'])
box(3.70,2.62,2.60,.68,['Aggressive joint choice','Route anticipates priority','Strong preemption'],fill=warm)
line([(5.20,3.675),(5.20,3.50),(1.90,3.50),(1.90,3.335)])
ax.text(3.55,3.52,'selective',ha='center',va='bottom',fontsize=9,color=grey)
line([(6.20,3.675),(6.20,3.40),(5.00,3.40),(5.00,3.335)])
ax.text(6.12,3.44,'escalated',ha='right',va='bottom',fontsize=9,color=grey)

# Both branches produce a route and a signal request, then share all safety logic.
line([(1.90,2.595),(1.90,2.30)],head=False)
line([(5.00,2.595),(5.00,2.30),(1.125,2.30),(1.125,2.005)])
ax.plot(1.90,2.30,'o',ms=2.8,color=blue,zorder=3)
ax.text(3.48,2.18,'route and priority request',ha='center',va='center',fontsize=9,color=grey)
box(.25,1.25,1.75,.70,['Bounded leases','Dispatch arbitration'])
box(2.35,1.25,2.50,.70,['Legal signal controller','Min green 8 · amber 3 · red 2 s','Ped slot 25 s · age guard'])
box(5.20,1.25,1.35,.70,['SUMO plant','Physical traffic'])
line([(2.025,1.60),(2.315,1.60)])
line([(4.875,1.60),(5.165,1.60)])

# The plant feedback carries observations, never prospective simulator outcomes.
line([(6.575,1.60),(6.69,1.60),(6.69,4.39),(.11,4.39),(.11,3.975),(.215,3.975)],lw=.9)

# The evaluation ledger has an input from logged plant states and no output to control.
box(.25,.15,6.30,.68,['Paired S0 evaluation ledger',r'Signed residence $\Delta J$  ·  spatial exposure $A$  ·  individual harm $D^{+}$'],fill=light,dashed=True)
line([(5.875,1.225),(5.875,.865)],color=grey,dashed=True,lw=.9)
ax.text(4.72,1.04,'logged states only',ha='center',va='center',fontsize=9,color=grey)
fig.savefig(OUT/'method.png',dpi=300)
fig.savefig(OUT/'method.svg')
plt.close(fig)
caption='''Figure. Joint ambulance routing and selective signal priority with a causal progress guard. Received counts and observed executed progress on regular road links determine each ambulance's mode. Selective mode evaluates a finite route–action library using a predicted time band and an approximate ordinary-traffic burden; an irreversible progress-triggered switch invokes aggressive joint routing and preemption. Both modes share request arbitration, service-age protection and legal signal clearances. The 8 s green label denotes a minimum, while amber, all-red and the reserved pedestrian opportunity last 3, 2 and 25 s. The separate paired-S0 ledger (executable policy P0) evaluates signed restricted residence change ΔJ, positive spatial exposure A and positive individual residence burden D⁺ from logged trajectories; those evaluation quantities are computed from the paired records. The pedestrian opportunity is a fixed signal reservation, and the traffic parameters specify the synthetic scenario.'''
(OUT/'method_caption.txt').write_text(caption+'\n')
print(OUT/'method.png')
