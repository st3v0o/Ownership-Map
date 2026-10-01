"""Classify a residential parcel's owner into one of four categories.

  owner_occupied  - an individual (or family trust/estate) whose mailing
                    address matches the property address
  individual_landlord - an individual whose mailing address is elsewhere
  company         - LLCs, corporations, partnerships, banks, investors
  public_nonprofit - government, housing authority, churches, land trusts,
                    universities and other non-profits

Classification is rule based on the owner name and mailing address that the
City Assessor publishes. Each result carries a short human readable reason so
the map can show *why* a lot got its colour.
"""

import difflib
import re

OWNER_OCCUPIED = "owner_occupied"
INDIVIDUAL_LANDLORD = "individual_landlord"
COMPANY = "company"
PUBLIC_NONPROFIT = "public_nonprofit"

CATEGORIES = [OWNER_OCCUPIED, INDIVIDUAL_LANDLORD, COMPANY, PUBLIC_NONPROFIT]


def _rx(words):
    return re.compile(r"(?<![A-Z0-9])(?:" + "|".join(words) + r")(?![A-Z0-9])")


# Checked first: government, housing authorities, religious and charitable
# owners. These would otherwise trip the company patterns ("AUTHORITY",
# "FOUNDATION INC", ...).
PUBLIC_NONPROFIT_RX = _rx([
    r"CITY OF RICHMOND", r"RICHMOND CITY", r"COMMONWEALTH OF VIRGINIA",
    r"COMMONWEALTH OF VA", r"STATE OF VIRGINIA", r"UNITED STATES",
    r"USA", r"U S A", r"SECRETARY OF HOUSING", r"HUD",
    r"FEDERAL NATIONAL MORTGAGE", r"FANNIE MAE", r"FEDERAL HOME LOAN MORTGAGE",
    r"FREDDIE MAC", r"VETERANS AFFAIRS",
    r"COUNTY OF \w+", r"\w+ COUNTY", r"HOUSING AUTHORITY",
    r"REDEVELOPMENT (?:AND|&) HOUSING", r"RRHA", r"SCHOOL BOARD",
    r"PUBLIC SCHOOLS", r"UNIVERSITY", r"UNIV", r"COLLEGE", r"VCU", r"RECTOR (?:AND|&) VISITORS",
    r"VIRGINIA HOUSING", r"VHDA", r"LAND BANK",
    r"COMMUNITY LAND", r"HABITAT FOR HUMANITY", r"CHURCH", r"CHURCHES",
    r"MINISTRY", r"MINISTRIES", r"BAPTIST", r"METHODIST", r"EPISCOPAL",
    r"PRESBYTERIAN", r"CATHOLIC", r"DIOCESE", r"LUTHERAN",
    r"SYNAGOGUE", r"MOSQUE", r"CONGREGATION", r"TABERNACLE",
    r"FOUNDATION", r"CHARITABLE", r"NON ?PROFIT", r"PROJECT HOMES",
    r"BETTER HOUSING COALITION", r"COMMUNITY DEVELOPMENT CORP\w*",
    r"SOUTHSIDE COMMUNITY DEVELOPMENT", r"MAGGIE L WALKER",
])

# Words that mark a business entity.
COMPANY_RX = _rx([
    r"L L C", r"LLC", r"L L P", r"LLP", r"LP", r"PLLC", r"INC", r"INCORPORATED",
    r"CORP", r"CORPORATION", r"CO", r"COMPANY", r"LTD", r"LIMITED",
    r"PARTNERSHIP", r"PARTNERS", r"PTNRS", r"PTNSHP", r"HOLDING", r"HOLDINGS",
    r"PROPERTY", r"PROPERTIES", r"PROP", r"PROPS", r"INVESTMENT", r"INVESTMENTS",
    r"INVESTORS?", r"INVEST", r"REALTY", r"REAL ESTATE", r"CAPITAL", r"VENTURES?",
    r"GROUP", r"ENTERPRISES?", r"DEVELOPMENT", r"DEVELOPERS?", r"BUILDERS?",
    r"CONSTRUCTION", r"HOMES", r"RENTALS?", r"RENTAL HOMES", r"LEASING",
    r"MANAGEMENT", r"MGMT", r"ASSOCIATES", r"ASSOC", r"FUND", r"FUNDING",
    r"BANK", r"BANCORP", r"MORTGAGE", r"FINANCIAL", r"LENDING", r"LOANS?",
    r"SAVINGS", r"CREDIT UNION", r"NATIONAL ASSOCIATION", r"NATL ASSN",
    r"FSB", r"REIT", r"SFR", r"BORROWER", r"ASSET", r"ASSETS",
    r"OWNER", r"OPCO", r"PROPCO", r"SERIES", r"SOLUTIONS", r"SERVICES?",
    r"APARTMENTS?", r"APTS?", r"VILLAGE", r"COMMONS", r"RESIDENTIAL",
    r"HOUSING", r"ACQUISITIONS?", r"EQUITY", r"EQUITIES", r"TRUST COMPANY",
    r"TRUST CO", r"ASSOCIATION", r"ASSN", r"CONDOMINIUM", r"CONDO",
    r"HOA", r"OWNERS ASSOC\w*",
])

