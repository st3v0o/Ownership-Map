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
from summary import build_summary  # noqa: E402
from classify import (CATEGORIES, COMPANY, classify, normalize_street, owner_key, same_address,
                      same_house_number)  # noqa: E402

LAYER_URL = os.environ.get(
    "PARCELS_LAYER_URL",
    "https://services1.arcgis.com/k3vhq11XkBNeeOfM/ArcGIS/rest/services/Parcels/FeatureServer/0",
)
QUERY_URL = LAYER_URL + "/query"

# The parcel layer only carries the property's house number, so street
# addresses come from the city's address tables, joined by PIN.
_SERVICES = "https://services1.arcgis.com/k3vhq11XkBNeeOfM/ArcGIS/rest/services/"
ADDRESS_SOURCES = [
    # (query URL, PIN field, address field, object-id field)
    (_SERVICES + "All_Address_Parcel_Asr_View/FeatureServer/3/query", "PIN", "AddressLabelWithUnit", "OBJECTID"),
    (_SERVICES + "Addresses_Single_PIN/FeatureServer/0/query", "PIN", "AddressLabel", "ESRI_OID"),
]

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


def fetch_addresses():
    """Return {PIN: [street address, ...]} from every address source."""
    by_pin = collections.defaultdict(list)
    for url, f_pin, f_addr, oid in ADDRESS_SOURCES:
        n = offset = 0
        try:
            while True:
                data = get_json(url, {
                    "f": "json", "where": "1=1", "outFields": f"{f_pin},{f_addr}",
                    "returnGeometry": "false", "orderByFields": oid,
                    "resultOffset": offset, "resultRecordCount": 2000,
                })
                feats = data.get("features", [])
                if not feats:
                    break
                for feat in feats:
                    a = feat["attributes"]
                    pin, addr = (a.get(f_pin) or "").strip(), re.sub(r"\s+", " ", a.get(f_addr) or "").strip()
                    if pin and addr and addr not in by_pin[pin]:
                        by_pin[pin].append(addr)
                        n += 1
                offset += len(feats)
        except Exception as e:  # noqa: BLE001
            print(f"  address source failed, continuing without it: {url}: {e}", flush=True)
        print(f"Addresses from {url.split('/services/')[1]}: {n}", flush=True)
    return by_pin


def property_addresses(candidates, bldg_no):
    """Street addresses for one parcel, best first: those whose house number
    matches the assessor's, without unit numbers, deduplicated."""
    b = (bldg_no or "").strip().upper()
    match = [a for a in candidates if b and a.upper().split(" ")[0] == b.split(" ")[0]]
    seen, out = set(), []
    for a in sorted(match, key=len):
        key = normalize_street(a)
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


# Facets the page's charts filter on. Order matters: the page uses the index.
LAND_USES = ["Single Family", "Duplex (2 Family)", "Multi-Family"]
WHERE = ["at_property", "richmond", "virginia", "out_of_state", "unknown"]
FACET_ORIGIN = (-77.75, 37.35)  # centroids are stored as 1e-5 degree offsets from here


def owner_location(addrs, bldg, mail_line, mail_city, mail_state):
    """Index into WHERE: where the owner's tax bill is mailed."""
    if any(same_address(a, mail_line) for a in addrs) or (
            not addrs and same_house_number(bldg, mail_line, mail_city)):
        return 0
    if not mail_line.strip():
        return 4
    if (mail_city or "").strip().upper() == "RICHMOND":
        return 1
    if (mail_state or "").strip().upper() in ("VA", "VIRGINIA"):
        return 2
    return 3


