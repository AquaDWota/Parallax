"""Turn the CoStar hackathon extract into the tables the pipeline needs.

Put the two files in data/real/ (git-ignored) and run:
    python -m scripts.prepare_costar

Inputs : data/real/location-occupancy.jsonl, data/real/company-detail.jsonl
Outputs: data/real/costar_properties.csv  one row per property with a location
         data/real/costar_leases.csv      one row per lease expiry 2016-2026 with an inferred outcome
         data/real/costar_buildings.csv   properties ranked for imaging -> scripts.batch_car_counts --buildings

How the files join:
  occupancy.tenantLocationId == company.id          (tenant)
  occupancy.addressId        == company.address.id  (property location: lat/long, city)

Outcome at lease expiry E (leaseDeal.expirationDate), from the tenant's occupancy end T (toDate):
  * same tenant starts another occupancy at the property within 180 days of T  -> renewed / downsized / expanded (by sq ft)
  * T open, or T more than 365 days after E                                    -> renewed
  * T within 180 days after E (or before E)                                    -> moved_out
  * otherwise ambiguous, or E still in the future                              -> excluded
expirationReason is a CoStar code we don't have the key for; it's kept as a column.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from parallax.config import DATA_DIR

REAL = DATA_DIR / "real"
TODAY = datetime(2026, 11, 1)


def _d(s):
    return datetime.fromisoformat(s[:10]) if s else None


def _sqft(o):
    return sum((s.get("squareFeetOccupied") or 0) for s in (o.get("spaces") or []))


def main():
    occ = [json.loads(l) for l in open(REAL / "location-occupancy.jsonl") if l.strip()]
    co = [json.loads(l) for l in open(REAL / "company-detail.jsonl") if l.strip()]
    company = {c["id"]: c for c in co}
    addr = {c["address"]["id"]: c["address"] for c in co if c.get("address")}

    # ---------- properties ----------
    props = {}
    for o in occ:
        a = addr.get(o.get("addressId"))
        if not a or a.get("latitude") is None:
            continue
        p = props.setdefault(o["propertyId"], dict(
            property_id=o["propertyId"], city=(a.get("city") or "").title(), state=a.get("state"),
            address=f"{a.get('streetNumber', '')} {a.get('streetName', '')} {a.get('streetType', '') or ''}".strip(),
            postcode=(a.get("postcode") or "")[:5], lat=a["latitude"], lon=a["longitude"],
            n_occupancies=0, n_tenants=set(), max_tenant_sqft=0.0, space_use=Counter()))
        p["n_occupancies"] += 1
        p["n_tenants"].add(o.get("tenantLocationId"))
        p["max_tenant_sqft"] = max(p["max_tenant_sqft"], _sqft(o))
        su = (o.get("leaseDeal") or {}).get("spaceUse")
        if su is not None:
            p["space_use"][su] += 1

    # ---------- lease expiry events ----------
    by_pair = defaultdict(list)
    for o in occ:
        by_pair[(o["propertyId"], o.get("tenantLocationId"))].append(o)
    events = []
    for o in occ:
        ld = o.get("leaseDeal") or {}
        E = _d(ld.get("expirationDate"))
        if not E or not (datetime(2016, 1, 1) <= E <= TODAY - timedelta(days=90)):
            continue
        if o["propertyId"] not in props:
            continue
        T = _d(o.get("toDate"))
        sq = _sqft(o)
        outcome = None
        if T:
            nxt = [x for x in by_pair[(o["propertyId"], o.get("tenantLocationId"))]
                   if x is not o and _d(x["fromDate"]) and abs((_d(x["fromDate"]) - T).days) <= 180]
            if nxt:
                s2 = _sqft(nxt[0])
                outcome = ("downsized" if sq and s2 < 0.85 * sq else
                           "expanded" if sq and s2 > 1.15 * sq else "renewed")
            elif T > E + timedelta(days=365):
                outcome = "renewed"
            elif T <= E + timedelta(days=180):
                outcome = "moved_out"
        else:
            outcome = "renewed"
        if outcome is None:
            continue
        c = company.get(o.get("tenantLocationId"), {})
        prof = c.get("profile") or {}
        events.append(dict(
            lease_id=o["id"], building_id=f"P{o['propertyId']}", property_id=o["propertyId"],
            tenant=(prof.get("companyName") or c.get("name") or "").strip(),
            tenant_industry=prof.get("industryType", ""), tenant_employees=c.get("numEmployees", ""),
            sqft=sq, start_date=(ld.get("commencementDate") or o.get("fromDate") or "")[:10],
            expiry_date=E.date().isoformat(), move_out_date=T.date().isoformat() if T else "",
            outcome=outcome, expiration_reason=o["expirationReason"], space_use=ld.get("spaceUse", ""),
            rent_psf=(ld.get("rateActual") or {}).get("value", "") if isinstance(ld.get("rateActual"), dict) else ld.get("rateActual", ""),
        ))

    # ---------- write ----------
    ev_by_prop = Counter(e["property_id"] for e in events if e["expiry_date"] >= "2018")
    with open(REAL / "costar_properties.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["building_id", "property_id", "city", "state", "address", "postcode", "lat", "lon",
                    "n_occupancies", "n_tenants", "max_tenant_sqft", "main_space_use", "n_expiries_2018_on"])
        for p in props.values():
            w.writerow([f"P{p['property_id']}", p["property_id"], p["city"], p["state"], p["address"], p["postcode"],
                        p["lat"], p["lon"], p["n_occupancies"], len(p["n_tenants"]), p["max_tenant_sqft"],
                        p["space_use"].most_common(1)[0][0] if p["space_use"] else "", ev_by_prop.get(p["property_id"], 0)])
    with open(REAL / "costar_leases.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(events[0].keys()))
        w.writeheader()
        w.writerows(events)
    ranked = sorted((p for p in props.values() if ev_by_prop.get(p["property_id"])),
                    key=lambda p: -ev_by_prop[p["property_id"]])
    with open(REAL / "costar_buildings.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["building_id", "lat", "lon", "name", "city", "area", "n_expiries"])
        for p in ranked:
            w.writerow([f"P{p['property_id']}", p["lat"], p["lon"], p["address"], p["city"], p["postcode"],
                        ev_by_prop[p["property_id"]]])

    oc = Counter(e["outcome"] for e in events)
    print(f"properties with location: {len(props):,}  ({Counter(p['city'] for p in props.values()).most_common(3)})")
    print(f"lease expiries 2016-2026 with an outcome: {len(events):,}  {dict(oc)}")
    print(f"properties to image (have expiries 2018+): {len(ranked)}  -> {REAL / 'costar_buildings.csv'}")


if __name__ == "__main__":
    sys.exit(main())
