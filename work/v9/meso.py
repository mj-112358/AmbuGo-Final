"""Conservative mesoscopic and analytic numerical references for AmbuGo.

The model uses per-lane FIFO point queues, free-flow travel clocks, physical
and PCU storage, old-state receiving reservations and fractional service
credits. These mechanisms support conservation and queue-accounting checks."""
from __future__ import annotations
import csv
import hashlib
import heapq
import json
import math
import random
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

CLASS = {
    "car": (.53, 1.0, 6.5), "motorcycle": (.30, .5, 3.1),
    "autorickshaw": (.10, 1., 4.3), "bus": (.04, 3., 14.),
    "goods": (.03, 2.5, 9.5),
}

def stream(seed, key):
    digest=hashlib.sha256(f"AmbuGo-independent-meso:{seed}:{key}".encode()).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))

@dataclass
class Packet:
    ident: str
    release: float
    route: tuple
    pcu: float = 1.
    footprint: float = 6.5
    ordinary: bool = True
    route_pos: int = 0
    ready: float = 0.
    entered: float = 0.
    completion: float | None = None

@dataclass
class Lane:
    storage_pcu: float
    storage_m: float
    packets: deque = field(default_factory=deque)
    credit: float = 0.
    used_pcu: float = 0.
    used_m: float = 0.
    def fits(self, packet):
        return (self.used_pcu+packet.pcu<=self.storage_pcu+1e-9 and
                self.used_m+packet.footprint<=self.storage_m+1e-9)
    def append(self, p):
        assert self.fits(p)
        self.packets.append(p);self.used_pcu+=p.pcu;self.used_m+=p.footprint
    def pop(self):
        p=self.packets.popleft();self.used_pcu-=p.pcu;self.used_m-=p.footprint
        return p

@dataclass
class Link:
    ident: str
    source: str
    target: str
    length: float
    speed: float
    capacity_per_lane: float
    lanes: list
    @property
    def travel(self): return self.length/self.speed

class CyclicSignal:
    """Exclusive approach greens with yellow, all-red and pedestrian reservations.
    
    The pedestrian stage reserves signal occupancy for its configured duration.
    This reference represents pedestrians through that fixed reservation."""
    def __init__(self, arms, greens, offset=0, min_green=8., amber=3., all_red=2., ped=25.):
        self.arms=tuple(arms); self.greens=tuple(greens); self.min_green=min_green
        self.amber=amber;self.all_red=all_red;self.ped=ped
        self.stages=[]
        for a,g in zip(arms,greens):
            self.stages += [(a,"green",max(min_green,g)),(a,"amber",amber),(a,"allred",all_red)]
        self.stages.append((None,"pedestrian",ped))
        self.cycle=sum(x[2] for x in self.stages)
        off=offset%self.cycle; self.stage=0
        while off>=self.stages[self.stage][2]:off-=self.stages[self.stage][2];self.stage+=1
        self.elapsed=off;self.forced=None;self.next_forced=None
    def active(self):return self.stages[self.stage][0] if self.stages[self.stage][1]=="green" else None
    def service_active(self):return self.active() if self.elapsed>=2. else None
    def tick(self,dt):
        self.elapsed+=dt
        if self.elapsed+1e-9 < self.stages[self.stage][2]:return
        self.elapsed=0.
        if self.stages[self.stage][1]=="allred" and self.next_forced is not None:
            self.stage=next(i for i,x in enumerate(self.stages) if x[0]==self.next_forced and x[1]=="green")
            self.next_forced=None
        else:self.stage=(self.stage+1)%len(self.stages)
    def request(self,arm):
        if arm not in self.arms:return
        a,kind,_=self.stages[self.stage]
        if kind=="green" and a==arm:return
        # Request can shorten a green only after its minimum. Clearance and the
        # pedestrian occupancy block are never shortened or interrupted.
        self.next_forced=arm
        if kind=="green" and self.elapsed>=self.min_green:self.stage+=1;self.elapsed=0.


def load_links(network_dir):
    rows=list(csv.DictReader((Path(network_dir)/"edges.csv").open()))
    links={}
    for e in rows:
        count=int(e["lanes"]);L=float(e["length_m"])-5.
        # Both physical packing and aggregate PCU jam storage must hold.
        lanes=[Lane(L*.16,L) for _ in range(count)]
        links[e["edge_id"]]=Link(e["edge_id"],e["from_node"],e["to_node"],
              float(e["length_m"]),float(e["speed_limit_mps"]),
              float(e["capacity_veh_per_s_per_lane"]),lanes)
    return links

