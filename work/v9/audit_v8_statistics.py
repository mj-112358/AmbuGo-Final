"""Audit the supplied v8 CSV records and compute independent statistical summaries."""
import csv,json,collections,math,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
P=ROOT/'teammate_v8/ambugo_v8/results'

def rows(name):return list(csv.DictReader((P/name).open()))
R=rows('eval_runs.csv');T=rows('tables/main_results.csv');C=rows('tables/policy_contrasts.csv')
G=collections.defaultdict(list)
for r in R:G[(float(r['X']),float(r['rho']),r['policy'])].append(r)
keys=[(float(r['X']),float(r['rho']),r['policy'],int(r['rep'])) for r in R]
B={(float(r['X']),float(r['rho']),int(r['rep'])):r for r in R if r['policy']=='P0'}
expected={(x,r,p) for x in (.6,.7,.8,.85,.9,.95) for r in (0.,.5) for p in ('P0','P1','P2','P3','P3C','P4')}
assert set(G)==expected
assert len(R)==14400 and len(set(keys))==len(R)
assert all({int(r['rep']) for r in g}==set(range(200)) for g in G.values())
assert all(all(r[k]==B[(float(r['X']),float(r['rho']),int(r['rep']))][k] for k in ['origin','dispatch','incident']) for r in R)
max_identity=max(abs(float(r['d_delay_vh'])-(float(r['delay_vh'])-float(B[(float(r['X']),float(r['rho']),int(r['rep']))]['delay_vh']))) for r in R if r['policy']!='P0')
assert max_identity<1e-10
# All original bootstrap calls use seed0, 200 rows and 10000 draws. Reconstruct
# the index distribution independently once, preserving archived row order.
idx=np.random.default_rng(0).integers(0,200,size=(10000,200))
def ci(a):
 a=np.asarray(a,float);v=a[idx].mean(axis=1);return np.array([a.mean(),*np.quantile(v,[.025,.975])])
def arr(group,name):return np.array([float(r[name]) for r in group])
def paired_group(x,r,p):
 base=G[(x,r,'P0')];d={int(z['rep']):z for z in G[(x,r,p)]};return base,[d[int(z['rep'])] for z in base]
errors=collections.defaultdict(float)
pvals=[];pkeys=[]
for t in T:
 x,r,p=float(t['X']),float(t['rho']),t['policy'];base,g=paired_group(x,r,p)
 errors['amb_mean']=max(errors['amb_mean'],abs(float(t['amb_mean'])-arr(g,'amb_tt').mean()))
 errors['wait_mean']=max(errors['wait_mean'],abs(float(t['n_wait_over_mean'])-arr(g,'n_wait_over').mean()))
 if p=='P0':continue
 for vals,names in [(arr(g,'amb_tt')-arr(base,'amb_tt'),['d_amb_mean','d_amb_lo','d_amb_hi']),(arr(g,'d_delay_vh'),['d_delay_mean','d_delay_lo','d_delay_hi']),(arr(g,'d_delay_ph'),['d_pdelay_mean','d_pdelay_lo','d_pdelay_hi'])]:
  computed=ci(vals);stored=np.array([float(t[k]) for k in names]);errors['bootstrap_all_coordinates']=max(errors['bootstrap_all_coordinates'],float(abs(computed-stored).max()))
 signs=np.random.default_rng(0).choice([-1.,1.],size=(20000,200));v=arr(g,'d_delay_vh');null=np.abs((signs*v).mean(axis=1));pvals.append((1+int(np.count_nonzero(null>=abs(v.mean())-1e-12)))/20001);pkeys.append((x,r,p))
assert errors['amb_mean']<5.01e-5 and errors['bootstrap_all_coordinates']<5.01e-5
order=np.argsort(pvals);adjusted=np.empty(len(pvals));running=0
for rank,i in enumerate(order):running=max(running,(len(pvals)-rank)*pvals[i]);adjusted[i]=min(1,running)
adj=dict(zip(pkeys,adjusted))
for t in T:
 if t['policy']=='P0':continue
 k=(float(t['X']),float(t['rho']),t['policy']);errors['Holm']=max(errors['Holm'],abs(float(t['p_delay_holm'])-adj[k]))
