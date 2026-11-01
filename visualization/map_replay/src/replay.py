"""Read frozen simulator replays with display-position interpolation.

Signal phases, routes, speed, membership and status use the previous recorded
sample (zero-order hold). Coordinates use Web Mercator metres (EPSG:3857);
ground-distance measurements require the appropriate projection correction."""
from pathlib import Path
import json
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
SIM=ROOT/'data/replays'
R=6378137.
def llxy(lon,lat):
    lon=np.asarray(lon);lat=np.asarray(lat)
    return np.stack((R*np.radians(lon),R*np.log(np.tan(np.pi/4+np.radians(lat)/2))),axis=-1)

class Replay:
    def __init__(self,p):
        self.p=p;self.meta=json.loads((SIM/(p+'.json')).read_text());self.a={k:v for k,v in np.load(SIM/(p+'.npz')).items()}
        self.t=self.a['t'];self.flatxy=llxy(self.a['lon'],self.a['lat']);self.amxy=llxy(self.a['ambulance_lon'],self.a['ambulance_lat'])
        self.ami=[i for i,v in enumerate(self.meta['vehicles']) if v['type']=='ambulance'];self.amlookup=set(self.ami)
        dimensions={'car':(4.5,1.8),'motorcycle':(2.1,.8),'bus':(12,2.5),'goods':(8,2.3),'ambulance':(5,2)}
        self.vehicle_dimensions=np.array([dimensions[v['type']] for v in self.meta['vehicles']])
    def at(self,t):return int(np.clip(np.searchsorted(self.t,t,side='right')-1,0,len(self.t)-1))
    def positions(self,t):
        i=self.at(t);a=self.a;lo,hi=a['offsets'][i:i+2];vid=a['vehicle'][lo:hi];xy=self.flatxy[lo:hi].copy();angle=a['angle'][lo:hi];speed=a['speed'][lo:hi]
        if i+1<len(self.t):
            ll,hh=a['offsets'][i+1:i+3];vid2=a['vehicle'][ll:hh];_,j,k=np.intersect1d(vid,vid2,return_indices=True);u=np.clip((t-self.t[i])/(self.t[i+1]-self.t[i]),0,1);xy[j]=xy[j]*(1-u)+self.flatxy[ll:hh][k]*u
        return vid,xy,angle,speed
    def amb(self,t):
        i=self.at(t);xy=self.amxy[i].copy()
        if i+1<len(self.t):
            good=np.isfinite(xy[:,0])&np.isfinite(self.amxy[i+1,:,0]);u=np.clip((t-self.t[i])/(self.t[i+1]-self.t[i]),0,1);xy[good]=(1-u)*xy[good]+u*self.amxy[i+1][good]
        return xy
