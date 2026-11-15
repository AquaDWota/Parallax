"""Turn the CoStar hackathon extract into the tables the pipeline needs.

Put the two files in data/real/ (git-ignored) and run:
    python -m scripts.prepare_costar

Inputs : data/real/location-occupancy.jsonl, data/real/company-detail.jsonl,
         data/real/commercial-property.jsonl (type, class, RBA, submarket, parking by type)
Outputs: data/real/costar_properties.csv  one row per property with a location
         data/real/costar_occupancy.csv   every tenancy (from/to dates, sq ft) -> building occupancy over time
         data/real/costar_leases.csv      one row per lease expiry 2016-2026 with an inferred outcome
         data/real/costar_buildings.csv   properties ranked for imaging -> scripts.batch_car_counts --buildings

How the files join:
  occupancy.tenantLocationId == company.id          (tenant)
  occupancy.addressId        == company.address.id  (property location: lat/long, city)

Outcome at lease expiry E (leaseDeal.expirationDate). CoStar's expirationReason decides when it's informative:
  7 Renewal, 12 MovingIntoSameBuilding  -> renewed / downsized / expanded (sq ft of the next occupancy)
  8 ShedSpace                           -> downsized
  1,3,4,5,6,10,13 (moved / closed)      -> moved_out
Otherwise (0 Unknown, 2 UnableToConfirm, 14 OccupancySplit) fall back to dates, using the occupancy end T:
  * same tenant starts another occupancy there within 180 days of T -> renewed / downsized / expanded
  * T open, or T more than 365 days after E                         -> renewed
  * T within 180 days after E (or before E)                         -> moved_out
  * otherwise ambiguous -> excluded. Expiries in the future are excluded.

Measurable = mostly surface parking: >= 30 surface stalls and surface >= 40% of known stalls.
Apartments (propertyType 11) are left out of imaging: residents' cars would swamp the commercial tenants.
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


PTYPE = {1: "hospitality", 2: "industrial", 3: "land", 5: "office", 6: "retail", 7: "flex", 8: "sports",
         9: "mixed_use", 10: "specialty", 11: "multifamily", 13: "healthcare"}
CLASS = {1: "A", 2: "B", 3: "C", 4: "F"}
MOVED = {1, 3, 4, 5, 6, 10, 13}
STAYED = {7, 12}


def load_property_attrs(ids: set) -> dict:
    path = REAL / "commercial-property.jsonl"
    out = {}
    if not path.exists():
        print("note: commercial-property.jsonl not found - no type/class/parking")
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            p = json.loads(line)
            if p["id"] not in ids:
                continue
            spaces = {}
            for x in p.get("parking") or []:
                t = x.get("parkingType")
                spaces[t] = spaces.get(t, 0) + (x.get("totalSpaces") or 0)
            surface = spaces.get(1, 0) + spaces.get(2, 0)
            known = sum(spaces.values())
            share = surface / known if known else None
            rba = p.get("rentableBuildingAreaSquareFeet")
            if surface >= 30 and (share is None or share >= 0.4):
                ptype = "surface"
            elif known and surface < 30:
                ptype = "structured"
            elif not p.get("parking"):
                ptype = "unknown"
            else:
                ptype = "mixed"
            out[p["id"]] = dict(property_type=PTYPE.get(p.get("propertyType"), "other"),
                                building_class=CLASS.get(p.get("buildingClass"), ""),
                                rba_sqft=rba or "", year_built=p.get("yearBuilt") or "",
                                submarket_id=p.get("primarySubmarketId") or "",
                                surface_spaces=surface, total_spaces=known,
                                parking_ratio=p.get("parkingRatio") or "", parking_type=ptype)
    return out


def main():
    occ = [json.loads(l) for l in open(REAL / "location-occupancy.jsonl", encoding="utf-8") if l.strip()]
    co = [json.loads(l) for l in open(REAL / "company-detail.jsonl", encoding="utf-8") if l.strip()]
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
        reason = o["expirationReason"]
        if T and reason in MOVED:
            outcome = "moved_out"
        elif T and reason == 8:
            outcome = "downsized"
        elif T and reason in STAYED:
            nxt = [x for x in by_pair[(o["propertyId"], o.get("tenantLocationId"))]
                   if x is not o and _d(x["fromDate"]) and abs((_d(x["fromDate"]) - T).days) <= 365]
            s2 = _sqft(nxt[0]) if nxt else sq
            outcome = ("downsized" if sq and s2 < 0.85 * sq else
                       "expanded" if sq and s2 > 1.15 * sq else "renewed")
        elif T:
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
        if T and reason in MOVED and T < E - timedelta(days=365):
            continue  # left more than a year before expiry: not a decision at expiry
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

    attrs = load_property_attrs(set(props))
    blank = dict(property_type="", building_class="", rba_sqft="", year_built="", submarket_id="",
                 surface_spaces="", total_spaces="", parking_ratio="", parking_type="unknown")

    # ---------- write ----------
    ev_by_prop = Counter(e["property_id"] for e in events if e["expiry_date"] >= "2018")
    with open(REAL / "costar_properties.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["building_id", "property_id", "city", "state", "address", "postcode", "lat", "lon",
                    "n_occupancies", "n_tenants", "max_tenant_sqft", "main_space_use", "n_expiries_2018_on"] + list(blank))
        for p in props.values():
            a = attrs.get(p["property_id"], blank)
            w.writerow([f"P{p['property_id']}", p["property_id"], p["city"], p["state"], p["address"], p["postcode"],
                        p["lat"], p["lon"], p["n_occupancies"], len(p["n_tenants"]), p["max_tenant_sqft"],
                        p["space_use"].most_common(1)[0][0] if p["space_use"] else "", ev_by_prop.get(p["property_id"], 0)]
                       + [a[k] for k in blank])
    with open(REAL / "costar_leases.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(events[0].keys()))
        w.writeheader()
        w.writerows(events)
    def imageable(p):
        a = attrs.get(p["property_id"], blank)
        return (ev_by_prop.get(p["property_id"]) and a["property_type"] != "multifamily"
                and a["parking_type"] in ("surface", "mixed", "unknown"))
    ranked = sorted((p for p in props.values() if imageable(p)),
                    key=lambda p: ({"surface": 0, "mixed": 1}.get(attrs.get(p["property_id"], blank)["parking_type"], 2),
                                   -ev_by_prop[p["property_id"]]))
    with open(REAL / "costar_buildings.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["building_id", "lat", "lon", "name", "city", "area", "n_expiries", "property_type",
                    "building_class", "surface_spaces", "parking_type"])
        for p in ranked:
            a = attrs.get(p["property_id"], blank)
            w.writerow([f"P{p['property_id']}", p["lat"], p["lon"], p["address"], p["city"], a["submarket_id"],
                        ev_by_prop[p["property_id"]], a["property_type"], a["building_class"],
                        a["surface_spaces"], a["parking_type"]])

    with open(REAL / "costar_occupancy.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["building_id", "occupancy_id", "tenant_location_id", "from_date", "to_date", "sqft", "expiration_reason"])
        n_occ = 0
        for o in occ:
            if o["propertyId"] not in props or not o.get("fromDate"):
                continue
            w.writerow([f"P{o['propertyId']}", o["id"], o.get("tenantLocationId") or "", o["fromDate"][:10],
                        (o.get("toDate") or "")[:10], _sqft(o), o["expirationReason"]])
            n_occ += 1

    oc = Counter(e["outcome"] for e in events)
    print(f"properties with location: {len(props):,}  ({Counter(p['city'] for p in props.values()).most_common(3)})")
    print(f"tenancies written for occupancy: {n_occ:,}")
    print(f"lease expiries 2016-2026 with an outcome: {len(events):,}  {dict(oc)}")
    pt = Counter(attrs.get(p, blank)["parking_type"] for p in ev_by_prop)
    print(f"parking at properties with 2018+ expiries: {dict(pt)}")
    print(f"properties to image (non-apartment; surface first, then mixed surface+garage): {len(ranked)}  -> {REAL / 'costar_buildings.csv'}")
    print(f"expiries at those properties: {sum(ev_by_prop[p['property_id']] for p in ranked):,}")


if __name__ == "__main__":
    sys.exit(main())
