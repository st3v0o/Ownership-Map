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
    r"PUBLIC SCHOOLS", r"UNIVERSITY", r"COLLEGE", r"VCU", r"RECTOR (?:AND|&) VISITORS",
    r"VIRGINIA HOUSING", r"VHDA", r"LAND BANK", r"LAND TRUST",
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
    return bool(pr and mr and pr[0] == mr[0])


def classify(owner_name, property_addr, mail_addr):
    """Return (category, reason)."""
    n = normalize_name(owner_name)
    if not n:
        return INDIVIDUAL_LANDLORD, "No owner name on record"

    m = PUBLIC_NONPROFIT_RX.search(n)
    if m:
        return PUBLIC_NONPROFIT, f'Government / non-profit owner ("{m.group(0)}")'

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
    if same_address(property_addr, mail_addr):
        return OWNER_OCCUPIED, f"{who}; tax bills mailed to this property"
    if not (mail_addr or "").strip():
        return INDIVIDUAL_LANDLORD, f"{who}; no mailing address on record"
    return INDIVIDUAL_LANDLORD, f"{who}; tax bills mailed elsewhere"