def centroid(geom):
    """Vertex average of the largest outer ring; good enough to place a lot."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    ring = max((p[0] for p in polys if p), key=len)
    return sum(x for x, _ in ring) / len(ring), sum(y for _, y in ring) / len(ring)


def display_address(addrs, mail_line):
    """The parcel's address for the popup: the one tax bills go to when it is
    one of them, else the first; extra addresses are summarised."""
    if not addrs:
        return ""
    main = next((a for a in addrs if same_address(a, mail_line)), addrs[0])
    rest = [a for a in addrs if a != main]
    if len(rest) == 1:
        return f"{main} / {rest[0]}"
    return f"{main} (+{len(rest)} more)" if rest else main


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
    f_pin = pick_field(fields, ["PIN", "GPIN"])
    f_lu = pick_field(fields, ["LandUse", "LandUseDesc", "LandUseDescription", "LUC", "PropertyClass"], must=("LAND", "USE"))
    f_id = pick_field(fields, ["ParcelID", "PIN", "Parcel_ID", "GPIN"], must=("PARCEL",)) or oid
    f_value = pick_field(fields, ["TotalValue", "TotalAssessment", "AssessedValue"], must=("TOTAL", "VAL"))
    f_year = pick_field(fields, ["YearBuilt", "Year_Built"], must=("YEAR",))

    picked = dict(id=f_id, owner=f_owner, owner2=f_owner2, mail=f_mail, mail2=f_mail2,
                  mail_city=f_mcity, mail_state=f_mstate, mail_zip=f_mzip,
                  address=f_addr, pin=f_pin, land_use=f_lu, value=f_value, year=f_year)
    print("Field mapping:", json.dumps(picked, indent=2))
    if not (f_owner and f_mail and f_addr):
        sys.exit("Could not find owner / mailing address / property address fields; see field list above.")

    sample = get_json(QUERY_URL, {"f": "json", "where": "1=1", "outFields": "*",
                                  "returnGeometry": "false", "resultRecordCount": 8})
    print("Sample records:")
    for feat in sample.get("features", []):
        print(" ", json.dumps(feat["attributes"])[:600])

    addresses = fetch_addresses() if f_pin else {}
    joined = fallback = 0

    out_fields = sorted({oid, *[v for v in picked.values() if v]})
    page = min(int(meta.get("maxRecordCount") or 1000), 2000)

    land_uses = collections.Counter()
    by_cat = collections.Counter()
    company_owners = collections.Counter()
    samples = collections.defaultdict(list)
    kept = skipped = 0
    facets = {k: [] for k in ("c", "v", "u", "w", "x", "y")}
    records = []  # one small dict per lot for summary.json

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
            bldg = str(p.get(f_addr) or "").strip()
            mail_city = str(p.get(f_mcity) or "") if f_mcity else None
            addrs = property_addresses(addresses.get(str(p.get(f_pin) or "").strip(), []), bldg)
            if addrs:
                joined += 1
            else:
                fallback += 1
            cat, reason = classify(owner, addrs, mail_line, bldg, mail_city)
            # A second mail line ("APT 2" / c/o) can hold the street; try it too.
            if f_mail2 and cat != COMPANY and reason.endswith("mailed elsewhere"):
                alt = classify(owner, addrs, str(p.get(f_mail2) or ""), bldg, mail_city)
                if alt[0] != cat:
                    cat, reason = alt
            addr = display_address(addrs, mail_line) or bldg
            by_cat[cat] += 1
            if cat == COMPANY:
                company_owners[owner_key(owner)] += 1
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
                "u": LAND_USES.index(lu) if lu in LAND_USES else len(LAND_USES),
                "w": owner_location(addrs, bldg, mail_line, mail_city,
                                    str(p.get(f_mstate) or "") if f_mstate else ""),
            }
            cx, cy = centroid(feat["geometry"])
            facets["c"].append(props["c"])
            facets["v"].append(round(p.get(f_value) / 1000) if f_value and p.get(f_value) is not None else -1)
            facets["u"].append(props["u"])
            facets["w"].append(props["w"])
            facets["x"].append(round((cx - FACET_ORIGIN[0]) * 1e5))
            facets["y"].append(round((cy - FACET_ORIGIN[1]) * 1e5))
            records.append({
                "key": owner_key(owner), "name": owner, "c": props["c"], "w": props["w"],
                "v": p.get(f_value) if f_value else None, "mail": mail_line,
                "city": str(p.get(f_mcity) or "").strip() if f_mcity else "",
                "state": str(p.get(f_mstate) or "").strip() if f_mstate else "",
                "id": props["id"], "a": addr, "lu": lu, "x": cx, "y": cy,
            })
            if f_value and p.get(f_value) is not None:
                props["v"] = p.get(f_value)
            if f_year and p.get(f_year):
                props["y"] = p.get(f_year)
            nd.write(json.dumps({"type": "Feature", "geometry": feat["geometry"], "properties": props}) + "\n")
            kept += 1

    print(f"\nKept {kept} residential parcels, skipped {skipped} non-residential.")
    print(f"Street address joined for {joined} ({joined / max(kept, 1):.1%}); "
          f"house-number fallback for {fallback}.")
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

    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    summary, featured = build_summary(records, CATEGORIES, generated)

    # Tag lots so the map can outline an owner: k = rank among the largest
    # company owners (map panel), g = owner id from summary.json (summary page).
    top = {n: i + 1 for i, (n, _) in enumerate(company_owners.most_common(25))}
    tmp = nd_path + ".tmp"
    with open(nd_path) as src, open(tmp, "w") as dst:
        for line in src:
            f = json.loads(line)
            key = owner_key(f["properties"]["o"])
            k = top.get(key) if f["properties"]["c"] == CATEGORIES.index(COMPANY) else None
            g = featured.get(key)
            if k:
                f["properties"]["k"] = k
            if g:
                f["properties"]["g"] = g
            if k or g:
                line = json.dumps(f) + "\n"
            dst.write(line)
    os.replace(tmp, nd_path)

    stats = {
        "generated": generated,
        "source": LAYER_URL,
        "total": kept,
        "categories": {c: by_cat[c] for c in CATEGORIES},
        "top_company_owners": [{"rank": top[n], "name": n, "parcels": k} for n, k in company_owners.most_common(25)],
    }
    # Per-lot facets for the page's linked charts (columnar, values in $1000s).
    with open(os.path.join(args.out, "facets.json"), "w") as f:
        json.dump({"origin": FACET_ORIGIN, "scale": 1e5, "value_unit": 1000,
                   "land_uses": LAND_USES, "where": WHERE, **facets}, f, separators=(",", ":"))
    print("\nOwner location:", dict(collections.Counter(WHERE[w] for w in facets["w"])))
    print("Land use index:", dict(collections.Counter(facets["u"])))
    with open(os.path.join(args.out, "stats.json"), "w") as f:
        json.dump(stats, f, indent=1)
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(summary, f, separators=(",", ":"))
    print("\nTop owners by lots:")
    for r in summary["owners"]["lots"]["all"][:15]:
        print(f"  {r['lots']:>5}  ${r['value']:>13,}  {CATEGORIES[r['c']]:<20} {r['name']}")
    print("\nTop owners by assessed value:")
    for r in summary["owners"]["value"]["all"][:15]:
        print(f"  {r['lots']:>5}  ${r['value']:>13,}  {CATEGORIES[r['c']]:<20} {r['name']}")
    print("\nShared mailing addresses:")
    for m in summary["mail_groups"][:10]:
        print(f"  {m['lots']:>5} lots  {m['owners']:>3} names  {m['mail'][:45]:<45} {', '.join(m['names'][:2])[:60]}")
    print("\nOut-of-state owners by state:", [(s['state'], s['lots']) for s in summary["states"][:10]])
    print("\nTop company owners:")
    for row in stats["top_company_owners"]:
        print(f"  {row['parcels']:>5}  {row['name']}")
    if kept == 0:
        sys.exit("No residential parcels kept - check the land-use list above.")


if __name__ == "__main__":
    main()
