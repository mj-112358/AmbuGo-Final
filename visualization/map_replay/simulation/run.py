#!/usr/bin/env python3
"""Reproduce the two recorded episodes without overwriting the shipped replays."""
from pathlib import Path
import argparse,hashlib,importlib.metadata,json,os,platform,sys,time

HERE=Path(__file__).resolve().parent
PINNED={'numpy':'2.5.4','networkx':'3.7','libsumo':'1.28.0',
        'sumolib':'1.28.0','traci':'1.28.0','sumo-data':'1.28.0','eclipse-sumo':'1.28.0'}
EXPECTED_DEMAND='574223d825fdba35922d91a00e5efa5ff0877ccd14f6a66720935679bf606c09'
EXPECTED_NET='bde374f42e5a34567bd053eefb0f9d39cd1702c651da2e50aae2a1346cecd917'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def environment():
    versions={name:importlib.metadata.version(name) for name in PINNED}
    return dict(python=sys.version,platform=platform.platform(),packages=versions,
                exact_pinned_versions=versions==PINNED)

def compare_arrays(produced,reference):
    import numpy as np
    with np.load(produced) as a,np.load(reference) as b:
        checks={}
        for key in sorted(set(a.files)|set(b.files)):
            if key not in a.files or key not in b.files:
                checks[key]={'equal':False,'reason':'array missing'};continue
            same=a[key].shape==b[key].shape
            equal=same and np.array_equal(a[key],b[key],equal_nan=True)
            record=dict(equal=bool(equal),shape=list(a[key].shape),dtype=str(a[key].dtype))
            if not equal and same:
                aa=a[key].astype(float);bb=b[key].astype(float)
                finite=np.isfinite(aa)&np.isfinite(bb)
                record['maximum_absolute_finite_error']=float(np.max(np.abs(aa[finite]-bb[finite]))) if finite.any() else None
            checks[key]=record
        return dict(all_arrays_equal=all(v['equal'] for v in checks.values()),arrays=checks)

def smoke(rp,output):
    """Ten simulation seconds with the exact network/demand and actual controller."""
    rp.HERE=output;output.mkdir(parents=True,exist_ok=True)
    config=json.loads((HERE/'inputs/config.json').read_text())
    net=HERE/'inputs/mohali_urban.net.xml'
    _,g,m,links,s=rp.make_inputs(net,config)
    assert s['schedule_sha256']==EXPECTED_DEMAND
    c=dict(rp.ss.DEFAULTS);c.update(step=.5,sensor_period=5,sensor_delay=2,sensor_noise=True,
                                   harm_budget=1000.,epsilon=0.,action_mode='strong',progress_guard_s=20.)
    sigs={j:rp.ss.Signal(j,s['design']['plans'][j],[links[j][k] for k in range(max(links[j])+1)],
                         rp.ss.stable_rng(0,'offset',j).randrange(len(s['design']['plans'][j]['arms']))) for j in m['juncs']}
    ctl=rp.RealMapController(m,s,sigs,'P3',c,turngraph=g,destination=config['destination_edge'])
    tr=rp.traci;tr.start(['sumo','-n',str(net),'-r',s['route_file'],'--step-length','.5',
                        '--seed',str(config['seed']),'--no-step-log','true',
                        '--duration-log.disable','true','--no-warnings','true',
                        '--time-to-teleport','-1','--collision.action','warn'])
    collisions=0
    try:
        version=tr.getVersion()
        for half in range(20):
            if half%2==0:
                t=half//2;ctl.observe(t,{e:tr.edge.getLastStepVehicleNumber(e) for e in m['edges']})
                req=ctl.requests_at(t,[])
                for j,signal in sigs.items():signal.update(t,req.get(j),ctl.obs,base='fixed')
            tr.simulationStep();collisions+=tr.simulation.getCollidingVehiclesNumber()
        coord=list(tr.simulation.convertGeo(2412.505,4138.7475))
        elapsed=tr.simulation.getTime()
    finally:tr.close()
    result=dict(test='10-second in-process simulator and controller smoke test',
                passed=elapsed==10 and collisions==0,simulated_seconds=elapsed,
                collisions=collisions,network_edges=len(m['edges']),controllers=len(sigs),
                sumo_version=version,coordinate_conversion_example_lonlat=coord,
                demand_sha256=s['schedule_sha256'],environment=environment())
    (output/'smoke_result.json').write_text(json.dumps(result,indent=2))
    return result