LEGAL_SUFFIXES = {"LLC", "LLP", "LP", "PLLC", "INC", "INCORPORATED", "CORP",
                  "CORPORATION", "LTD", "LIMITED", "CO", "COMPANY"}

# Person-held vehicles: these count as individuals, not companies.
PERSONAL_HOLDING_RX = _rx([
    r"TRUST", r"TRUSTEE", r"TRUSTEES", r"TR", r"TRS", r"TTEE", r"TTEES",
    r"REVOCABLE", r"REV", r"LIVING", r"IRREVOCABLE", r"FAMILY",
    r"ESTATE", r"EST", r"ESTATE OF", r"HEIRS", r"ET AL", r"ETAL", r"ET UX",
    r"ETUX", r"LIFE ESTATE", r"LIFE EST", r"EXECUTOR", r"EXECUTRIX",
    r"ADMINISTRATOR", r"GUARDIAN",
])


# "C/O <agent>" and "ATTN <person>" name who receives the bill, not the owner.
CARE_OF_RX = re.compile(r"\s*(?:\bC\s*/\s*O\b|\s/\s*CO\b|\bC O\b|\bCARE OF\b|\bATTN\b).*$")

# Richmond neighborhood names that contain non-profit words.
NEIGHBORHOOD_RX = re.compile(
    r"\b(?:CHURCH HILL|COLLEGE (?:PARK|HILL|HEIGHTS)|UNIVERSITY (?:HEIGHTS|PARK)|"
    r"FOUNDATION (?:HILL|PARK))\b")

# Non-profit words that a private company can also carry in its name. With a
# strong business marker (LLC, LP, REALTY, ...) they don't make it non-profit.
WEAK_NONPROFIT = {"UNIVERSITY", "UNIV", "COLLEGE", "CHURCH", "CHURCHES", "FOUNDATION",
                  "LAND BANK", "COMMUNITY LAND", "CONGREGATION"}
STRONG_COMPANY_RX = _rx([
    r"L L C", r"LLC", r"L L P", r"LLP", r"LP", r"PLLC", r"LTD", r"REALTY",
    r"VENTURES?", r"INVESTMENTS?", r"INVESTORS?", r"CAPITAL", r"PROPERTIES",
    r"HOLDINGS?", r"RENTALS?", r"DEVELOPERS?", r"BUILDERS?",
])

# In Richmond, "<anything> LAND TRUST" is almost always a private holding
# trust named after the property ("205 E 12TH ST LAND TRUST", "CRAFTON LAND
# TRUST TRUSTEE") that keeps the investor anonymous. Only community land
# trusts (Maggie Walker Community Land Trust) are non-profits.
PRIVATE_LAND_TRUST_RX = re.compile(r"\bLAND TRUST\b")
COMMUNITY_LAND_TRUST_RX = re.compile(r"\bCOMMUNITY LAND\b")


def strip_care_of(name):
    """Drop a trailing "C/O ..." or "ATTN ..." agent from an owner name."""
    return CARE_OF_RX.sub("", (name or "").upper()).strip()


def display_name(name):
    """Owner name as published, minus any trailing "C/O ..." agent."""
    m = CARE_OF_RX.search((name or "").upper())
    return (name[:m.start()] if m else name or "").strip()


def owner_key(name):
    """Name used to group one owner's parcels (care-of agent removed)."""
    return normalize_name(strip_care_of(name))


