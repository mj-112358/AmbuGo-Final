"""Seed-level paired inference for the synthetic AmbuGo study.

Each input contains one value per independent scenario or seed. Aggregate
multiple missions within a seed before inference. Functions report sample
sizes, uncertainty estimates and the assumptions of each method."""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
from typing import Iterable
import numpy as np


def _vector(x: Iterable[float]) -> np.ndarray:
    a = np.asarray(list(x), dtype=float)
    if a.ndim != 1 or not np.isfinite(a).all():
        raise ValueError('Expected a finite one-dimensional episode-level vector')
    if len(a) < 2:
        raise ValueError('At least two independent episodes are required')
    return a


def bootstrap_mean_ci(values, *, confidence=.95, resamples=10000, seed=20261025):
    """Percentile bootstrap CI for an episode-level population mean.

    Resampling preserves all within-episode dependence. This is an approximate
    interval and should be accompanied by the sample size and raw differences.
    """
    x = _vector(values)
    rng = np.random.default_rng(seed)
    boot = np.empty(resamples)
    batch = max(1, min(512, 2000000 // len(x)))
    for start in range(0, resamples, batch):
        n = min(batch, resamples-start)
        boot[start:start+n] = x[rng.integers(0, len(x), size=(n,len(x)))].mean(axis=1)
    alpha=(1-confidence)/2
    lo,hi=np.quantile(boot,[alpha,1-alpha])
    return {'n_seeds':int(len(x)), 'mean':float(x.mean()),
            'sd':float(x.std(ddof=1)), 'se':float(x.std(ddof=1)/math.sqrt(len(x))),
            'ci_low':float(lo),'ci_high':float(hi),
            'confidence':confidence,'resamples':resamples,
            'method':'paired scenario-level percentile bootstrap; approximate coverage'}


def paired_summary(treated, comparator, **kwargs):
    a,b=_vector(treated),_vector(comparator)
    if len(a)!=len(b):
        raise ValueError('Pairing requires equal scenario counts')
    out=bootstrap_mean_ci(a-b,**kwargs)
    out['treated_mean']=float(a.mean());out['comparator_mean']=float(b.mean())
    return out


def paired_t_summary(values, confidence=.95):
    """Student-t interval and test for independent episode differences.
    
    The finite-sample calculation assumes normally distributed differences.
    Report a bootstrap sensitivity analysis alongside this parametric summary."""
    from scipy.stats import t
    x=_vector(values);n=len(x);mean=float(x.mean());sd=float(x.std(ddof=1));se=sd/math.sqrt(n)
    if se==0:
        p=1.0 if mean==0 else 0.0
        return {'n_seeds':n,'mean':mean,'sd':sd,'se':se,'ci_low':mean,'ci_high':mean,'p_value':p,'degenerate':True}
    crit=float(t.ppf((1+confidence)/2,n-1))
    p=float(2*t.sf(abs(mean/se),n-1))
    return {'n_seeds':n,'mean':mean,'sd':sd,'se':se,'ci_low':mean-crit*se,'ci_high':mean+crit*se,'p_value':p,'degenerate':False}


def sign_flip_test(values, *, permutations=20000, seed=20261025):
    """Two-sided sensitivity diagnostic for sign-exchangeable differences.
    
    Valid inference requires symmetry under the null or a randomized design
    that justifies label exchangeability. Establish this assumption from the
    experimental design in addition to using common random seeds."""
    x=_vector(values);obs=abs(float(x.mean()));n=len(x);extreme=0
    if n <= 18:
        total=2**n
        for start in range(0,total,1024):
            integers=np.arange(start,min(start+1024,total),dtype=np.uint64)
            signs=2*((integers[:,None] >> np.arange(n,dtype=np.uint64)) & 1).astype(float)-1
            extreme+=int(np.count_nonzero(np.abs(signs@x/n)>=obs-1e-14))
        p=extreme/total;mode='enumerated'
    else:
        rng=np.random.default_rng(seed);total=permutations
        for start in range(0,total,512):
            b=min(512,total-start);signs=2*rng.integers(0,2,size=(b,n))-1
            extreme+=int(np.count_nonzero(np.abs(signs@x/n)>=obs-1e-14))
        p=(extreme+1)/(total+1);mode='Monte Carlo plus-one correction'
    return {'p_value':float(p),'mode':mode,'draws':total,
            'assumption':'independent scenario differences invariant under independent sign reversal under the null',
            'role':'sensitivity diagnostic requiring sign-exchangeable scenario differences'}


def holm_adjust(p_values):
    p=np.asarray(list(p_values),dtype=float)
    if p.ndim!=1 or not np.isfinite(p).all() or np.any((p<0)|(p>1)):
        raise ValueError('p-values must be finite and in [0,1]')
    order=np.argsort(p,kind='stable');m=len(p);out=np.empty(m);running=0.
    for rank,i in enumerate(order):
        running=max(running,(m-rank)*p[i]);out[i]=min(1.,running)
    return out.tolist()


def clopper_pearson(successes, trials, confidence=.95):
    """Two-sided exact binomial interval for independent Bernoulli trials.
    
    For multiple ambulances per seed, use an episode-level indicator such as
    whether any mission missed its threshold. This retains the independent
    episode as the unit of inference."""
    from scipy.stats import beta
    k,n=int(successes),int(trials)
    if n<=0 or not 0<=k<=n:raise ValueError('Invalid binomial count')
    a=(1-confidence)/2
    lo=0. if k==0 else float(beta.ppf(a,k,n-k+1))
    hi=1. if k==n else float(beta.ppf(1-a,k+1,n-k))
    return {'events':k,'independent_trials':n,'estimate':k/n,'ci_low':lo,'ci_high':hi,'method':'Clopper-Pearson two-sided'}


def zero_event_one_sided_upper(n,confidence=.95):
    if n<=0:raise ValueError('n must be positive')
    return 1-(1-confidence)**(1/n)


def cumulative_metrics(treated,baseline,dt=1.):
    """Compute discrete paired occupancy accounting on an exhaustive partition.
    
    Arrays have shape [time, fixed spatial groups]. Include external source
    queues, internal junction space and each ordinary live vehicle exactly once.
    Integration uses grid-rectangle quadrature on the recorded time grid."""
    a=np.asarray(treated,dtype=float);b=np.asarray(baseline,dtype=float)
    if a.shape!=b.shape or a.ndim!=2 or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('Both arrays must have identical finite [time,group] shape')
    if np.any(a<0) or np.any(b<0) or dt<=0:raise ValueError('Invalid counts or step')
    d=a-b;pos=np.maximum(d,0);neg=np.maximum(-d,0)
    J=float(a.sum()*dt);J0=float(b.sum()*dt);A=float(pos.sum()*dt);B=float(neg.sum()*dt)
    delta=float(d.sum()*dt)
    if not math.isclose(delta,A-B,rel_tol=1e-10,abs_tol=1e-7):raise ArithmeticError('Paired decomposition failed')
    return {'residence_s':J,'baseline_residence_s':J0,'delta_residence_s':delta,
            'positive_spatial_burden_vehicle_s':A,'negative_spatial_burden_vehicle_s':B,
            'terminal_delta_vehicles':float(d[-1].sum()) if len(d) else 0.,
            'terminal_L1_spatial_difference':float(np.abs(d[-1]).sum()) if len(d) else 0.}


def paired_csv(path,metric,policy_key='policy',seed_key='seed',baseline='no_priority',group_keys=('load','missions')):
    rows=list(csv.DictReader(Path(path).open()));groups={}
    for row in rows:
        g=tuple(row[k] for k in group_keys);groups.setdefault(g,{}).setdefault(row[policy_key],{})[row[seed_key]]=float(row[metric])
    results=[]
    for g,policies in sorted(groups.items()):
        if baseline not in policies:continue
        ref=policies[baseline]
        for p,values in sorted(policies.items()):
            if p==baseline:continue
            if set(values)!=set(ref):raise ValueError(f'Missing pairs in {g}: {p}')
            seeds=sorted(ref);d=[values[s]-ref[s] for s in seeds]
            stat=bootstrap_mean_ci(d);stat.update(dict(zip(group_keys,g)));stat.update(policy=p,baseline=baseline,metric=metric)
            results.append(stat)
    return results


def self_check():
    z=paired_summary([1,2,3],[1,2,3],resamples=100)
    assert z['mean']==z['ci_low']==z['ci_high']==0
    z=holm_adjust([.01,.04,.03]);assert np.allclose(z,[.03,.06,.06])
    z=cumulative_metrics([[1,2],[2,1]],[[2,1],[1,2]])
    assert z['delta_residence_s']==0 and z['positive_spatial_burden_vehicle_s']==2
    z=sign_flip_test([1,1],permutations=100);assert z['p_value']==.5
    assert .01<zero_event_one_sided_upper(200)<.02
    return {'checks_passed':5,'scope':'statistical utility identities and interval calculations'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--self-check',action='store_true');p.add_argument('--csv');p.add_argument('--metric');p.add_argument('--baseline',default='no_priority');p.add_argument('--out');a=p.parse_args()
    if a.self_check:print(json.dumps(self_check(),indent=2))
    elif a.csv and a.metric:
        ans=paired_csv(a.csv,a.metric,baseline=a.baseline)
        if a.out:Path(a.out).write_text(json.dumps(ans,indent=2))
        else:print(json.dumps(ans,indent=2))
    else:p.print_help()
