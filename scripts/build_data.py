"""Download Richmond, VA parcels, classify residential owners, write map data.

Outputs (in --out, default build/):
  parcels.ndjson   one GeoJSON feature per residential parcel (input to tippecanoe)
  stats.json       city-wide counts and the largest company owners

Source: City of Richmond GeoHub "Parcels" layer, which joins parcel shapes to
the City Assessor's ownership records (CAMA).
"""

import argparse
import collections
import datetime
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from classify import CATEGORIES, COMPANY, classify, normalize_name  # noqa: E402

LAYER_URL = os.environ.get(
    "PARCELS_LAYER_URL",
    "https://services1.arcgis.com/k3vhq11XkBNeeOfM/ArcGIS/rest/services/Parcels/FeatureServer/0",
)
QUERY_URL = LAYER_URL + "/query"

# Land-use descriptions that count as residential. Matched case-insensitively
# against the layer's land-use field.
RESIDENTIAL_RX = re.compile(
    r"RES|SINGLE|FAMILY|DUPLEX|TRIPLEX|QUAD|TOWN ?HO|CONDO|DWELL|MULTI|APART|ROW ?HO|MOBILE|SFD|SFR",
    re.I,
)
NOT_RESIDENTIAL_RX = re.compile(r"VACANT|LAND ONLY|PARKING|COMMERCIAL|OFFICE|RETAIL|INDUSTR", re.I)


def get_json(url, params, tries=5):
    full = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(tries):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": "ownership-map/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            if "error" in data:
                raise RuntimeError(data["error"])
            return data
        except Exception as e:  # noqa: BLE001
            if attempt == tries - 1:
                raise
            wait = 2 ** (attempt + 1)
            print(f"  retry in {wait}s after: {e}", flush=True)
            time.sleep(wait)


def pick_field(fields, exact, must=(), avoid=()):
    names = [f["name"] for f in fields]
    lower = {n.lower(): n for n in names}
    for e in exact:
        if e.lower() in lower:
            return lower[e.lower()]
    if not must:
        return None
    for n in names:
        u = n.upper()
        if all(m in u for m in must) and not any(a in u for a in avoid):
            return n
    return None


def describe_layer():
    meta = get_json(LAYER_URL, {"f": "json"})
    fields = meta.get("fields", [])
    print(f"Layer: {meta.get('name')}  maxRecordCount={meta.get('maxRecordCount')}")
    print("Fields:")
    for f in fields:
        print(f"  {f['name']:<28} {f.get('type', ''):<22} {f.get('alias', '')}")
    return meta, fields


def fetch_features(out_fields, page_size, oid_field):
    count = get_json(QUERY_URL, {"f": "json", "where": "1=1", "returnCountOnly": "true"})["count"]
    print(f"Downloading {count} parcels in pages of {page_size} ...", flush=True)
    offset = 0
    while offset < count:
        data = get_json(QUERY_URL, {
            "f": "geojson",
            "where": "1=1",
            "outFields": ",".join(out_fields),
            "outSR": 4326,
            "geometryPrecision": 6,
            "orderByFields": oid_field,
            "resultOffset": offset,
            "resultRecordCount": page_size,
        })
        feats = data.get("features", [])
        if not feats:
            break
        yield from feats
        offset += len(feats)
        print(f"  {offset}/{count}", flush=True)


