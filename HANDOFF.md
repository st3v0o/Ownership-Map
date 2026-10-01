# Handoff: Richmond ownership map

Status as of 2026-10-01 (second session). Branch `claude/richmond-ownership-map`, PR #1.

## Goal

An interactive, zoomable map of every residential lot in Richmond, VA, colored by owner type:

| Color | Category |
|---|---|
| Green | Owner-occupied (individual; tax bill mailed to the property) |
| Amber | Individual landlord (individual; tax bill mailed elsewhere) |
| Red | Company-owned (LLC, corp, bank, investor) |
| Gray | Public / non-profit (government, housing authority, church, community land trust) |

It must work well on a phone and is hosted free on GitHub Pages.

## What exists (all on the branch)

| File | Purpose |
|---|---|
| `scripts/build_data.py` | Downloads the parcels, keeps residential land uses, classifies owners, writes `build/parcels.ndjson` and `build/stats.json`, and logs field names, sample records, land-use counts, category counts, samples per category and top company owners |
| `scripts/classify.py` | Rule-based owner classifier (regex word lists plus a mailing-address comparison) |
| `tests/test_classify.py` | Unit tests: `python -m unittest discover -s tests` |
| `scripts/build_tiles.sh` | tippecanoe builds two zoom ranges (z11–13 with colors only, z14–16 with all attributes), then tile-join produces `site/data/parcels.pmtiles` |
| `site/index.html` | MapLibre page with legend toggles, "in this view" counts, largest company owners (tap to outline their lots), popups, address search (Nominatim), a mobile bottom sheet, and a CARTO raster basemap |
| `package.json` | maplibre-gl and pmtiles; `npm run vendor` copies them into `site/vendor/` (gitignored) |
| `.github/workflows/build-map.yml` | Runs tests, vendors the libraries, builds data and tiles, uploads the Pages artifact, and deploys **only on `main`**. It also runs monthly on the 18th |

The first session could not reach Richmond's servers, so it ran the data build on GitHub Actions and read the logs. The third run (run 36808821468) **succeeded end to end**, but the data has the problems listed below.

## Data source facts (verified from the Actions logs)

The layer is `https://services1.arcgis.com/k3vhq11XkBNeeOfM/ArcGIS/rest/services/Parcels/FeatureServer/0`. Queries go to `.../0/query`, maxRecordCount is 2000, and it holds 76,931 parcels.

Fields: `ParcelID, PIN, CountOfPIN, OwnerName, AsrLocationBldgNo, MailAddress, MailCity, MailState, MailZip, AssessmentDate, LandValue, DwellingValue, TotalValue, LandSqFt, ProvalAsmtNhood, TaxExemptCode, PropertyClassID, PropertyClass, LandUse, Mailable, MaskedOwner, OBJECTID, GlobalID, City, State, Shape__Area, Shape__Length`

LandUse counts:

| LandUse | Parcels |
|---|---|
| Single Family | 53,652 |
| Multi-Family | 7,138 |
| Vacant | 5,775 |
| Commercial | 3,302 |
| Duplex (2 Family) | 2,754 |
| Industrial | 1,255 |
| Office | 785 |
| Institutional | 670 |
| Mixed-Use | 637 |
| Public-Open Space | 616 |
| (blank) | 272 |
| Government | 75 |

63,544 parcels were kept as residential (Single Family, Multi-Family, Duplex).

Sample record: `OwnerName "Johnson Jeremy", AsrLocationBldgNo "6915", MailAddress "6915 Longview Dr", MailCity "Richmond", MailZip "23225", PropertyClass "R One Story", LandUse "Single Family", MaskedOwner null`.

## Fixed in the second session

Richmond's servers were reachable from the Mac, so the build ran locally (full output matched Actions).