def reproduce(rp,case,output,reference_dir):
    import instrumentation as ins
    import numpy as np
    policy='P3' if case=='B1000' else 'P0'
    folder=output/case;folder.mkdir(parents=True,exist_ok=True);rp.HERE=folder
    base_class=ins.Base
    rp.RealMapController=ins.ExplainedController if case=='B1000' else base_class
    ins.BUDGET=1000.;ins.instances.clear()
    original_make_inputs=rp.make_inputs
    def checked_inputs(net,config):
        result=original_make_inputs(net,config)
        if result[-1]['schedule_sha256']!=EXPECTED_DEMAND:
            raise RuntimeError('Generated demand differs from the frozen episode. Check pinned versions and inputs.')
        return result
    rp.make_inputs=checked_inputs
    config=json.loads((HERE/'inputs/config.json').read_text())
    try:rp.run(policy,HERE/'inputs/mohali_urban.net.xml',config)
    finally:rp.RealMapController=base_class;rp.make_inputs=original_make_inputs
    new=json.loads((folder/(policy+'.json')).read_text())
    old=json.loads((HERE/'reference'/f'{case}_summary.json').read_text())
    fields=['missions','plans','progress_guard_log','route_changes','priority_phase_admissions',
            'signal_timing_violations','collision_events','teleport_events','schedule_sha256',
            'ordinary_completed','ordinary_scheduled','net_sha256','frozen_controller_sha256','edge_ids','junction_ids','routes']
    report=dict(case=case,policy=policy,fields={k:new[k]==old[k] for k in fields},environment=environment())
    expected_replay=reference_dir/(policy+'.npz')
    if not expected_replay.exists():
        raise FileNotFoundError(f'Missing stored replay for numerical verification: {expected_replay}')
    report.update(compare_arrays(folder/(policy+'.npz'),expected_replay))
    ordinary=json.loads((folder/(policy+'_ordinary_events.json')).read_text())
    report['ordinary_event_records_equal']=ordinary==json.loads((HERE/'reference'/f'{case}_ordinary_events.json').read_text())
    if case=='B1000':
        ctl=ins.instances[-1]
        log=dict(budget_veh_s=1000,provenance='Portable deterministic reproduction of the recorded B1000 episode.',
                 decisions=ctl.explain_decisions,events=ctl.explain_events,progress=ctl.explain_progress,
                 source_net_sha256=new['net_sha256'],source_controller_sha256=new['frozen_controller_sha256'],
                 legacy_allow_counter_note='Legacy estimate counter includes signalized and unsignalized edges; priority admissions are reported separately.')
        (folder/'control_explanations.json').write_text(json.dumps(log,indent=2))
        captured=json.loads((HERE/'reference/B1000_control_explanations.json').read_text())
        canonical=lambda entries:sorted(entries,key=lambda x:(x['t'],x['ambulance'],x.get('junction',''),x.get('approach','')))
        report['decision_records_equal']=canonical(log['decisions'])==canonical(captured['decisions'])
        report['request_event_records_equal']=canonical(log['events'])==canonical(captured['events'])
    report['passed']=all(report['fields'].values()) and report['all_arrays_equal'] and report['ordinary_event_records_equal'] and report.get('decision_records_equal',True) and report.get('request_event_records_equal',True)
    (folder/'verification.json').write_text(json.dumps(report,indent=2))
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=['all','P0','B1000'],default='all')
    parser.add_argument('--output',type=Path,default=HERE/'reruns')
    parser.add_argument('--reference-dir',type=Path,default=HERE.parent/'data/replays')
    parser.add_argument('--smoke',action='store_true')
    args=parser.parse_args();args.output=args.output.resolve()
    args.output.mkdir(parents=True,exist_ok=True)
    os.environ['PUNJAB_OUTPUT_DIR']=str(args.output)
    import run_punjab as rp
    env=environment()
    if not env['exact_pinned_versions']:
        print('Dependency versions differ from the recorded environment; exact equality may fail.',file=sys.stderr)
    assert sha(HERE/'inputs/mohali_urban.net.xml')==EXPECTED_NET,'Frozen network has changed'
    assert sha(HERE/'inputs/demand.rou.xml')==EXPECTED_DEMAND,'Frozen demand has changed'
    assert sha(HERE/'upstream/sumo_study.py')=='471a22911a2de9773fcd839872b3ba1ec5e00412c0ecc79142503e72f41cecf2','Frozen upstream controller has changed'
    if args.smoke:reports=[smoke(rp,args.output/'smoke')]
    else:reports=[reproduce(rp,case,args.output,args.reference_dir.resolve()) for case in (['P0','B1000'] if args.case=='all' else [args.case])]
    summary=dict(passed=all(r['passed'] for r in reports),reports=reports)
    (args.output/'verification_summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps({'passed':summary['passed'],'checks':[r.get('case',r.get('test')) for r in reports]},indent=2))
    raise SystemExit(0 if summary['passed'] else 2)

if __name__=='__main__':main()