def k_routes(links,origin,destination,k=4,stretch=1.25):
    outgoing={}
    for e in links.values():outgoing.setdefault(e.source,[]).append(e)
    heap=[(0.,origin,(),(origin,))];found=[];best=None
    while heap:
        c,n,path,visited=heapq.heappop(heap)
        if best is not None and c>best*stretch+1e-9:break
        if n==destination:
            if best is None:best=c
            found.append((path,c))
            if len(found)>=k:break
            continue
        for e in sorted(outgoing.get(n,[]),key=lambda e:e.ident):
            if e.target in visited:continue
            heapq.heappush(heap,(c+e.travel,e.target,path+(e.ident,),visited+(e.target,)))
    return found

class Simulator:
    def __init__(self, links, signals, packets, dt=.25):
        assert dt>0
        assert max(l.capacity_per_lane*dt for l in links.values())<=.5
        self.links=links;self.signals=signals;self.dt=dt;self.time=0.
        self.pending=deque(sorted(packets,key=lambda p:(p.release,p.ident)))
        self.source={}; self.all_packets=list(packets); self.completed=[]
        self.generated=0;self.external=0;self.integral_ordinary=0.;self.integral_total=0.
        self.audit_ticks=0;self.trace=[];self.crossed_red=0;self.storage_fail=0
    def _receiving(self,e,p,reservations):
        for i,l in sorted(enumerate(e.lanes),key=lambda x:(len(x[1].packets),x[0])):
            rp,rm=reservations.get((e.ident,i),(0.,0.))
            if l.used_pcu+rp+p.pcu<=l.storage_pcu+1e-9 and l.used_m+rm+p.footprint<=l.storage_m+1e-9:
                reservations[e.ident,i]=(rp+p.pcu,rm+p.footprint);return i
        return None
    def step(self, policy="nominal"):
        t=self.time;dt=self.dt
        # Area uses left-limit population over the tick after these admissions;
        # release times are rounded upward to this public simulation grid.
        while self.pending and self.pending[0].release<=t+1e-9:
            p=self.pending.popleft();self.source.setdefault(p.route[0],deque()).append(p);self.generated+=1;self.external+=1
        if policy=="preempt":
            for e in self.links.values():
                for l in e.lanes:
                    for p in l.packets:
                        if not p.ordinary and p.ready-t<=30 and e.target in self.signals:self.signals[e.target].request(e.ident)
        reservations={};moves=[]
        for e in sorted(self.links.values(),key=lambda x:x.ident):
            allowed=e.target not in self.signals or self.signals[e.target].service_active()==e.ident
            for i,l in enumerate(e.lanes):
                if not l.packets or not allowed or l.packets[0].ready>t+1e-9:
                    l.credit=0.;continue
                p=l.packets[0]
                l.credit=l.credit+e.capacity_per_lane*dt
                if l.credit+1e-9<p.pcu:continue
                if p.route_pos+1>=len(p.route):moves.append((e.ident,i,None,None,p));continue
                nxt=self.links[p.route[p.route_pos+1]];j=self._receiving(nxt,p,reservations)
                if j is not None:moves.append((e.ident,i,nxt.ident,j,p))
                else:l.credit=min(l.credit,p.pcu)
                # Denied service credit stays at head packet PCU; it cannot grow.
        # Reserve source admissions against old-state receiving storage as well.
        admissions=[]
        for eid,q in sorted(self.source.items()):
            while q:
                p=q[0];i=self._receiving(self.links[eid],p,reservations)
                if i is None:break
                admissions.append((eid,i,q.popleft()));self.external-=1
        for eid,i,nid,j,p in moves:
            l=self.links[eid].lanes[i];assert l.pop() is p;l.credit=max(0.,l.credit-p.pcu)
            if nid is None:p.completion=t;self.completed.append(p)
            else:
                p.route_pos+=1;p.entered=t;p.ready=math.ceil((t+self.links[nid].travel)/dt-1e-10)*dt
        for eid,i,nid,j,p in moves:
            if nid is not None:self.links[nid].lanes[j].append(p)
        for eid,i,p in admissions:
            p.entered=t;p.ready=math.ceil((t+self.links[eid].travel)/dt-1e-10)*dt;self.links[eid].lanes[i].append(p)
        inside=[p for e in self.links.values() for l in e.lanes for p in l.packets]
        external=[p for q in self.source.values() for p in q]
        self.integral_ordinary+=dt*sum(p.ordinary for p in inside+external)
        self.integral_total+=dt*(len(inside)+len(external))
        assert self.generated==len(self.completed)+len(inside)+len(external)
        assert len({p.ident for p in inside+external+self.completed})==self.generated
        for e in self.links.values():
            for l in e.lanes:
                assert abs(l.used_pcu-sum(p.pcu for p in l.packets))<1e-7
                assert abs(l.used_m-sum(p.footprint for p in l.packets))<1e-7
                assert l.used_pcu<=l.storage_pcu+1e-7 and l.used_m<=l.storage_m+1e-7
                assert l.used_pcu>=-1e-7 and l.used_m>=-1e-7
        for sig in self.signals.values():sig.tick(dt)
        self.audit_ticks+=1;self.time+=dt
    def run(self,horizon,policy="nominal"):
        steps=round(horizon/self.dt);assert abs(steps*self.dt-horizon)<1e-8
        for _ in range(steps):self.step(policy)
        times=[p.completion-p.release for p in self.completed if not p.ordinary]
        # Census identity under the same grid-rounded desired release times.
        residence=sum(max(0.,min(self.time,p.completion if p.completion is not None else self.time)-p.release)
                      for p in self.all_packets if p.release<self.time)
        assert abs(self.integral_total-residence)<1e-6
        return dict(ordinary_residence_s=self.integral_ordinary,total_residence_s=self.integral_total,
                    generated=self.generated,completed=len(self.completed),external=self.external,
                    ambulance_travel_s=times,audited_ticks=self.audit_ticks,area_identity_error=self.integral_total-residence)


