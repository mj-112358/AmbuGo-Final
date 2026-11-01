#!/usr/bin/env python3
"""Run a synthetic traffic/control demonstration on mapped OSM geometry.

Import frozen v9 classes and adapt routing to SUMO's allowed-turn edge graph
and a mapped hospital road approach. Traffic demand and signal settings are
scenario inputs."""
from pathlib import Path
import sys,json,math,random,time,hashlib,argparse,subprocess,os,xml.etree.ElementTree as ET
from collections import defaultdict
ROOT=Path(__file__).resolve().parent
V9=ROOT/'upstream';HERE=Path(os.environ.get('PUNJAB_OUTPUT_DIR',ROOT/'reruns'));HERE.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(V9))
import numpy as np
import networkx as nx
import sumolib
import sumo_study as ss
traci=ss.traci
if ss.BACKEND != 'libsumo':
    raise RuntimeError('This reproduction requires libsumo, as used for the recorded episode.')
# libsumo consumes the SUMO argument vector in-process; no bundled binary path is needed.
ss.SUMO='sumo'

class RealMapController(ss.Controller):
    def __init__(self,*args,turngraph,destination,**kwargs):
        super().__init__(*args,**kwargs);self.turngraph=turngraph;self.destination=destination
        self.fullplans=[]
    def candidates(self,e):
        if e not in self.pathcache:
            out=[];best=None
            try:
                for p in nx.shortest_simple_paths(self.turngraph,e,self.destination,weight='weight'):
                    cost=sum(self.m['edges'][x]['ff'] for x in p)
                    if best is None:best=cost
                    if cost>best*1.5:break
                    out.append(p)
                    if len(out)>=4:break
            except (nx.NetworkXNoPath,nx.NodeNotFound):pass
            self.pathcache[e]=out or [[e]]
        return self.pathcache[e]
    def plan(self,aid,e,remaining,t,policy=None):
        before=tuple(traci.vehicle.getRoute(aid));super().plan(aid,e,remaining,t,policy)
        after=tuple(traci.vehicle.getRoute(aid))
        self.fullplans.append(dict(t=t,ambulance=aid,edge=e,mode=policy or self.policy,route=list(after),changed=before!=after,action=list(self.amaction[aid])))

def model(netfile):
    n=sumolib.net.readNet(str(netfile),withInternal=False)
    edges={e.getID():e for e in n.getEdges() if e.allows('passenger')}
    g=nx.DiGraph();g.add_nodes_from(edges)
    for eid,e in edges.items():
        for to,cc in e.getOutgoing().items():
            if to.getID() not in edges:continue
            if not any(c.getFromLane().allows('passenger') and c.getToLane().allows('passenger') for c in cc):continue
            if to.getToNode()==e.getFromNode():continue
            g.add_edge(eid,to.getID(),weight=to.getLength()/to.getSpeed())
    xml=ET.parse(netfile).getroot();linkarms=defaultdict(dict);e_to_tls={}
    for co in xml.findall('connection'):
        if 'tl' in co.attrib and co.get('from') in edges:
            j=co.get('tl');eid=co.get('from');linkarms[j][int(co.get('linkIndex'))]=eid;e_to_tls[eid]=j
    # All links belonging to a signal are included, including non-passenger links.
    for co in xml.findall('connection'):
        if co.get('tl') in linkarms:linkarms[co.get('tl')][int(co.get('linkIndex'))]=co.get('from')
    nodes={x.getID():dict(id=x.getID(),x=x.getCoord()[0],y=x.getCoord()[1]) for x in n.getNodes()}
    ed={eid:dict(id=eid,fr=e.getFromNode().getID(),to=e_to_tls.get(eid,e.getToNode().getID()),L=e.getLength(),v=e.getSpeed(),lanes=e.getLaneNumber(),ff=e.getLength()/e.getSpeed(),s=.5*e.getLaneNumber(),K=max(2,e.getLength()*e.getLaneNumber()/7.5)) for eid,e in edges.items()}
    inc=defaultdict(list)
    for eid,ee in ed.items():inc[ee['to']].append(eid)
    for j,la in linkarms.items():
        # Original signal controller needs a positive-green stage per incoming arm.
        for eid in set(la.values()):
            if eid not in ed:
                e=n.getEdge(eid);ed[eid]=dict(id=eid,fr=e.getFromNode().getID(),to=j,L=e.getLength(),v=e.getSpeed(),lanes=e.getLaneNumber(),ff=e.getLength()/e.getSpeed(),s=.5*e.getLaneNumber(),K=max(2,e.getLength()*e.getLaneNumber()/7.5));inc[j].append(eid)
    m=dict(nodes=nodes,edges=ed,juncs=sorted(linkarms),inc=dict(inc),meanpcu=1.1)
    return n,g,m,linkarms

