# Ownership Map — Richmond, VA

An interactive map of every residential lot in Richmond, colored by who owns it:

| Color | Category | Rule |
|---|---|---|
| 🟩 Green | Owner-occupied | Individual (or family trust / estate) whose tax bill is mailed to the property |
| 🟨 Amber | Individual landlord | Individual whose tax bill is mailed somewhere else |
| 🟥 Red | Company-owned | LLC, corporation, partnership, bank, investor |
| ⬜ Gray | Public / non-profit | Government, housing authority, church, community land trust, university |

Tap any lot to see the owner, mailing address, and why it got its color. **See all N
properties by this owner** zooms out to fit everything that owner has, outlines it and fades
the rest; the bar at the top clears it. Companies are matched by name; people by name and
mailing address, so two different John Smiths are not merged. The panel
has linked charts that filter the map and each other:

- **Assessed value** histogram, stacked by owner type: drag across it or use the
  two-handle slider to show only lots in a price range.
- **Where the tax bill goes** (at the property / Richmond / elsewhere in Virginia /
  out of state) and **Land use** (single family / duplex / multi-family): tap a row
  to filter, tap more rows to add them.
- The legend toggles owner types. Every chart counts lots **in the current view** (or
  **the whole city**) with all the *other* filters applied, so you can see what a
  filter would add before you pick it. Tapping a lot marks where it falls in each chart.

It also lists the largest company owners (tap one to outline all of its lots).

**Summary page** (`summary.html`): headline numbers, owner-type totals (lots, value,
median value, out-of-state), the top 10–100 owners by number of lots or total assessed
value (filterable by owner type), the most valuable properties, mailing addresses that
receive bills for many lots under different owner names, and out-of-state owners by
state. Every owner, property and address links to the map, outlined.

## How it works

- **Data:** the City of Richmond GeoHub *Parcels* layer, which joins parcel shapes to the
  City Assessor's ownership records.
- **Property addresses:** the Parcels layer only has the house number, so street
  addresses come from the city's *All_Address_Parcel_Asr_View* and
  *Addresses_Single_PIN* tables, joined by PIN (about 99% of residential parcels).
  For the rest, a lot counts as owner-occupied when the mailing address has the same
  house number, is in Richmond, and is not a PO box.
- `scripts/build_data.py` downloads the parcels, keeps residential land uses, and
  classifies each owner with the rules in `scripts/classify.py`.
- The build also writes `facets.json` (each lot's owner type, value, land use, owner
  location and centroid, about 400 KB gzipped) so the charts can count at any zoom.
- `scripts/summary.py` builds `summary.json` for the summary page.
- `scripts/build_tiles.sh` turns the result into a single vector-tile file
  (`parcels.pmtiles`) with [tippecanoe](https://github.com/felt/tippecanoe).
- `site/index.html` is a static [MapLibre](https://maplibre.org/) page that reads it,
  over an [OpenFreeMap](https://openfreemap.org/) basemap (free, no API key).
- `.github/workflows/build-map.yml` runs all of this on GitHub Actions and publishes to
  GitHub Pages: on every push to `main`, and monthly to pick up new ownership records.

## Caveats

Owner type is inferred from names and mailing addresses, so it is an estimate:
landlords who receive tax bills at the rental show as owner-occupied, and a few
unusual names may be misread. Private "<address> Land Trust" holdings count as
companies; only community land trusts count as non-profits. Run `python -m unittest discover -s tests` after
changing the rules.
