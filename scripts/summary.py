"""City-wide summary for site/summary.html: top owners, most valuable lots,
shared mailing addresses and out-of-state owners.

build_summary() takes one dict per residential lot:
  key    owner grouping key (classify.owner_group)
  name   owner name as published
  c      category index (classify.CATEGORIES)
  v      assessed value in dollars, or None
  w      owner location index (build_data.WHERE): 0 at property, 3 out of state, ...
  mail   mailing street line;  city / state  mailing city and state
  id, a, lu, x, y   parcel id, display address, land use, centroid lon / lat
"""

import collections
import statistics

from classify import display_name, normalize_street

TOP_N = 100
TOP_MAIL = 50


def _bbox(lots):
    xs = [r["x"] for r in lots]
    ys = [r["y"] for r in lots]
    return [round(min(xs), 5), round(min(ys), 5), round(max(xs), 5), round(max(ys), 5)]


def _owner_rows(lots_by_key):
    rows = []
    for key, lots in lots_by_key.items():
        names = collections.Counter(display_name(r["name"]) for r in lots)
        cats = collections.Counter(r["c"] for r in lots)
        mails = collections.Counter(
            ", ".join(p for p in (r["mail"], r["city"], r["state"]) if p) for r in lots)
        rows.append({
            "key": key,
            "name": names.most_common(1)[0][0],
            "c": cats.most_common(1)[0][0],
            "lots": len(lots),
            "value": sum(r["v"] or 0 for r in lots),
            "mail": mails.most_common(1)[0][0],
            "bbox": _bbox(lots),
        })
    return rows


def _top(rows, sort_key, cat=None, n=TOP_N):
    pool = [r for r in rows if cat is None or r["c"] == cat]
    # Ties broken by the other measure, then name, so the lists are stable.
    other = "value" if sort_key == "lots" else "lots"
    return sorted(pool, key=lambda r: (-r[sort_key], -r[other], r["name"]))[:n]


def build_summary(records, categories, generated):
    by_key = collections.defaultdict(list)
    for r in records:
        if r["key"]:
            by_key[r["key"]].append(r)
    owners = _owner_rows(by_key)

    # Owner lists: overall and per category, by lot count and by total value.
    lists = {}
    for sort_key in ("lots", "value"):
        lists[sort_key] = {"all": _top(owners, sort_key)}
        for i in range(len(categories)):
            lists[sort_key][str(i)] = _top(owners, sort_key, i)

    # Give every owner an id (g) the map uses to outline all their lots;
    # the largest owners get the smallest numbers.
    ids = {r["key"]: i + 1 for i, r in enumerate(sorted(owners, key=lambda r: (-r["lots"], r["key"])))}
    slim = lambda r: {"g": ids[r["key"]], **{k: r[k] for k in ("name", "c", "lots", "value", "mail", "bbox")}}
    lists = {s: {c: [slim(r) for r in rows] for c, rows in per_cat.items()} for s, per_cat in lists.items()}

    # Category totals.
    cats = []
    for i, name in enumerate(categories):
        lots = [r for r in records if r["c"] == i]
        values = [r["v"] for r in lots if r["v"]]
        cats.append({
            "key": name,
            "lots": len(lots),
            "value": sum(values),
            "median_value": statistics.median(values) if values else 0,
            "out_of_state": sum(1 for r in lots if r["w"] == 3),
            "owners": len({r["key"] for r in lots if r["key"]}),
        })

    # Most valuable single lots.
    priciest = sorted((r for r in records if r["v"]), key=lambda r: -r["v"])[:TOP_N]
    properties = [{"id": r["id"], "a": r["a"], "name": r["name"], "c": r["c"], "value": r["v"],
                   "lu": r["lu"], "x": round(r["x"], 5), "y": round(r["y"], 5)} for r in priciest]

    # Mailing addresses that receive bills for many lots under different owner
    # names: often one investor or manager behind several LLCs.
    by_mail = collections.defaultdict(list)
    for r in records:
        street = normalize_street(r["mail"])
        if r["w"] != 0 and street:
            by_mail[(street, (r["city"] or "").upper())].append(r)
    mail_groups = []
    for (street, city), lots in by_mail.items():
        names = collections.Counter(r["key"] or r["name"] for r in lots)
        if len(names) < 2:
            continue
        shown = {}
        for r in lots:
            shown.setdefault(r["key"] or r["name"], display_name(r["name"]))
        mail_groups.append({
            "mail": ", ".join(p for p in (lots[0]["mail"], lots[0]["city"], lots[0]["state"]) if p),
            "lots": len(lots),
            "owners": len(names),
            "value": sum(r["v"] or 0 for r in lots),
            "names": [shown[k] for k, _ in names.most_common(4)],
            "c": collections.Counter(r["c"] for r in lots).most_common(1)[0][0],
            "bbox": _bbox(lots),
        })
    mail_groups.sort(key=lambda m: (-m["lots"], -m["owners"]))

    # Out-of-state owners by state.
    states = collections.defaultdict(lambda: [0, 0])
    for r in records:
        if r["w"] == 3:
            s = (r["state"] or "?").strip().upper() or "?"
            states[s][0] += 1
            states[s][1] += r["v"] or 0
    states = sorted(({"state": s, "lots": n, "value": v} for s, (n, v) in states.items()),
                    key=lambda s: -s["lots"])

    return {
        "generated": generated,
        "total_lots": len(records),
        "total_value": sum(r["v"] or 0 for r in records),
        "total_owners": len(by_key),
        "categories": cats,
        "owners": lists,
        "properties": properties,
        "mail_groups": mail_groups[:TOP_MAIL],
        "states": states,
    }, ids