def simulate_network(network_dir, seed=0,demand_scale=1.,horizon_s=2400.,missions_per_hour=2.,policy="nominal",dt=.25):
    """Run a synthetic network demonstrator with a demand-rate multiplier.
    
    Eight origins each have a 0.025 veh/s base rate times demand_scale, modified
    by a stationary common lognormal AR1 shock. Destination probabilities use
    inverse-free-flow gravity weights with a hospital multiplier of 1.8.
    The demand_scale parameter specifies the arrival-rate multiplier."""
    links=load_links(network_dir);bounds=sorted({l.source for l in links.values() if l.source.startswith("B")})
    catalog={};destw={}
    for o in bounds:
        destw[o]=[]
        for d in bounds:
            if d==o:continue
            rr=k_routes(links,o,d);catalog[o,d]=rr
            if rr:destw[o].append((d,(1.8 if d=="BE1" else 1.)/rr[0][1]))
    signals={}
    for n in sorted({l.target for l in links.values() if l.target.startswith("J")}):
        arms=sorted(l.ident for l in links.values() if l.target==n)
        signals[n]=CyclicSignal(arms,[24.]*len(arms),stream(seed,"offset:"+n).random()*(29*len(arms)+25))
    shocks=[];rr=stream(seed,"demand-shock");rho=.75;sd=.18;z=rr.gauss(0,sd/(1-rho*rho)**.5)
    for minute in range(math.ceil(horizon_s/60)):
        if minute:z=rho*z+rr.gauss(0,sd)
        shocks.append(math.exp(z-.5*sd*sd/(1-rho*rho)))
    packets=[];iid=0
    classes=list(CLASS);weights=[CLASS[x][0] for x in classes]
    for o in bounds:
        ra=stream(seed,"arrivals:"+o);rd=stream(seed,"destination:"+o);rc=stream(seed,"class:"+o);rp=stream(seed,"route:"+o)
        for minute,shock in enumerate(shocks):
            lam=.025*demand_scale*shock;t=minute*60.
            if lam<=0:continue
            t+=ra.expovariate(lam)
            while t<min(horizon_s,(minute+1)*60):
                d=rd.choices([x[0] for x in destw[o]],[x[1] for x in destw[o]])[0]
                choices=catalog[o,d];route=rp.choices([x[0] for x in choices],[math.exp(-.05*(x[1]-choices[0][1])) for x in choices])[0]
                c=rc.choices(classes,weights)[0];p=CLASS[c]
                packets.append(Packet(f"v{iid}",math.ceil(t/dt)*dt,route,p[1],p[2]));iid+=1;t+=ra.expovariate(lam)
    rm=stream(seed,"missions");t=min(600.,horizon_s/3)
    while missions_per_hour>0 and t<horizon_s:
        t+=rm.expovariate(missions_per_hour/3600)
        if t>=horizon_s:break
        o=rm.choice([x for x in bounds if x!="BE1"]);route=catalog[o,"BE1"][0][0]
        packets.append(Packet(f"a{iid}",math.ceil(t/dt)*dt,route,1.,7.,False));iid+=1
    sim=Simulator(links,signals,packets,dt);result=sim.run(horizon_s,policy)
    result.update(seed=seed,demand_scale=demand_scale,policy=policy,dt=dt)
    return result