def route(n,g,start,end):
    try:return nx.shortest_path(g,start,end,weight='weight')
    except:return None

def choose_routes(n,g,m,config):
    dest=config['destination_edge'];origin=config['ambulance_origin_edge'];ar=route(n,g,origin,dest)
    if not ar:raise RuntimeError('No ambulance route')
    od=[]
    # Input boundary points are selected from actual road geometry by the map adapter.
    sources=config.get('origin_edges',[]);sinks=config.get('destination_edges',[])
    if not sources or not sinks:
        coords=np.array([n.getEdge(e).getShape()[0] for e in g.nodes]);lo=coords.min(axis=0);hi=coords.max(axis=0)
        for eid in g.nodes:
            e=n.getEdge(eid);x,y=e.getShape()[0];d=min(x-lo[0],hi[0]-x,y-lo[1],hi[1]-y)
            if d<.14*min(hi-lo) and e.getLength()>30 and e.getSpeed()>=8:sources.append(eid)
        sinks=list(sources)
    rng=random.Random(14009);rng.shuffle(sources);rng.shuffle(sinks)
    # Fixed route-pool selection is independent of the treatment policy.
    for start in sources[:32]:
        for end in sinks[:32]:
            if start==end:continue
            p=route(n,g,start,end)
            if not p:continue
            distance=sum(m['edges'][e]['L'] for e in p)
            sig=sum(m['edges'][e]['to'] in m['juncs'] for e in p)
            if 1200<distance<7000 and sig>=1:od.append(p)
    rng.shuffle(od);od=od[:48]
    if not od:raise RuntimeError('No ordinary traffic routes')
    return ar,od

def make_inputs(netfile,config):
    n,g,m,links=model(netfile);ar,od=choose_routes(n,g,m,config)
    H=config.get('horizon',2400);flow=config.get('arrival_rate',1.6);rng=random.Random(config.get('seed',19))
    ordinary=[];t=0
    while True:
        if flow<=0:break
        t+=rng.expovariate(flow)
        if t>=H:break
        cl=rng.choices(['car','motorcycle','bus','goods'],[.75,.15,.05,.05])[0]
        ordinary.append(dict(id=f'v{len(ordinary):06d}',depart=math.ceil(t*2)/2,type=cl,route=rng.choice(od)))
    missions=[dict(id=f'a{k:03d}',depart=t,type='ambulance',route=ar,origin=ar[0],destination=ar[-1]) for k,t in enumerate(config.get('dispatches',[600,1000,1400]))]
    exp=defaultdict(float)
    for p in od:
        for e in p:exp[e]+=flow/len(od)
    plans={}
    for j in m['juncs']:
        arms=sorted(set(links[j].values()));weights=[exp.get(e,.01) for e in arms];greens=ss.green_split(max(24.,20*len(arms)),weights,8);C=sum(greens)+5*len(arms)+25
        plans[j]=dict(arms=arms,greens=[round(x) for x in greens],cycle=C,X={e:exp.get(e,0)*m['meanpcu']/(m['edges'][e]['s']*gr/C) for e,gr in zip(arms,greens)})
    design=dict(plans=plans,expected_veh_per_s=dict(exp))
    xml=ET.Element('routes')
    for typ,L,width,gap,tau,accel,decel in [('car',4.5,1.8,2,1.2,2.4,4.5),('motorcycle',2.1,.8,1,.9,2.8,5),('bus',12,2.5,2.5,1.8,1.2,4),('goods',8,2.3,2.5,1.6,1.6,4),('ambulance',5,2,2,1.3,2,4.5)]:
        ET.SubElement(xml,'vType',id=typ,vClass='passenger',length=str(L),width=str(width),minGap=str(gap),tau=str(tau),accel=str(accel),decel=str(decel),sigma='0',speedFactor='1',speedDev='0')
    for v in sorted(ordinary+missions,key=lambda v:(v['depart'],v['id'])):
        e=ET.SubElement(xml,'vehicle',id=v['id'],type=v['type'],depart=str(v['depart']),departLane='best',departSpeed='max');ET.SubElement(e,'route',edges=' '.join(v['route']))
    routefile=HERE/'demand.rou.xml';ET.ElementTree(xml).write(routefile,encoding='utf-8',xml_declaration=True)
    schedule=dict(ordinary=ordinary,ambulances=missions,design=design,seed=config.get('seed',19),configuration=config,geometry=str(netfile),provenance='Real OSM road geometry; hypothetical uncalibrated traffic, signal timing, and ambulance missions. Frozen v9 controller classes reused with allowed-turn route adaptation.',route_file=str(routefile),schedule_sha256=hashlib.sha256(routefile.read_bytes()).hexdigest())
    (HERE/'scenario.json').write_text(json.dumps(schedule,indent=2));return n,g,m,links,schedule

