# Ownership Map — Richmond, VA

An interactive map of every residential lot in Richmond, colored by who owns it:

| Color | Category | Rule |
|---|---|---|
| 🟩 Green | Owner-occupied | Individual (or family trust / estate) whose tax bill is mailed to the property |
| 🟨 Amber | Individual landlord | Individual whose tax bill is mailed somewhere else |
| 🟥 Red | Company-owned | LLC, corporation, partnership, bank, investor |
| ⬜ Gray | Public / non-profit | Government, housing authority, church, land trust, university |

Tap any lot to see the owner, mailing address, and why it got its color. The panel
shows the mix for whatever is on screen and lists the largest company owners
(tap one to outline all of its lots).

## How it works

- **Data:** the City of Richmond GeoHub *Parcels* layer, which joins parcel shapes to the
  City Assessor's ownership records.
- `scripts/build_data.py` downloads the parcels, keeps residential land uses, and
  classifies each owner with the rules in `scripts/classify.py`.
- `scripts/build_tiles.sh` turns the result into a single vector-tile file
  (`parcels.pmtiles`) with [tippecanoe](https://github.com/felt/tippecanoe).
- `site/index.html` is a static [MapLibre](https://maplibre.org/) page that reads it.
- `.github/workflows/build-map.yml` runs all of this on GitHub Actions and publishes to
  GitHub Pages: on every push to `main`, and monthly to pick up new ownership records.

## Caveats

Owner type is inferred from names and mailing addresses, so it is an estimate:
landlords who receive tax bills at the rental show as owner-occupied, and a few
unusual names may be misread. Run `python -m unittest discover -s tests` after
changing the rules.
