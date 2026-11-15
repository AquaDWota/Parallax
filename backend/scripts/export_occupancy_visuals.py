"""Export pinned occupancy/car diagnostics for notebook plots and local app tabs."""
import argparse,json,math
from pathlib import Path
import duckdb,pandas as pd

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--root",required=True);args=parser.parse_args();root=Path(args.root).resolve()
    commit="600aa82143d127833bdd0cc724cfa31646febac4"
    report=sorted((root/"data/results/version-comparisons").glob(f"*-{commit[:7]}/updated-app-results.json"))[-1]
    db=report.parent/"data/parallax_real.duckdb"
    with duckdb.connect(str(db),read_only=True) as c:
        b=c.execute("select * from buildings").df();u=c.execute("select * from usage").df();t=c.execute("select * from tenancies").df()
    groups={bid:g for bid,g in t.groupby("building_id")};buildings=b.set_index("building_id")
    def number(x):return round(float(x),4) if pd.notna(x) and math.isfinite(float(x)) else None
    points=[]
    for r in u.itertuples():
        if pd.isna(r.cars) or r.building_id not in groups:continue
        g=groups[r.building_id];size=buildings.loc[r.building_id,"sqft"]
        active=g.loc[g.from_date.le(r.capture_date)&(g.to_date.isna()|g.to_date.ge(r.capture_date))]
        raw=100*active.sqft.sum()/size if size>0 else float("nan")
        points.append({"building_id":r.building_id,"name":buildings.loc[r.building_id,"name"],"city":r.city,"date":r.capture_date.date().isoformat(),"capture_id":r.capture_id,"cars":number(r.cars),"fill_pct":number(r.fill*100),"occupancy_raw":number(raw),"occupancy":number(min(raw,120)),"relative_activity":number(r.abs_index/100),"quality_flag":r.quality_flag,"flagged":bool(r.quality_flag!="ok" or raw>100),"active_tenancies":len(active)})
    frame=pd.DataFrame(points)
    # Define mismatch selection before inspecting images; do not use model accuracy.
    eligible=frame.loc[frame.date.ge("2023-01-01")&frame.occupancy_raw.between(80,100)&frame.relative_activity.le(.5)].copy()
    eligible=eligible.sort_values(["date","relative_activity","building_id"],ascending=[False,True,True]).drop_duplicates("building_id")
    selected=[]
    for city in ["Houston","Los Angeles"]:
        subset=eligible.loc[eligible.city.eq(city)]
        if len(subset):selected.append(subset.iloc[0].to_dict())
    for row in eligible.to_dict("records"):
        if row["building_id"] not in {r["building_id"] for r in selected}:selected.append(row)
        if len(selected)>=4:break
    for row in selected:row["image_url"]="/occupancy-case-images/"+row["building_id"]+".jpg"
    summary=frame.groupby("city").agg(observations=("cars","size"),buildings=("building_id","nunique"),zero_counts=("cars",lambda s:int(s.eq(0).sum()))).reset_index().to_dict("records")
    result={"commit":commit,"database":str(db.relative_to(root)),"scope":"All non-null car-count observations at imaged properties with tenancy history; broader than the fitted-model sample","summary":summary,"points":points,"mismatches":selected,"mismatch_rule":"At least 80% and at most 100% raw recorded occupancy; relative parking at most 0.5x; captures from 2023 onward; latest per building; include both cities when available, then latest remaining; up to four cases","image_note":"Actual crop of the existing lot geometry; no new detector run, no independently verified stall/car counts"}
    out=root/"data/results/lease-validation/occupancy-exploration";out.mkdir(parents=True,exist_ok=True)
    (out/"occupancy-visuals.json").write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
    frame.to_csv(out/"all-car-occupancy-observations.csv",index=False)
    for frontend in [root/"frontend",root/".tools/parallax-reruns"/commit/"source/frontend"]:
        public=frontend/"public";public.mkdir(exist_ok=True)
        (public/"occupancy-visuals.json").write_text(json.dumps(result,allow_nan=False),encoding="utf-8")
    print(json.dumps({"observations":len(points),"buildings":frame.building_id.nunique(),"summary":summary,"mismatches":[r["building_id"] for r in selected]}))
if __name__=="__main__":main()
