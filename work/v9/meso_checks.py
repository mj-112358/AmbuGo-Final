"""Run analytic and conservative-packet numerical verification checks.

Usage: bundled-python work/v9/meso_checks.py --out PATH
Outputs record synthetic reference cases and conservation checks."""
import argparse
import json
import math
import time
from pathlib import Path
from meso import (fluid_pulse_exact,fluid_pulse_numerical,packet_pulse,
                  simulate_network,Simulator,Link,Lane,Packet,CyclicSignal)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out');ap.add_argument('--network',default='outputs/AmbuGo_v7_Synthetic_Data');args=ap.parse_args()
    started=time.perf_counter();checks=[];fluid=[];convergence=[]
    def check(name,ok,detail):
        checks.append(dict(check=name,passed=bool(ok),detail=detail))
        if not ok:raise AssertionError((name,detail))
    for x in [.50,.70,.85,.90]:
        exact=fluid_pulse_exact(.5*x,.5,10.)
        numeric=fluid_pulse_numerical(.5*x,.5,10.,.13)
        error=numeric['area_vehicle_s']-exact['area_vehicle_s']
        fluid.append(dict(**exact,numerical_area_vehicle_s=numeric['area_vehicle_s'],error_vehicle_s=error))
        check(f'fluid_pulse_exact_X_{x}',abs(error)<1e-8,dict(error_vehicle_s=error))
        vals=[]
        for m in [.25,.10,.025,.005]:
            z=packet_pulse(.5*x,.5,10.,m,m/10.)
            convergence.append(dict(X=x,**z));vals.append(abs(z['error_vehicle_s']))
        check(f'packet_refinement_convergence_X_{x}',all(a>b for a,b in zip(vals,vals[1:])),dict(absolute_errors_vehicle_s=vals))
        check(f'fine_packet_error_under_0point5percent_X_{x}',vals[-1]/exact['area_vehicle_s']<.005,dict(relative_error=vals[-1]/exact['area_vehicle_s']))
    # The constant-arrival fluid reference has exact shape X/(1-X).
    scaled=[d['area_vehicle_s']*(1-d['X'])/d['X'] for d in fluid]
    check('fluid_shape_X_over_one_minus_X',max(scaled)-min(scaled)<1e-10,dict(scaled_areas=scaled,theoretical_value=25.))

    # A blocked receiving link has one vehicle of physical and PCU storage.
    # A second upstream head must not enter, even though it has service credit.
    a=Link('AB','A','B',1.,10.,2.,[Lane(1.,6.5)])
    b=Link('BC','B','C',1.,10.,2.,[Lane(1.,6.5)])
    p=Packet('blocked',0.,('AB','BC'));q=Packet('downstream',0.,('BC',))
    sim=Simulator({'AB':a,'BC':b},{},[p,q],.25)
    sim.step();q.ready=10.
    for _ in range(12):sim.step()
    check('receiving_reservation_blocks_spillback',len(a.lanes[0].packets)==1 and len(b.lanes[0].packets)==1,
          dict(upstream=len(a.lanes[0].packets),downstream=len(b.lanes[0].packets)))
    check('denied_credit_does_not_accumulate_unbounded',a.lanes[0].credit<=p.pcu+1e-10,
          dict(credit=a.lanes[0].credit,head_pcu=p.pcu))
    # Physical packing is independent of PCU arithmetic.
    narrow=Lane(100.,6.5);narrow.append(Packet('car',0.,('x',)))
    check('physical_storage_separate_from_pcu',not narrow.fits(Packet('motorcycle',0.,('x',),.5,3.1)),dict(pcu_remaining=narrow.storage_pcu-narrow.used_pcu,metres_remaining=narrow.storage_m-narrow.used_m))

    # Fractional credits are retained after service. A .7-PCU head under
    # 1-PCU/s at .25s steps requires .75 credit and must leave .05.
    c=Link('C','O','D',.01,10.,1.,[Lane(10.,100.)])
    p=Packet('fraction',0.,('C',),.7,3.)
    sim=Simulator({'C':c},{},[p],.25)
    for _ in range(4):sim.step()
    check('fractional_service_credit_preserved',abs(c.lanes[0].credit-.05)<1e-10,
          dict(credit=c.lanes[0].credit))

    # Clearances cannot be cut by an ambulance request; a pedestrian block is
    # also noninterruptible in this verification reference.
    sg=CyclicSignal(['A','B'],[24.,24.])
    for _ in range(8):sg.tick(1.)
    sg.request('B')
    states=[]
    for _ in range(5):states.append(sg.stages[sg.stage][1]);sg.tick(1.)
    check('preemption_retains_amber_and_all_red',states==['amber']*3+['allred']*2,dict(states=states))
    check('preemption_targets_requested_approach_after_clearance',sg.active()=='B',dict(active=sg.active()))
    pedidx=next(i for i,x in enumerate(sg.stages) if x[1]=='pedestrian');sg.stage=pedidx;sg.elapsed=0.;sg.request('A')
    check('preemption_does_not_interrupt_pedestrian_reservation',sg.stage==pedidx,dict(stage=sg.stages[sg.stage][1]))

    runs=[]
    for seed,scale,policy in [(1,1.,'nominal'),(1,1.,'preempt'),(2,4.,'nominal'),(2,4.,'preempt'),(3,12.,'nominal'),(3,12.,'preempt')]:
        runs.append(simulate_network(args.network,seed=seed,demand_scale=scale,horizon_s=1200.,missions_per_hour=12.,policy=policy))
    check('network_cohort_area_identity',all(abs(x['area_identity_error'])<1e-6 for x in runs),dict(max_absolute_error=max(abs(x['area_identity_error']) for x in runs)))
    check('stress_creates_external_queue_without_dropping_vehicles',runs[-1]['external']>0,dict(external=runs[-1]['external']))
    rerun=simulate_network(args.network,seed=1,demand_scale=1.,horizon_s=1200.,missions_per_hour=12.,policy='nominal')
    check('bit_reproducible_network_run',rerun==runs[0],dict(seed=1))
    # Common desired arrivals and mission releases make generated counts equal
    # across controls; internal paths remain fixed in this secondary reference.
    check('paired_generated_cohort_identical',all(runs[i]['generated']==runs[i+1]['generated'] for i in [0,2,4]),dict(generated_pairs=[[runs[i]['generated'],runs[i+1]['generated']] for i in [0,2,4]]))
    result=dict(scope='Independent synthetic numerical verification of queue mechanics and accounting',
        checks_passed=sum(x['passed'] for x in checks),checks=checks,fluid_pulse=fluid,packet_refinement=convergence,
        network_reference_runs=runs,audited_network_ticks=sum(x['audited_ticks'] for x in runs)+rerun['audited_ticks'],
        seconds=time.perf_counter()-started,
        formula=dict(area='lambda*c*Delta^2/(2*(c-lambda))',recovery_from_pulse_start='c*Delta/(c-lambda)',assumptions='initially empty isolated constant-arrival fluid queue; baseline constant service c; treated service zero for Delta then c; lambda<c'),
        limitations=['The analytic reference assumes constant arrivals and a single service blackout','The numerical reference uses specified synthetic signal timings','Vehicle movement uses per-lane FIFO packet queues and storage reservations','The secondary network reference uses fixed 24-second approach greens','Secondary network runs check conservation, accounting and reproducibility'])
    if args.out:Path(args.out).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