assert errors['Holm']<5.01e-5
contrast_rows=[]
for t in C:
 x,r=float(t['X']),float(t['rho']);a,b=t['contrast'].split('-');gb,ga=sorted(paired_group(x,r,b)[1],key=lambda z:int(z['rep'])),sorted(paired_group(x,r,a)[1],key=lambda z:int(z['rep']))
 for name,names in [('amb_tt',['d_amb','d_amb_lo','d_amb_hi']),('delay_vh',['d_delay_vh','d_delay_lo','d_delay_hi'])]:
  v=ci(arr(ga,name)-arr(gb,name));stored=np.array([float(t[k]) for k in names]);errors['policy_contrast_coordinates']=max(errors['policy_contrast_coordinates'],float(abs(v-stored).max()))
assert errors['policy_contrast_coordinates']<.000501
# Tail entries: counts and exact intervals checked if installed scipy available.
TAIL=rows('tables/tail_risk.csv');tail_counts=True;tail_max_ci_error=None
try:
 from scipy.stats import beta
 tail_max_ci_error=0.
except ImportError: beta=None
for t in TAIL:
 x,r,p=float(t['X']),float(t['rho']),t['policy'];v=arr(G[(x,r,p)],'amb_tt');n=len(v);k=int((v>float(t['threshold_s'])).sum());tail_counts&=(int(t['n'])==n and int(t['late'])==k)
 if beta:
  lo=0 if k==0 else beta.ppf(.025,k,n-k+1);hi=1 if k==n else beta.ppf(.975,k+1,n-k)
  tail_max_ci_error=max(tail_max_ci_error,abs(float(t['cp_lo'])-lo),abs(float(t['cp_hi'])-hi))
assert tail_counts
# Fit alternatives summarize the shape of the retained observations descriptively.
xs=np.array([.6,.7,.8,.85,.9,.95]);ys=np.array([arr(G[(x,0.,'P2')],'d_delay_vh').mean() for x in xs]);fits={}
for name,M in [('inverse_zero_intercept',(1/(1-xs))[:,None]),('linear',np.array([np.ones(6),xs]).T),('quadratic',np.array([np.ones(6),xs,xs*xs]).T),('inverse_with_intercept',np.array([np.ones(6),1/(1-xs)]).T)]:
 b=np.linalg.lstsq(M,ys,rcond=None)[0];sse=float(sum((ys-M@b)**2));fits[name]={'parameters':b.tolist(),'sse':sse,'r2':1-sse/sum((ys-ys.mean())**2)}
out={'audit_date':'2026-10-25','scope':'read-only CSV and statistics audit; traffic reproduction performed separately',
'raw_rows':len(R),'cells':len(G),'replications_per_cell':200,'seeds':[0,199],'duplicate_cell_rep_keys':0,
'matching_dispatch_origin_incident_within_pairs':True,'finite_ambulance_outcomes':all(math.isfinite(float(r['amb_tt'])) for r in R),'maximum_ambulance_time_s':max(float(r['amb_tt']) for r in R),
'stored_gridlock_count':sum(r['gridlock']=='True' for r in R),'signed_paired_residence_identity_max_abs_error_vh':max_identity,
'independently_recomputed_main_table_rows':len(T),'independently_recomputed_contrast_rows':len(C),'max_rounding_errors':dict(errors),
'exact_tail_count_match':tail_counts,'max_Clopper_Pearson_interval_rounding_error':tail_max_ci_error,
'auxiliary_raw_row_counts':{f.name:sum(1 for _ in csv.DictReader(f.open())) for f in P.glob('*runs.csv')},
'descriptive_scaling_fits_six_means':fits,'scaling_warning':'Unweighted in-sample fit on six selected means; no universal law is established. Quadratic has extra parameter and is not declared the true law.',
'files_sha256':{name:hashlib.sha256((P/name).read_bytes()).hexdigest() for name in ['eval_runs.csv','tables/main_results.csv','tables/policy_contrasts.csv','tables/tail_risk.csv']}}
(ROOT/'v8_statistics_audit.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