def normalize_name(name):
    s = (name or "").upper()
    s = s.replace("&", " AND ")
    s = re.sub(r"[.,'\"`]", "", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


STREET_SUFFIXES = {
    "STREET": "ST", "AVENUE": "AVE", "AV": "AVE", "ROAD": "RD", "DRIVE": "DR",
    "LANE": "LN", "COURT": "CT", "PLACE": "PL", "BOULEVARD": "BLVD",
    "TERRACE": "TER", "CIRCLE": "CIR", "PARKWAY": "PKWY", "HIGHWAY": "HWY",
    "TURNPIKE": "TPKE", "SQUARE": "SQ", "TRAIL": "TRL", "WAY": "WAY",
    "ALLEY": "ALY", "CRESCENT": "CRES", "POINT": "PT", "PIKE": "PIKE",
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
    "FIRST": "1ST", "SECOND": "2ND", "THIRD": "3RD", "FOURTH": "4TH",
    "FIFTH": "5TH", "SIXTH": "6TH", "SEVENTH": "7TH", "EIGHTH": "8TH",
    "NINTH": "9TH", "TENTH": "10TH",
}

UNIT_RX = re.compile(r"\b(?:APT|UNIT|STE|SUITE|NO|#|BLDG|FL|FLOOR|RM|ROOM|LOT)\b.*$")


def normalize_street(addr):
    """Reduce an address line to 'NUMBER STREET-WORDS' for comparison."""
    s = (addr or "").upper()
    s = s.replace("#", " # ")
    s = re.sub(r"[.,]", " ", s)
    s = UNIT_RX.sub("", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    words = [STREET_SUFFIXES.get(w, w) for w in s.split()]
    return " ".join(words).strip()


def same_address(property_addr, mail_addr):
    """True when the owner's mailing address is the property itself."""
    p = normalize_street(property_addr)
    m = normalize_street(mail_addr)
    if not p or not m:
        return False
    if p == m:
        return True
    pw, mw = p.split(), m.split()
    # Same house number and the first street word matches
    # ("123 N MAIN ST" vs "123 MAIN ST", "123 MAIN" vs "123 MAIN ST").
    if pw[0] != mw[0] or not pw[0][:1].isdigit():
        return False
    dirs = {"N", "S", "E", "W"}
    pr = [w for w in pw[1:] if w not in dirs]
    mr = [w for w in mw[1:] if w not in dirs]
    if not (pr and mr):
        return False
    # Allow small misspellings in the mailing address ("BOULDERS CREEK" for
    # "BOULDER CREEK", "WAKFIELD" for "WAKEFIELD"), but not numbered streets.
    a, b = pr[0], mr[0]
    if a == b:
        return True
    if a[:1].isdigit() or b[:1].isdigit() or min(len(a), len(b)) < 5 or abs(len(a) - len(b)) > 1:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


PO_BOX_RX = re.compile(r"\b(?:P\s*O\s*BOX|POST OFFICE BOX|BOX|PMB)\b")


def same_house_number(bldg_no, mail_addr, mail_city):
    """Fallback when only the property's house number is known: the mailing
    address starts with that number, is in Richmond and is not a PO box."""
    m = normalize_street(mail_addr)
    b = (bldg_no or "").strip().upper()
    if not b or not m or PO_BOX_RX.search(m):
        return False
    if (mail_city or "").strip().upper() != "RICHMOND":
        return False
    return m.split()[0] == b.split()[0]


def classify(owner_name, property_addr, mail_addr, bldg_no=None, mail_city=None):
    """Return (category, reason).

    property_addr is one street address or a list of them (a parcel can have
    several). When none is known, bldg_no and mail_city drive a house-number
    fallback for owner-occupied detection.
    """
    n = owner_key(owner_name)
    if not n:
        return INDIVIDUAL_LANDLORD, "No owner name on record"

    if PRIVATE_LAND_TRUST_RX.search(n) and not COMMUNITY_LAND_TRUST_RX.search(n):
        return COMPANY, "Private land trust (owner kept anonymous)"

    np_hits = {h.group(0) for h in PUBLIC_NONPROFIT_RX.finditer(NEIGHBORHOOD_RX.sub(" ", n))}
    if np_hits and not (np_hits <= WEAK_NONPROFIT and STRONG_COMPANY_RX.search(n)):
        m = sorted(np_hits, key=lambda h: (h in WEAK_NONPROFIT, h))[0]
        return PUBLIC_NONPROFIT, f'Government / non-profit owner ("{m}")'

    personal = PERSONAL_HOLDING_RX.search(n)
    hits = [h.group(0) for h in COMPANY_RX.finditer(n)]
    # "CO" next to a trust is a co-trustee ("SMITH JOHN CO TRUSTEE"), not a company.
    if personal:
        hits = [h for h in hits if h != "CO"]
    if hits:
        # Prefer a legal-entity suffix (LLC, INC, ...) when explaining the call.
        legal = [h for h in hits if h.replace(" ", "") in LEGAL_SUFFIXES]
        return COMPANY, f'Business owner ("{(legal or hits)[0]}" in name)'

    who = "Family trust / estate" if personal else "Individual owner"
    addrs = [property_addr] if isinstance(property_addr, str) else list(property_addr or [])
    addrs = [a for a in addrs if (a or "").strip()]
    if any(same_address(a, mail_addr) for a in addrs):
        return OWNER_OCCUPIED, f"{who}; tax bills mailed to this property"
    if not addrs and same_house_number(bldg_no, mail_addr, mail_city):
        return OWNER_OCCUPIED, f"{who}; tax bills mailed to this house number"
    if not (mail_addr or "").strip():
        return INDIVIDUAL_LANDLORD, f"{who}; no mailing address on record"
    return INDIVIDUAL_LANDLORD, f"{who}; tax bills mailed elsewhere"
