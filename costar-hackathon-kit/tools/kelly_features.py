"""Kelly research feature preparation. Does not modify the app or source databases."""
from __future__ import annotations
import argparse, json, os, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
import duckdb

PINNED_COMMIT="600aa82143d127833bdd0cc724cfa31646febac4"

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--root",required=True);args=parser.parse_args()
    root=Path(args.root).resolve();out=root/"data/results/kelly-version";out.mkdir(parents=True,exist_ok=True)
    candidates=sorted((root/"data/results/version-comparisons").glob(f"*-{PINNED_COMMIT[:7]}/data/parallax_real.duckdb"))
    if not candidates:raise FileNotFoundError("Pinned updated database missing; run the version comparison first.")
    db=candidates[-1]
    source=root/".tools/parallax-reruns"/PINNED_COMMIT/"source/backend"
    if not source.is_dir():raise FileNotFoundError("Pinned source snapshot is missing.")
    os.environ.update(PARALLAX_DATA_MODE="real",PARALLAX_DATA_DIR=str(db.parent));sys.path.insert(0,str(source))
    from parallax.events import build_lease_events
    with duckdb.connect(str(db),read_only=True) as c:
        buildings=c.execute("SELECT * FROM buildings").df();leases=c.execute("SELECT * FROM leases").df();usage=c.execute("SELECT * FROM usage").df()
    # Forecast 12 months before expiry; usage is measured 12-30 months before expiry.
    events,exclusions=build_lease_events(buildings,leases,usage,lead_months=12,window_months=18)
    kit=root/"costar-hackathon-kit/data"
    with (kit/"commercial-property.jsonl").open(encoding="utf-8") as f:properties={"P"+str(r["id"]):r for r in map(json.loads,f)}
    with (kit/"location-occupancy.jsonl").open(encoding="utf-8") as f:raw=list(map(json.loads,f))
    raw_by_id={str(r["id"]):r for r in raw};by_building=defaultdict(list)
    for r in raw:by_building["P"+str(r["propertyId"])].append(r)
    def date(value):
        try:return pd.Timestamp(str(value)[:10]) if value else pd.NaT
        except (ValueError,TypeError):return pd.NaT
    def area(row):return sum(s.get("squareFeetOccupied") or 0 for s in (row.get("spaces") or []))
    rows=[]
    for event in events.to_dict("records"):
        bid=event["building_id"];raw_event=raw_by_id[str(event["lease_id"])];prop=properties[bid];deal=raw_event.get("leaseDeal") or {}
        asof=event["expiry_date"]-pd.DateOffset(months=12)
        built=[r.get("year") for r in prop.get("constructionEvents",[]) if r.get("eventType")==2 and isinstance(r.get("year"),int) and r["year"]<=asof.year]
        built_year=min(built) if built else None
        renovation_dates=[]
        for renovation in prop.get("renovations",[]):
            end=date(renovation.get("endDate"))
            if pd.notna(end) and end<=asof:renovation_dates.append(end)
        for renovation in prop.get("constructionEvents",[]):
            if renovation.get("eventType") not in [4,5,16,17] or not isinstance(renovation.get("year"),int):continue
            # Year-only events are not treated as complete until that year's end.
            end=pd.Timestamp(year=renovation["year"],month=12,day=31)
            if end<=asof:renovation_dates.append(end)
        latest_renovation=max(renovation_dates) if renovation_dates else pd.NaT
        start=date(deal.get("commencementDate"))
        term=(event["expiry_date"]-start).days/365.25 if pd.notna(start) and start<event["expiry_date"] else np.nan
        tenant_area=area(raw_event);building_area=event["building_sqft"]
        share=tenant_area/building_area if building_area>0 else np.nan
        share=share if 0<share<=1 else np.nan
        active_areas=defaultdict(float)
        for tenancy in by_building[bid]:
            begin,end=date(tenancy.get("fromDate")),date(tenancy.get("toDate"))
            if pd.notna(begin) and begin<=asof and (pd.isna(end) or end>=asof):
                tid=tenancy.get("tenantLocationId")
                active_areas[("known",tid) if tid is not None else ("unknown",tenancy["id"])]+=area(tenancy)
        total=sum(active_areas.values());largest=max(active_areas.values())/total if total>0 else np.nan
        end=date(raw_event.get("toDate"))
        rows.append({**event,"prediction_date":asof,"building_age_years":asof.year-built_year if built_year else np.nan,
            "years_since_renovation":(asof-latest_renovation).days/365.25 if pd.notna(latest_renovation) else np.nan,
            "lease_duration_years":term,"lease_share":share,"largest_active_tenant_share":largest,
            "usage_x_tenant_share":((event["usage"]-100)/100)*share,
            "source_tenant_id":raw_event.get("tenantLocationId"),"source_reason":raw_event.get("expirationReason"),
            "source_occupancy_end":end,"open_occupancy_assumption":pd.isna(end),
            "target_space_retained":int(event["outcome"] in ["renewed","expanded"]),
            "target_tenant_retained":int(event["outcome"] in ["renewed","expanded","downsized"])})
    frame=pd.DataFrame(rows)
    context_path=root/"data/kelly-context.json"
    context_columns=["employment_growth_yoy","net_domestic_migration_per_1000"]
    for col in context_columns:frame[col]=np.nan
    context_matches={col:0 for col in context_columns}
    if context_path.is_file():
        records=json.loads(context_path.read_text(encoding="utf-8"))
        if not isinstance(records,list):raise ValueError("kelly-context.json must be a list of dated building-context records")
        for record in records:
            if not all(k in record for k in ["building_id","reference_date","available_date","source_url"]):raise ValueError("Each context record needs building_id, reference_date, available_date and source_url")
            if date(record["available_date"])<date(record["reference_date"]):raise ValueError("Context available_date must not precede its reference_date")
        for idx,row in frame.iterrows():
            eligible=[r for r in records if r["building_id"]==row.building_id and date(r["available_date"])<=row.prediction_date and date(r["reference_date"])<=row.prediction_date]
            for col in context_columns:
                known=[r for r in eligible if r.get(col) is not None]
                if known:
                    selected=max(known,key=lambda r:(date(r["reference_date"]),date(r["available_date"])))
                    frame.loc[idx,col]=float(selected[col]);context_matches[col]+=1
    frame.to_csv(out/"kelly-feature-events.csv",index=False)
    manifest={"pinned_commit":PINNED_COMMIT,"source_database":str(db),"forecast_lead_months":12,"usage_window_months":18,"events":len(frame),"exclusions":exclusions,"context_file_present":context_path.is_file(),"context_matches":context_matches,"measurement_warning":"Existing historical car counts; not a new detector run","point_in_time_warning":"Features use dates but come from retrospective source snapshots; historical information availability is not verified"}
    (out/"feature-provenance.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(manifest,indent=2))
if __name__=="__main__":main()
