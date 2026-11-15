"""Run a pinned Git commit against isolated copies of local inputs; no network calls."""
from __future__ import annotations
import argparse, hashlib, io, json, os, shutil, subprocess, sys, zipfile
from datetime import datetime, timezone
from pathlib import Path

WORKER = r'''import json, warnings
from pathlib import Path
from fastapi.testclient import TestClient
import statsmodels.formula.api as smf
from api.main import app
from parallax import analysis, config, store
s=store.build()
ev,exclusions=s.events(0)
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    formula="renewed ~ usage + trend + " + " + ".join(analysis._controls_for(ev))
    try:
        fit=smf.logit(formula,data=ev).fit(disp=0,maxiter=200)
        fit_status={"converged":bool(fit.mle_retvals.get("converged",False)),"n":int(fit.nobs),"formula":formula}
    except Exception as error:
        fit_status={"converged":False,"error":str(error),"formula":formula}
fit_status["warnings"]=list(dict.fromkeys(str(w.message) for w in caught))
# Exercise the actual API handlers without starting another long-running server.
responses={}
with TestClient(app) as client:
    for name,url in [("health","/api/health"),("metadata","/api/meta"),("results","/api/results/overview")]:
        response=client.get(url)
        responses[name]={"status_code":response.status_code}
        if response.status_code==200:responses[name]["data"]=response.json()
        else:responses[name]["error"]=response.text[:2000]
    try:
        response=client.post("/api/tools/shadow_vacancy_screen",json={})
        responses["risk_screen"]={"status_code":response.status_code,"data":response.json()}
    except Exception as error:responses["risk_screen"]={"error":str(error)}
report={"api_responses":responses,"event_exclusions":exclusions,"renewal_fit_status":fit_status,"prediction":analysis.out_of_sample(ev),"counts":{"buildings":len(s.buildings),"lease_events_in_database":len(s.leases),"eligible_events":len(ev)}}
Path(config.DATA_DIR.parent / "updated-app-results.json").write_text(json.dumps(report,indent=2,default=str),encoding="utf-8")
print(json.dumps({"counts":report["counts"],"converged":fit_status["converged"],"prediction":report["prediction"]}))
'''

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--ref",required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    sha=subprocess.check_output(["git","rev-parse",args.ref],cwd=root,text=True).strip()
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run=root/"data/results/version-comparisons"/(stamp+"-"+sha[:7]);run.mkdir(parents=True)
    source=root/".tools/parallax-reruns"/sha/"source"
    if not source.exists():
        source.mkdir(parents=True)
        archive=subprocess.check_output(["git","archive","--format=zip",sha],cwd=root)
        with zipfile.ZipFile(io.BytesIO(archive)) as z:z.extractall(source)
    data=run/"data";real=data/"real";real.mkdir(parents=True)
    names=["commercial-property.jsonl","location-occupancy.jsonl","company-detail.jsonl","vexcel_buildings.csv","captures.csv","car_counts.csv"]
    manifest=[]
    for name in names:
        old=root/"data/real"/name
        if not old.is_file():raise FileNotFoundError(f"Required existing input missing: {old}")
        shutil.copy2(old,real/name)
        manifest.append({"name":name,"bytes":old.stat().st_size,"sha256":digest(old),"source_mtime_utc":datetime.fromtimestamp(old.stat().st_mtime,timezone.utc).isoformat()})
    env=os.environ.copy();env.update(PARALLAX_DATA_MODE="real",PARALLAX_DATA_DIR=str(data),PARALLAX_AGENT="scripted",PYTHONUTF8="1",PYTHONIOENCODING="utf-8")
    backend=source/"backend"
    # Recreate expiry/occupancy/upcoming CSVs using the pinned preparation code.
    prepared=subprocess.run([sys.executable,"-X","utf8","-m","scripts.prepare_costar"],cwd=backend,env=env,capture_output=True,text=True,encoding="utf-8")
    (run/"preparation.log").write_text(prepared.stdout+prepared.stderr,encoding="utf-8")
    if prepared.returncode:raise RuntimeError(f"Preparation failed; see {run / 'preparation.log'}")
    worker=run/"run_updated_api.py";worker.write_text(WORKER,encoding="utf-8")
    executed=subprocess.run([sys.executable,"-X","utf8","-c",WORKER],cwd=backend,env=env,capture_output=True,text=True,encoding="utf-8")
    (run/"execution.log").write_text(executed.stdout+executed.stderr,encoding="utf-8")
    provenance={"commit":sha,"requested_ref":args.ref,"generated_at_utc":datetime.now(timezone.utc).isoformat(),"comparison_type":"Updated code, existing historical car measurements; not a new CV detection run","network_calls":False,"source_inputs":manifest,"worker_exit_code":executed.returncode}
    (run/"provenance.json").write_text(json.dumps(provenance,indent=2),encoding="utf-8")
    print("RESULT_DIRECTORY="+str(run),flush=True)
    if executed.returncode:raise RuntimeError(f"Updated API run failed; see {run / 'execution.log'}")
    print(executed.stdout,flush=True)
if __name__=="__main__":main()
