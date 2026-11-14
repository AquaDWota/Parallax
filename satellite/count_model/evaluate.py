"""Score the Sentinel-2 -> Vexcel lot-fill model honestly.

Target: lot fill = Vexcel cars / estimated stalls. Two scores, both cross-validated by building
(a lot is never in train and test at once):
  1. across buildings - "which lots are fuller". Easy to fake: a model can learn lot size, roof edges
     and neighbourhood without seeing a single car. Reported only to show the trap.
  2. within buildings - "did THIS lot get fuller or emptier between flights". Features and target are
     demeaned per lot first, so lot size, surface colour and location cancel out. This is what Parallax
     needs (the same building over time), and the go/no-go number.
Placebo: shuffle the target within each lot - the within score must collapse to ~0.

Run: python evaluate.py   (reads results/features.csv)
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
df = pd.read_csv(HERE / "results" / "features.csv")
df = df[df.stall_capacity_est.notna() & (df.stall_capacity_est > 0)].copy()
df["fill"] = df.cars / df.stall_capacity_est
FEATS = [c for c in df.columns if c.startswith("m_")] + ["vis_std", "ndvi"]
df["vis"] = df[["m_B02", "m_B03", "m_B04"]].mean(axis=1)

# keep lots with at least 3 flights, so "within building" has something to work with
n_fl = df.groupby("building_id").capture_id.transform("nunique")
df = df[n_fl >= 3].reset_index(drop=True)
g = df.building_id
print(f"{len(df)} (lot, flight) pairs, {g.nunique()} lots, "
      f"{df.capture_id.nunique()} flights, median {df.n_scenes.median():.0f} clear Sentinel-2 scenes per pair")
print(f"lot fill: mean {df.fill.mean():.2f}, within-lot sd {df.groupby('building_id').fill.transform(lambda s: s - s.mean()).std():.2f}\n")

cv = GroupKFold(n_splits=5)


def r2(y, p):
    return 1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum()


def score(X, y, model):
    p = cross_val_predict(model, X, y, groups=g, cv=cv)
    return r2(y, p), np.corrcoef(y, p)[0, 1]


ridge = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-3, 3, 13)))
gbr = GradientBoostingRegressor(n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=0)

X, y = df[FEATS].to_numpy(), df.fill.to_numpy()
Xw = (df[FEATS] - df.groupby("building_id")[FEATS].transform("mean")).to_numpy()
yw = (df.fill - df.groupby("building_id").fill.transform("mean")).to_numpy()
rng = np.random.default_rng(0)
yp = df.groupby("building_id").fill.transform(lambda s: rng.permutation(s.to_numpy())).to_numpy()
ypw = yp - df.assign(f=yp).groupby("building_id").f.transform("mean").to_numpy()

print("                                   R2      corr")
for name, m in [("ridge", ridge), ("boosted trees", gbr)]:
    a = score(X, y, m)
    b = score(Xw, yw, m)
    c = score(Xw, ypw, m)
    print(f"{name:14s} across buildings    {a[0]:+.3f}   {a[1]:+.3f}   <- the shortcut trap")
    print(f"{name:14s} WITHIN buildings    {b[0]:+.3f}   {b[1]:+.3f}   <- go/no-go")
    print(f"{name:14s} within, placebo     {c[0]:+.3f}   {c[1]:+.3f}   <- should be ~0")
r = np.corrcoef((df.vis - df.groupby("building_id").vis.transform("mean")), yw)[0, 1]
print(f"\nsimplest check - within-lot correlation of brightness with fill: {r:+.3f} (cars darken a concrete lot -> expect negative)")
for area, d in df.groupby("area"):
    rr = np.corrcoef(d.vis - d.groupby("building_id").vis.transform("mean"),
                     d.fill - d.groupby("building_id").fill.transform("mean"))[0, 1]
    print(f"  {area}: {rr:+.3f}  ({len(d)} pairs)")