def full_mail(props, mail_fields):
    parts = [str(props.get(f) or "").strip() for f in mail_fields if f]
    return ", ".join(p for p in parts if p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="build")
    ap.add_argument("--all-land-uses", action="store_true",
                    help="skip the residential filter (for debugging)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    meta, fields = describe_layer()
    oid = meta.get("objectIdField") or pick_field(fields, ["OBJECTID", "FID"]) or "OBJECTID"
    f_owner = pick_field(fields, ["OwnerName", "Owner_Name", "OWNER"], must=("OWN",), avoid=("ADDR", "CITY", "STATE", "ZIP", "OCC"))
    f_owner2 = pick_field(fields, ["OwnerName2", "Owner2", "OwnerName_2"])
    f_mail = pick_field(fields, ["MailAddress", "MailingAddress", "OwnerAddress", "MailAddr"], must=("MAIL", "ADD"), avoid=("CITY", "STATE", "ZIP"))
    f_mail2 = pick_field(fields, ["MailAddress2", "MailAddress_2"])
    f_mcity = pick_field(fields, ["MailCity"], must=("MAIL", "CITY"))
    f_mstate = pick_field(fields, ["MailState"], must=("MAIL", "STATE"))
    f_mzip = pick_field(fields, ["MailZip", "MailZipCode"], must=("MAIL", "ZIP"))
    f_addr = pick_field(fields, ["AsrLocationBldgNo", "AddressLabel", "SiteAddress", "PropertyAddress", "LocationAddress", "Address", "FullAddress"], must=("ADDR",), avoid=("MAIL", "OWN"))
    f_lu = pick_field(fields, ["LandUse", "LandUseDesc", "LandUseDescription", "LUC", "PropertyClass"], must=("LAND", "USE"))
    f_id = pick_field(fields, ["ParcelID", "PIN", "Parcel_ID", "GPIN"], must=("PARCEL",)) or oid
    f_value = pick_field(fields, ["TotalValue", "TotalAssessment", "AssessedValue"], must=("TOTAL", "VAL"))
    f_year = pick_field(fields, ["YearBuilt", "Year_Built"], must=("YEAR",))

    picked = dict(id=f_id, owner=f_owner, owner2=f_owner2, mail=f_mail, mail2=f_mail2,
                  mail_city=f_mcity, mail_state=f_mstate, mail_zip=f_mzip,
                  address=f_addr, land_use=f_lu, value=f_value, year=f_year)
    print("Field mapping:", json.dumps(picked, indent=2))
    if not (f_owner and f_mail and f_addr):
        sys.exit("Could not find owner / mailing address / property address fields; see field list above.")

    sample = get_json(QUERY_URL, {"f": "json", "where": "1=1", "outFields": "*",
                                  "returnGeometry": "false", "resultRecordCount": 8})
    print("Sample records:")
    for feat in sample.get("features", []):
        print(" ", json.dumps(feat["attributes"])[:600])

    out_fields = sorted({oid, *[v for v in picked.values() if v]})
    page = min(int(meta.get("maxRecordCount") or 1000), 2000)

    land_uses = collections.Counter()
    by_cat = collections.Counter()
    company_owners = collections.Counter()
    samples = collections.defaultdict(list)
    kept = skipped = 0

    nd_path = os.path.join(args.out, "parcels.ndjson")
    with open(nd_path, "w") as nd:
        for feat in fetch_features(out_fields, page, oid):
            p = feat.get("properties") or {}
            if not feat.get("geometry"):
                continue
            lu = str(p.get(f_lu) or "").strip() if f_lu else ""
            land_uses[lu] += 1
            if f_lu and not args.all_land_uses:
                if not RESIDENTIAL_RX.search(lu) or NOT_RESIDENTIAL_RX.search(lu):
                    skipped += 1
                    continue

            owner = " ".join(str(p.get(f) or "").strip() for f in (f_owner, f_owner2) if f).strip()
            mail_line = str(p.get(f_mail) or "").strip()
            addr = str(p.get(f_addr) or "").strip()
            cat, reason = classify(owner, addr, mail_line)
            # A second mail line ("APT 2" / c/o) can hold the street; try it too.
            if f_mail2 and cat != COMPANY and reason.endswith("mailed elsewhere"):
                alt = classify(owner, addr, str(p.get(f_mail2) or ""))
                if alt[0] != cat:
                    cat, reason = alt

            by_cat[cat] += 1
            if cat == COMPANY:
                company_owners[normalize_name(owner)] += 1
            if len(samples[cat]) < 400:
                samples[cat].append((owner, addr, mail_line, reason))

            props = {
                "id": str(p.get(f_id) or ""),
                "a": addr,
                "o": owner,
                "m": full_mail(p, [f_mail, f_mail2, f_mcity, f_mstate, f_mzip]),
                "c": CATEGORIES.index(cat),
                "r": reason,
                "lu": lu,
            }
            if f_value and p.get(f_value) is not None:
                props["v"] = p.get(f_value)
            if f_year and p.get(f_year):
                props["y"] = p.get(f_year)
            nd.write(json.dumps({"type": "Feature", "geometry": feat["geometry"], "properties": props}) + "\n")
            kept += 1

    print(f"\nKept {kept} residential parcels, skipped {skipped} non-residential.")
    print("\nLand-use values (count, kept?):")
    for lu, n in land_uses.most_common(80):
        keep = bool(RESIDENTIAL_RX.search(lu)) and not NOT_RESIDENTIAL_RX.search(lu)
        print(f"  {n:>7}  {'KEEP' if keep else '    '}  {lu}")
    print("\nCategories:")
    for c in CATEGORIES:
        print(f"  {c:<22} {by_cat[c]:>7}  ({by_cat[c] / max(kept, 1):.1%})")
    rnd = random.Random(1)
    for c in CATEGORIES:
        print(f"\nSample {c}:")
        for owner, addr, mail, reason in rnd.sample(samples[c], min(15, len(samples[c]))):
            print(f"  {owner[:40]:<40} | {addr[:28]:<28} | {mail[:28]:<28} | {reason}")

    # Tag the largest company owners' lots (k = rank) so the map can outline them.
    top = {n: i + 1 for i, (n, _) in enumerate(company_owners.most_common(25))}
    tmp = nd_path + ".tmp"
    with open(nd_path) as src, open(tmp, "w") as dst:
        for line in src:
            f = json.loads(line)
            if f["properties"]["c"] == CATEGORIES.index(COMPANY):
                k = top.get(normalize_name(f["properties"]["o"]))
                if k:
                    f["properties"]["k"] = k
                    line = json.dumps(f) + "\n"
            dst.write(line)
    os.replace(tmp, nd_path)

    stats = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
        "source": LAYER_URL,
        "total": kept,
        "categories": {c: by_cat[c] for c in CATEGORIES},
        "top_company_owners": [{"rank": top[n], "name": n, "parcels": k} for n, k in company_owners.most_common(25)],
    }
    with open(os.path.join(args.out, "stats.json"), "w") as f:
        json.dump(stats, f, indent=1)
    print("\nTop company owners:")
    for row in stats["top_company_owners"]:
        print(f"  {row['parcels']:>5}  {row['name']}")
    if kept == 0:
        sys.exit("No residential parcels kept - check the land-use list above.")


if __name__ == "__main__":
    main()