1. **Owner-occupied detection.** Street addresses now come from `All_Address_Parcel_Asr_View/FeatureServer/3`
   (`PIN`, `AddressLabelWithUnit`) plus `Addresses_Single_PIN/FeatureServer/0` (`PIN`, `AddressLabel`), joined by PIN
   and kept only when the house number matches `AsrLocationBldgNo`. This joins **99.0%** of residential parcels.
   The other 618 use the house-number fallback (same number, `MailCity` Richmond, not a PO box). Mailing-street typos
   ("Boulders Creek", "Wakfield") still match. Popups show the full address, with "/ second address" or "(+N more)"
   when a parcel has several.
2. **C/O and ATTN agents** are stripped before classifying and before grouping top owners (`owner_key`).
3. **Neighborhood names** (Church Hill, College Park/Hill/Heights, University Heights/Park) don't count as non-profit.
   Weak non-profit words (church, college, university, foundation, ...) next to LLC/LP/Realty/Ventures/... mean company.
4. **Land trusts:** any `LAND TRUST` except a *community* land trust is a private holding, so it counts as a company.
   This catches number-less ones too, like "Crafton Land Trust Trustee".
5. **Tiles verified:** the `parcels.pmtiles` header says minzoom 11 / maxzoom 16, and z14-16 carry every attribute.
   The tile-join "mismatched maxzooms" warning is harmless.
6. **`MaskedOwner`** is null on all 76,931 parcels, so there's nothing to handle.
7. **Basemap:** CARTO raster tiles now return an "API KEY REQUIRED" watermark. The page uses OpenFreeMap's Positron
   style instead (free, no key), with the parcel layers inserted under its labels on `style.load`.
8. Unit tests cover every rule above (20 tests).

Category split after the fixes (63,544 lots): owner-occupied ~65%, individual landlord ~17%, company ~17.5%,
public/non-profit ~0.4%.

## Linked charts (added in the second session)

`site/index.html` has crossfiltered charts: an assessed-value histogram with brush and dual slider, "where the tax bill
goes" rows, land-use rows, the owner-type legend, and a "This view / Whole city" toggle. They are driven by
`site/data/facets.json` (columnar arrays `c, v ($1000s, -1 = none), u, w, x, y` with centroid offsets from `origin`
in 1e-5 degrees), written by `build_data.py`. The map filter uses tile attributes `v` (dollars), `u` and `w`; z11-13
tiles now carry them too. Owner location (`w`): 0 at the property, 1 Richmond mailing city, 2 elsewhere in VA,
3 out of state, 4 no address. Note: "Richmond" mailing city includes Henrico/Chesterfield addresses.

## Summary page

`site/summary.html` reads `site/data/summary.json` from `scripts/summary.py` (unit-tested in `tests/test_summary.py`).
Owners are grouped by `classify.owner_group`: `owner_key` (C/O, /co and ATTN agents dropped) for companies and public
bodies, and owner_key plus the normalized mailing street for people. Every owner gets an id `g`, with the largest owners
getting the smallest numbers. It is written to the tiles at all zooms and to `facets.json` (column `g`), so the popup's
"See all N properties" can find, fit and outline any owner's lots on the client. Map minZoom is 11, matching the tiles. Map deep links: `?g=<id>&b=<w,s,e,n>&n=<name>`
outlines and zooms to an owner; `?pid=<parcel id>#17.5/lat/lon` selects a lot.

## Ideas for later

- Keep filter state in the URL so filtered views can be shared.

- Group one investor's many LLCs by mailing address for the "largest owners" list.
- "Unit Owners Assoc" / condo associations own common areas; consider hiding them.

## Getting it live

1. Merge PR #1 to `main`. Only `main` deploys.
2. In the repo, go to **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Re-run the workflow (or push to `main`). The site will be at `https://st3v0o.github.io/Ownership-Map/`.

## Network hosts the session needs

`services1.arcgis.com`, `*.arcgis.com`, `rva.gov`, `www.rva.gov` for data. For local browser testing, also `tiles.openfreemap.org` and `nominatim.openstreetmap.org`. If these are still blocked, keep using the Actions-log loop: push, wait for the run, read the logs with the GitHub tools.
