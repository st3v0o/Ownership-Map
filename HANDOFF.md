# Handoff: Richmond ownership map

Status as of 2026-10-01. Branch `claude/richmond-ownership-map`, PR #1.

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

## Problems to fix next

1. **Owner-occupied detection is broken (0% green).** `AsrLocationBldgNo` holds **only the house number**; this layer has no street name for the property. Options, best first:
   - Get the property street address from another source, either a Richmond address-points layer (search the same ArcGIS org `k3vhq11XkBNeeOfM` for "Address") joined by ParcelID/PIN or spatially, or the City Assessor's free Public Data Set (rva.gov/assessor-real-estate/data-request), joined by PIN.
   - Fallback heuristic: owner-occupied when the mailing house number equals `AsrLocationBldgNo`, `MailCity` is Richmond, and the mailing address is not a PO box. This is a reasonable approximation with few false positives.
   - Also show the full property address in popups. Right now popups show only the house number.
2. **Public/non-profit false positives.**
   - "Church Hill Ventures Llc" is caught by `CHURCH` (Church Hill is a neighborhood).
   - "Dobrin College Park Llc" is caught by `COLLEGE`.
   - "Up Randolph Llc C/o University Property..." is caught by `UNIVERSITY` in the care-of agent.

   Fixes: strip everything from `C/O` onward before classifying; don't let neighborhood names (Church Hill, College Park, University Heights) count as non-profit; when the name has an LLC/INC and the only non-profit hit is a weak word, call it a company.
3. **Private "land trusts"** ("205 E 12th St Land Trust Trustees", "Porter Street 3108 Land Trust Trustee") are anonymous investor vehicles, not community land trusts. Treat `<address> LAND TRUST` as a company. Keep named community land trusts (e.g., Maggie Walker Community Land Trust) as non-profit.
4. **Top-owner grouping:** names like "AWE BROOKSIDE OWNER LLC C O WEST END CAPITAL GROUP LLC" should drop the `C/O` part. Consider also grouping by mailing address to catch one investor that uses many LLCs (optional).
5. **Verify the tiles.** tile-join warned `mismatched maxzooms: 16 vs previous 13`. Check that the final `parcels.pmtiles` header says minzoom 11 / maxzoom 16; if it says 13, the map never loads detail tiles and popups break. The output is 15 MB. Test locally with a range-capable server (`npx http-server`; Python's http.server doesn't support Range requests).
6. **`MaskedOwner`:** check what it holds (possibly owners who requested privacy) and handle it.
7. Add unit tests for every rule change above, using the real names quoted here.

## Getting it live

1. Merge PR #1 to `main`. Only `main` deploys.
2. In the repo, go to **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Re-run the workflow (or push to `main`). The site will be at `https://st3v0o.github.io/Ownership-Map/`.

## Network hosts the session needs

`services1.arcgis.com`, `*.arcgis.com`, `rva.gov`, `www.rva.gov` for data. For local browser testing, also `*.basemaps.cartocdn.com` and `nominatim.openstreetmap.org`. If these are still blocked, keep using the Actions-log loop: push, wait for the run, read the logs with the GitHub tools.