def run(policy,netfile,config):
    n,g,m,links,s=make_inputs(netfile,config);H=config.get('horizon',2400)
    c=dict(ss.DEFAULTS);c.update(step=.5,sensor_period=5,sensor_delay=2,sensor_noise=True,harm_budget=10000.,epsilon=0.,action_mode='strong',progress_guard_s=20.,warmup=300,horizon=H)
    sigs={j:ss.Signal(j,s['design']['plans'][j],[links[j][k] for k in range(max(links[j])+1)],ss.stable_rng(0,'offset',j).randrange(len(s['design']['plans'][j]['arms']))) for j in m['juncs']}
    control=RealMapController(m,s,sigs,policy,c,turngraph=g,destination=config['destination_edge'])
    cmd=[ss.SUMO,'-n',str(netfile),'-r',s['route_file'],'--step-length','.5','--time-to-teleport','-1','--collision.action','warn','--no-step-log','true','--duration-log.disable','true','--no-warnings','true','--seed',str(s['seed']),'--error-log',str(HERE/(policy+'.log'))]
    traci.start(cmd);started=time.time();eids=sorted(m['edges']);jids=sorted(sigs);edgeix={e:i for i,e in enumerate(eids)};vs=s['ordinary']+s['ambulances'];vids=[v['id'] for v in vs];vix={v:i for i,v in enumerate(vids)}
    geonet=dict(provenance='OSM road geometry compiled by SUMO, with signal points at modeled controlled-junction locations.',edges=[],signals=[])
    for eid in eids:
        ee=n.getEdge(eid);geonet['edges'].append(dict(id=eid,xy=[list(p) for p in ee.getShape()],lonlat=[list(traci.simulation.convertGeo(*p)) for p in ee.getShape()],lanes=ee.getLaneNumber(),speed_mps=ee.getSpeed(),length_m=ee.getLength()))
    for jid in jids:
        pts=[n.getEdge(e).getShape()[-1] for e in set(links[jid].values())];x,y=np.mean(pts,axis=0);lon,lat=traci.simulation.convertGeo(float(x),float(y));geonet['signals'].append(dict(id=jid,x=float(x),y=float(y),lon=lon,lat=lat,incoming=sorted(set(links[jid].values()))))
    (HERE/'network_geo.json').write_text(json.dumps(geonet,separators=(',',':')))
    flat={k:[] for k in ['vehicle','x','y','lon','lat','angle','speed','edge']};offs=[0];times=[];counts=[];halts=[];smode=[];sedge=[];sreq=[];ax=[];ay=[];aroute=[];fallback=[];routes=[];routeix={};events=[];arrivals={};insertion={};active=set();collisions=teleports=0;amap={v['id']:v for v in s['ambulances']};ordinary_exit={};ordinary_in={};N=[];elapsed=0
    try:
        for half in range(int(H*2)):
            t=half*.5
            if half%2==0:
                cc={e:traci.edge.getLastStepVehicleNumber(e) for e in eids};control.observe(int(t),cc)
                req=control.requests_at(int(t),[amap[a] for a in active])
                for j,si in sigs.items():si.update(int(t),req.get(j),control.obs,base='fixed')
            traci.simulationStep();now=traci.simulation.getTime()
            for v in traci.simulation.getDepartedIDList():
                if v in amap:active.add(v);insertion[v]=now
                else:ordinary_in[v]=now
            for v in traci.simulation.getArrivedIDList():
                if v in amap:active.discard(v);arrivals[v]=now
                else:ordinary_exit[v]=now
            collisions+=traci.simulation.getCollidingVehiclesNumber();teleports+=traci.simulation.getStartingTeleportNumber()
            N.append(sum(v['depart']<=now for v in s['ordinary'])-len(ordinary_exit))
            # Full .5 second trajectory capture after warmup; physical signal commands retained.
            if now<300:continue
            alive=traci.vehicle.getIDList();times.append(now)
            for v in alive:
                x,y=traci.vehicle.getPosition(v);lon,lat=traci.simulation.convertGeo(x,y)
                flat['vehicle'].append(vix[v]);flat['x'].append(x);flat['y'].append(y);flat['lon'].append(lon);flat['lat'].append(lat);flat['angle'].append(traci.vehicle.getAngle(v));flat['speed'].append(traci.vehicle.getSpeed(v));flat['edge'].append(edgeix.get(traci.vehicle.getRoadID(v),-1))
            offs.append(len(flat['vehicle']));ec=np.array([traci.edge.getLastStepVehicleNumber(e) for e in eids]);hc=np.array([traci.edge.getLastStepHaltingNumber(e) for e in eids])
            aa=[];bb=[];rr=[];ff=[]
            for v in s['ambulances']:
                aid=v['id'];ff.append(aid in control.fallback_ids)
                if aid in active:
                    x,y=traci.vehicle.getPosition(aid);lon,lat=traci.simulation.convertGeo(x,y);aa.append(lon);bb.append(lat)
                    route_now=tuple(traci.vehicle.getRoute(aid))
                    if route_now not in routeix:routeix[route_now]=len(routes);routes.append(list(route_now))
                    rr.append(routeix[route_now]);eid=traci.vehicle.getRoadID(aid)
                    if eid in edgeix:ec[edgeix[eid]]-=1
                else:aa.append(float('nan'));bb.append(float('nan'));rr.append(-1)
            counts.append(ec);halts.append(hc);ax.append(aa);ay.append(bb);aroute.append(rr);fallback.append(ff)
            smode.append([{'green':0,'amber':1,'allred':2,'ped':3}[sigs[j].mode] for j in jids]);sedge.append([edgeix.get(sigs[j].edge,-1) for j in jids]);sreq.append([edgeix.get(sigs[j].request['edge'],-1) if sigs[j].request else -1 for j in jids])
    finally:traci.close()
    arrays={k:np.array(v,dtype=np.int32 if k=='vehicle' else (np.int16 if k=='edge' else np.float64 if k in ('lon','lat') else np.float32)) for k,v in flat.items()}
    arrays.update(t=np.array(times),offsets=np.array(offs),ordinary_edge_counts=np.array(counts,dtype=np.int16),edge_halts=np.array(halts,dtype=np.int16),signal_mode=np.array(smode,dtype=np.uint8),signal_edge=np.array(sedge,dtype=np.int16),signal_request=np.array(sreq,dtype=np.int16),ambulance_lon=np.array(ax),ambulance_lat=np.array(ay),ambulance_route=np.array(aroute,dtype=np.int16),fallback=np.array(fallback,dtype=np.uint8),ordinary_population=np.array(N,dtype=np.int32))
    np.savez_compressed(HERE/(policy+'.npz'),**arrays)
    mr=[dict(id=a['id'],depart=a['depart'],insertion=insertion.get(a['id']),arrival=arrivals.get(a['id']),travel_s=arrivals.get(a['id'],H)-a['depart'],censored=a['id'] not in arrivals) for a in s['ambulances']]
    out=dict(policy=policy,seed=s['seed'],provenance=s['provenance'],configuration=c,scenario_config=config,missions=mr,vehicles=[{k:v[k] for k in ['id','type','depart']} for v in vs],edge_ids=eids,junction_ids=jids,routes=routes,ambulance_ids=[x['id'] for x in s['ambulances']],plans=control.fullplans,progress_guard_log=control.fallback_log,route_changes=control.route_changes,priority_phase_admissions=sum(x.accepted for x in sigs.values()),signal_timing_violations=sum(x.phase_violations for x in sigs.values()),collision_events=collisions,teleport_events=teleports,net_sha256=hashlib.sha256(netfile.read_bytes()).hexdigest(),adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),schedule_sha256=s['schedule_sha256'],frozen_controller_sha256=hashlib.sha256((V9/'sumo_study.py').read_bytes()).hexdigest(),runtime_s=time.time()-started,ordinary_completed=len(ordinary_exit),ordinary_scheduled=len(s['ordinary']))
    (HERE/(policy+'.json')).write_text(json.dumps(out,indent=2));(HERE/(policy+'_ordinary_events.json')).write_text(json.dumps([dict(id=v['id'],desired=v['depart'],insertion=ordinary_in.get(v['id']),arrival=ordinary_exit.get(v['id'])) for v in s['ordinary']]))
    print(json.dumps({k:v for k,v in out.items() if k not in ['vehicles','routes','edge_ids','junction_ids','plans','configuration','scenario_config']},indent=2),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('policy',choices=['P0','P2','P3']);ap.add_argument('--net',required=True);ap.add_argument('--config',required=True);a=ap.parse_args();run(a.policy,Path(a.net),json.loads(Path(a.config).read_text()))
