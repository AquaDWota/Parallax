"""Fetch public Census migration vintages and geographically match Kelly buildings."""
from __future__ import annotations
import argparse, hashlib, io, json, zipfile
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests
import pandas as pd
import shapefile
from shapely.geometry import shape,Point

# Availability is conservatively the day after the Census directory's published
# file timestamp. It is an availability proxy, not a verified first-release timestamp.
VINTAGES={2016:"2017-03-24",2017:"2018-03-23",2018:"2019-04-19",2019:"2020-03-27",2021:"2022-03-25",2022:"2023-03-31",2023:"2024-03-15",2024:"2025-03-14"}
SHAPE_URL="https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--root",required=True);args=parser.parse_args();root=Path(args.root).resolve()
    out=root/"data/results/kelly-version/migration-experiment";cache=out/"sources";cache.mkdir(parents=True,exist_ok=True)
    features=pd.read_csv(root/"data/results/kelly-version/kelly-feature-events.csv",parse_dates=["prediction_date"])
    wanted=set(features.building_id)
    with (root/"costar-hackathon-kit/data/commercial-property.jsonl").open(encoding="utf-8") as f:
        properties={"P"+str(r["id"]):r for r in map(json.loads,f) if "P"+str(r["id"]) in wanted}
    def get(url):
        path=cache/url.rsplit("/",1)[1]
        if not path.is_file():
            response=requests.get(url,timeout=120);response.raise_for_status();path.write_bytes(response.content)
        return path
    shape_path=get(SHAPE_URL)
    county_shapes=[]
    with zipfile.ZipFile(shape_path) as z:
        shp=next(n for n in z.namelist() if n.endswith(".shp"));base=shp[:-4]
        reader=shapefile.Reader(shp=io.BytesIO(z.read(shp)),shx=io.BytesIO(z.read(base+".shx")),dbf=io.BytesIO(z.read(base+".dbf")),encoding="utf-8")
        for item in reader.iterShapeRecords():
            record=item.record.as_dict()
            if record["STATEFP"] not in ["06","48"]:continue
            county_shapes.append((record,shape(item.shape.__geo_interface__)))
    crosswalk=[]
    for bid,p in properties.items():
        a=p["primaryAddress"];point=Point(a["longitude"],a["latitude"])
        matches=[r for r,geometry in county_shapes if geometry.covers(point)]
        if len(matches)!=1:raise ValueError(f"County match ambiguous/missing for {bid}: {len(matches)}")
        c=matches[0]
        crosswalk.append({"building_id":bid,"county_fips":c["GEOID"],"county_name":c["NAME"],"state_fips":c["STATEFP"],"latitude":point.y,"longitude":point.x,"boundary_source":SHAPE_URL})
    crosswalk=pd.DataFrame(crosswalk);crosswalk.to_csv(out/"building-county-crosswalk.csv",index=False)
    urls={year:f"https://www2.census.gov/programs-surveys/popest/datasets/{'2010' if year<2020 else '2020'}-{year}/counties/totals/co-est{year}-alldata.csv" for year in VINTAGES}
    with ThreadPoolExecutor(max_workers=3) as pool:paths=dict(zip(urls,pool.map(get,urls.values())))
    rows=[];manifest=[]
    needed=set(crosswalk.county_fips)
    for year,path in paths.items():
        data=pd.read_csv(path,encoding="latin-1",dtype={"STATE":str,"COUNTY":str})
        data.columns=[c.upper() for c in data.columns]
        data=data.copy()
        data["FIPS"]=data.STATE.str.zfill(2)+data.COUNTY.str.zfill(3)
        data=data.loc[data.FIPS.isin(needed)]
        rate=f"RDOMESTICMIG{year}"
        if rate not in data:raise ValueError(f"Published migration-rate column missing: {rate}")
        for _,r in data.iterrows():
            rows.append({"county_fips":r.FIPS,"county_name":r.CTYNAME,"vintage":year,"reference_date":f"{year}-07-01","available_date":VINTAGES[year],"net_domestic_migration_per_1000":float(r[rate]),"source_url":urls[year]})
        manifest.append({"vintage":year,"source_url":urls[year],"available_date_proxy":VINTAGES[year],"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    history=pd.DataFrame(rows);history.to_csv(out/"county-migration-vintages.csv",index=False)
    matched=features.merge(crosswalk,on="building_id",how="left",validate="many_to_one")
    for column in ["migration_rate","migration_reference_date","migration_available_date","migration_vintage","migration_source_url"]:matched[column]=None
    history["reference_date"]=pd.to_datetime(history.reference_date);history["available_date"]=pd.to_datetime(history.available_date)
    for index,row in matched.iterrows():
        valid=history.loc[history.county_fips.eq(row.county_fips)&history.available_date.le(row.prediction_date)&history.reference_date.le(row.prediction_date)]
        if not len(valid):continue
        latest=valid.sort_values(["reference_date","available_date"]).iloc[-1]
        matched.loc[index,["migration_rate","migration_reference_date","migration_available_date","migration_vintage","migration_source_url"]]=[latest.net_domestic_migration_per_1000,latest.reference_date,latest.available_date,int(latest.vintage),latest.source_url]
    matched["migration_rate"]=pd.to_numeric(matched.migration_rate,errors="coerce")
    matched.to_csv(out/"migration-matched-events.csv",index=False)
    provenance={"created_at_utc":datetime.now(timezone.utc).isoformat(),"definition":"Published Census net domestic migration rate per 1,000 average residents; negative=net domestic outflow. Not gross departures or international emigration.","availability":"Conservative day-after Census directory file timestamps, not independently verified first-release dates","boundary_source":SHAPE_URL,"boundary_sha256":hashlib.sha256(shape_path.read_bytes()).hexdigest(),"county_count":crosswalk.county_fips.nunique(),"building_count":len(crosswalk),"matched_events":int(matched.migration_rate.notna().sum()),"total_events":len(matched),"vintages":manifest,"limitations":["County context is not tenant migration","2023 generalized boundaries used for mapping; no historical boundary reconstruction","No vintage-2020 input: last available 2019 observation carries forward until vintage 2021 is available","Historical CSV downloads cannot independently certify absence of later corrections","Repeated county-year values are not independent macroeconomic observations"]}
    (out/"migration-provenance.json").write_text(json.dumps(provenance,indent=2),encoding="utf-8")
    print(json.dumps({k:provenance[k] for k in ["county_count","building_count","matched_events","total_events"]}))
if __name__=="__main__":main()