def fluid_pulse_exact(arrival_rate,capacity,blackout_s):
    """Solve an initially empty constant-arrival fluid queue after a service blackout.
    
    Arrival rate is constant with 0 < arrival_rate < capacity. Service is zero
    on [0, blackout_s) and equals capacity afterward. The baseline has constant
    capacity and a zero queue. Return recovery time, area and peak queue."""
    a,c,d=arrival_rate,capacity,blackout_s
    assert 0<a<c and d>0
    recovery=c*d/(c-a)
    area=a*c*d*d/(2*(c-a))
    return dict(X=a/c,recovery_s=recovery,area_vehicle_s=area,peak_queue=a*d)


def fluid_pulse_numerical(arrival_rate,capacity,blackout_s,dt):
    exact=fluid_pulse_exact(arrival_rate,capacity,blackout_s)
    t=0.;q=0.;area=0.;H=math.ceil((exact["recovery_s"]+2)/dt)*dt
    for _ in range(round(H/dt)):
        # Split at blackout endpoint and queue-empty event to integrate this
        # piecewise-linear ODE exactly, independently of a sampled formula.
        stop=t+dt
        boundaries=[t]+([blackout_s] if t<blackout_s<stop else [])+[stop]
        for u,v in zip(boundaries,boundaries[1:]):
            slope=arrival_rate-(0. if u<blackout_s else capacity);d=v-u
            if q>0 and slope<0 and q+slope*d<0:
                e=-q/slope;area+=q*e/2;q=0.
            else:
                nq=max(0.,q+slope*d);area+=(q+nq)*d/2;q=nq
        t=stop
    return dict(area_vehicle_s=area,final_queue=q,horizon_s=H)


def packet_pulse(arrival_rate,capacity,blackout_s,packet_mass=.1,dt=.01):
    """Deterministic fine-packet convergence check against the fluid pulse.

    Counts are fluid vehicle-equivalents of size packet_mass. Whole packets
    arrive at multiples of packet_mass/arrival_rate; the ordinary baseline has
    negligible residence in this zero-travel single-server reference.
    """
    assert dt>0 and packet_mass>0
    exact=fluid_pulse_exact(arrival_rate,capacity,blackout_s)
    H=math.ceil((exact["recovery_s"]+5)/dt)*dt
    arrival_times=[];a=packet_mass/arrival_rate
    while a<H:arrival_times.append(a);a+=packet_mass/arrival_rate
    def run(blackout):
        q=deque();n=0;credit=0.;area=0.;last_depart=None
        for k in range(round(H/dt)):
            t=k*dt
            while n<len(arrival_times) and arrival_times[n]<=t+1e-10:q.append(arrival_times[n]);n+=1
            if t>=blackout and q:
                credit=credit+capacity*dt
                if credit+1e-10>=packet_mass:q.popleft();credit=max(0.,credit-packet_mass);last_depart=t
            else:credit=0.
            area+=len(q)*packet_mass*dt
        return area,len(q),last_depart
    treated=run(blackout_s);base=run(0.)
    return dict(packet_mass=packet_mass,dt=dt,area_vehicle_s=treated[0]-base[0],
                fluid_area_vehicle_s=exact["area_vehicle_s"],error_vehicle_s=treated[0]-base[0]-exact["area_vehicle_s"],
                final_packet_count=treated[1],horizon_s=H)
