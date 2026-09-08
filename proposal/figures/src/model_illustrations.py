"""Generate deterministic synthetic coordinates for the proposal's PGFPlots figure.
These are teaching illustrations, not EventLens measurements or model results.
Run from any directory with Python and NumPy, then rebuild proposal.tex.
"""
from pathlib import Path
import math
import numpy as np
out = Path(__file__).resolve().parents[1]
rng = np.random.default_rng(42)
x = np.linspace(.2, 2.8, 24)
y = np.maximum(.05, .25 + .7*x + rng.normal(0,.24,len(x)))
b = np.linalg.lstsq(np.column_stack([np.ones(len(x)),x]),y,rcond=None)[0]
cloud = np.vstack([rng.normal([.22,-.6],[.07,.12],(16,2)), rng.normal([.8,.55],[.08,.12],(16,2)),rng.normal([.48,.08],[.07,.12],(16,2))])
z = (cloud-cloud.mean(axis=0))/cloud.std(axis=0)
c = z[[0,16,32]].copy()
for _ in range(25):
 labels=((z[:,None]-c[None,:])**2).sum(axis=2).argmin(axis=1)
 c=np.array([z[labels==j].mean(axis=0) for j in range(3)])
centres=c*cloud.std(axis=0)+cloud.mean(axis=0)
def coords(a): return ' '.join(f'({v[0]:.4f},{v[1]:.4f})' for v in a)
# Mixture loss distribution in percentage points: illustrative p=0.6.
p=.6
cdf=lambda t: p*.5*(1+math.erf((t-2)/(1.4*math.sqrt(2))))+(1-p)*.5*(1+math.erf((t+.5)/(.8*math.sqrt(2))))
lo,hi=-8.,12.
for _ in range(80):
 mid=(lo+hi)/2
 if cdf(mid)<.95: lo=mid
 else: hi=mid
var=(lo+hi)/2
phi=lambda z: math.exp(-z*z/2)/math.sqrt(2*math.pi)
tail=lambda mu,s: mu*.5*math.erfc((var-mu)/(s*math.sqrt(2)))+s*phi((var-mu)/s)
es=(p*tail(2,1.4)+(1-p)*tail(-.5,.8))/.05
lines=[r'% Generated synthetic values. Seed 42. No empirical research claims.',
 r'\def\regpoints{'+coords(np.c_[x,y])+'}',
 r'\def\regintercept{'+f'{b[0]:.5f}'+'}',r'\def\regslope{'+f'{b[1]:.5f}'+'}',
 r'\def\toyvar{'+f'{var:.5f}'+'}',r'\def\toyes{'+f'{es:.5f}'+'}']
for j in range(3): lines.append(r'\expandafter\def\csname cluster'+str(j)+r'\endcsname{'+coords(cloud[labels==j])+'}')
lines.append(r'\def\clustercentres{'+coords(centres)+'}')
(out/'model-coordinates.tex').write_text('\n'.join(lines)+'\n')
print('Generated synthetic regression, 3-cluster k-means and mixture-tail illustration.')
