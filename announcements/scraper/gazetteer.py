"""Kenya county / sub-county gazetteer and mention matching.

Counties use the official 001-047 county codes. Sub-counties are the 290
electoral constituencies (which mostly coincide with sub-counties) plus a few
administrative sub-counties common in drought reporting. The list was compiled
manually and should be checked against an authoritative shapefile (e.g. the
geoBoundaries / HDX Kenya ADM2 layer) before production use.

unit_id format follows the spec's style:  KEN  /  KEN.023  /  KEN.023.TURKANA_NORTH
"""
import re
from dataclasses import dataclass

COUNTIES: dict[str, tuple[str, list[str]]] = {
    "001": ("Mombasa", ["Changamwe", "Jomvu", "Kisauni", "Nyali", "Likoni", "Mvita"]),
    "002": ("Kwale", ["Msambweni", "Lunga Lunga", "Matuga", "Kinango"]),
    "003": ("Kilifi", ["Kilifi North", "Kilifi South", "Kaloleni", "Rabai", "Ganze", "Malindi", "Magarini"]),
    "004": ("Tana River", ["Garsen", "Galole", "Bura", "Tana Delta", "Tana North"]),
    "005": ("Lamu", ["Lamu East", "Lamu West"]),
    "006": ("Taita Taveta", ["Taveta", "Wundanyi", "Mwatate", "Voi"]),
    "007": ("Garissa", ["Garissa Township", "Balambala", "Lagdera", "Dadaab", "Fafi", "Ijara", "Hulugho"]),
    "008": ("Wajir", ["Wajir North", "Wajir East", "Tarbaj", "Wajir West", "Eldas", "Wajir South", "Habaswein"]),
    "009": ("Mandera", ["Mandera West", "Banissa", "Mandera North", "Mandera South", "Mandera East", "Lafey", "Kutulo"]),
    "010": ("Marsabit", ["Moyale", "North Horr", "Saku", "Laisamis", "Sololo"]),
    "011": ("Isiolo", ["Isiolo North", "Isiolo South", "Garbatulla", "Merti"]),
    "012": ("Meru", ["Igembe South", "Igembe Central", "Igembe North", "Tigania West", "Tigania East",
                     "North Imenti", "Buuri", "Central Imenti", "South Imenti"]),
    "013": ("Tharaka-Nithi", ["Maara", "Chuka", "Igambang'ombe", "Tharaka"]),
    "014": ("Embu", ["Manyatta", "Runyenjes", "Mbeere South", "Mbeere North"]),
    "015": ("Kitui", ["Mwingi North", "Mwingi West", "Mwingi Central", "Kitui West", "Kitui Rural",
                      "Kitui Central", "Kitui East", "Kitui South", "Mutomo", "Ikutha"]),
    "016": ("Machakos", ["Masinga", "Yatta", "Kangundo", "Matungulu", "Kathiani", "Mavoko", "Machakos Town", "Mwala"]),
    "017": ("Makueni", ["Mbooni", "Kilome", "Kaiti", "Kibwezi West", "Kibwezi East"]),
    "018": ("Nyandarua", ["Kinangop", "Kipipiri", "Ol Kalou", "Ol Joro Orok", "Ndaragwa"]),
    "019": ("Nyeri", ["Tetu", "Kieni", "Mathira", "Othaya", "Mukurweini", "Nyeri Town"]),
    "020": ("Kirinyaga", ["Mwea", "Gichugu", "Ndia", "Kirinyaga Central"]),
    "021": ("Murang'a", ["Kangema", "Mathioya", "Kiharu", "Kigumo", "Maragwa", "Kandara", "Gatanga"]),
    "022": ("Kiambu", ["Gatundu South", "Gatundu North", "Juja", "Thika Town", "Ruiru", "Githunguri",
                       "Kiambaa", "Kabete", "Kikuyu", "Limuru", "Lari"]),
    "023": ("Turkana", ["Turkana North", "Turkana West", "Turkana Central", "Loima", "Turkana South",
                        "Turkana East", "Kibish"]),
    "024": ("West Pokot", ["Kapenguria", "Sigor", "Kacheliba", "Pokot South"]),
    "025": ("Samburu", ["Samburu West", "Samburu North", "Samburu East", "Samburu Central"]),
    "026": ("Trans Nzoia", ["Kwanza", "Endebess", "Saboti", "Kiminini", "Cherangany"]),
    "027": ("Uasin Gishu", ["Soy", "Turbo", "Moiben", "Ainabkoi", "Kapseret", "Kesses"]),
    "028": ("Elgeyo-Marakwet", ["Marakwet East", "Marakwet West", "Keiyo North", "Keiyo South"]),
    "029": ("Nandi", ["Tinderet", "Aldai", "Nandi Hills", "Chesumei", "Emgwen", "Mosop"]),
    "030": ("Baringo", ["Tiaty", "Baringo North", "Baringo Central", "Baringo South", "Mogotio", "Eldama Ravine"]),
    "031": ("Laikipia", ["Laikipia West", "Laikipia East", "Laikipia North"]),
    "032": ("Nakuru", ["Molo", "Njoro", "Naivasha", "Gilgil", "Kuresoi South", "Kuresoi North", "Subukia",
                       "Rongai", "Bahati", "Nakuru Town West", "Nakuru Town East"]),
    "033": ("Narok", ["Kilgoris", "Emurua Dikirr", "Narok North", "Narok East", "Narok South", "Narok West"]),
    "034": ("Kajiado", ["Kajiado North", "Kajiado Central", "Kajiado East", "Kajiado West", "Kajiado South"]),
    "035": ("Kericho", ["Kipkelion East", "Kipkelion West", "Ainamoi", "Bureti", "Belgut", "Sigowet", "Soin"]),
    "036": ("Bomet", ["Sotik", "Chepalungu", "Bomet East", "Bomet Central", "Konoin"]),
    "037": ("Kakamega", ["Lugari", "Likuyani", "Malava", "Lurambi", "Navakholo", "Mumias West", "Mumias East",
                         "Matungu", "Butere", "Khwisero", "Shinyalu", "Ikolomani"]),
    "038": ("Vihiga", ["Sabatia", "Hamisi", "Luanda", "Emuhaya"]),
    "039": ("Bungoma", ["Mt. Elgon", "Mount Elgon", "Sirisia", "Kabuchai", "Bumula", "Kanduyi", "Webuye East",
                        "Webuye West", "Kimilili", "Tongaren"]),
    "040": ("Busia", ["Teso North", "Teso South", "Nambale", "Matayos", "Butula", "Funyula", "Budalangi"]),
    "041": ("Siaya", ["Ugenya", "Ugunja", "Alego Usonga", "Gem", "Bondo", "Rarieda"]),
    "042": ("Kisumu", ["Kisumu East", "Kisumu West", "Kisumu Central", "Seme", "Nyando", "Muhoroni", "Nyakach"]),
    "043": ("Homa Bay", ["Kasipul", "Kabondo Kasipul", "Karachuonyo", "Rangwe", "Homa Bay Town", "Ndhiwa",
                         "Suba North", "Suba South"]),
    "044": ("Migori", ["Rongo", "Awendo", "Suna East", "Suna West", "Uriri", "Nyatike", "Kuria West", "Kuria East"]),
    "045": ("Kisii", ["Bonchari", "South Mugirango", "Bomachoge Borabu", "Bobasi", "Bomachoge Chache",
                      "Nyaribari Masaba", "Nyaribari Chache", "Kitutu Chache North", "Kitutu Chache South"]),
    "046": ("Nyamira", ["Kitutu Masaba", "West Mugirango", "North Mugirango", "Borabu"]),
    "047": ("Nairobi", ["Westlands", "Dagoretti North", "Dagoretti South", "Langata", "Kibra", "Roysambu",
                        "Kasarani", "Ruaraka", "Embakasi South", "Embakasi North", "Embakasi Central",
                        "Embakasi East", "Embakasi West", "Makadara", "Kamukunji", "Starehe", "Mathare"]),
}

# Spelling variants that appear in Kenyan government text.
COUNTY_ALIASES = {
    "Tharaka-Nithi": ["Tharaka Nithi", "Tharaka-Nithi"],
    "Elgeyo-Marakwet": ["Elgeyo Marakwet", "Elgeyo-Marakwet", "Elgeiyo Marakwet"],
    "Murang'a": ["Murang'a", "Murang’a", "Muranga"],
    "Taita Taveta": ["Taita Taveta", "Taita-Taveta"],
    "Homa Bay": ["Homa Bay", "Homabay"],
    "Trans Nzoia": ["Trans Nzoia", "Trans-Nzoia"],
    "Uasin Gishu": ["Uasin Gishu", "Uasin-Gishu"],
}

# Names that are also common English words / generic terms: only accepted
# when their parent county is mentioned in the same document.
AMBIGUOUS_SUBCOUNTIES = {"Gem", "Soy", "Turbo", "Manyatta", "Tharaka", "Chuka", "Kikuyu", "Malindi", "Naivasha",
                         "Voi", "Bura", "Seme", "Lari", "Saku", "Ndia", "Kaiti", "Juja", "Molo", "Luanda"}

ADMIN_WORDS = r"(?:County|county|Sub[- ]?[Cc]ounty|Constituency|constituency|Ward|ward)"
# County names above are spelled exactly as in the dashboard (data/kenya-counties.js) so the two join on name.


@dataclass
class UnitMatch:
    unit_id: str
    level: str  # "county" | "subcounty"
    name: str
    county: str
    mentions: int
    match_score: float
    first_quote: str


def _slug(s: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", s.upper()).strip("_")


def _pattern(names: list[str]) -> re.Pattern:
    alts = "|".join(re.escape(n).replace("'", "['’]?").replace(r"\ ", r"[\s-]+") for n in sorted(names, key=len, reverse=True))
    # case-sensitive on purpose: place names are capitalised, which avoids "soy", "gem", "turbo"...
    return re.compile(rf"(?<![A-Za-z])(?:{alts})(?![A-Za-z])")


_COUNTY_PATTERNS = {
    code: _pattern(COUNTY_ALIASES.get(name, [name]) + [name.upper()])
    for code, (name, _) in COUNTIES.items()
}
_SUB_PATTERNS = [
    (code, sub, _pattern([sub]))
    for code, (cname, subs) in COUNTIES.items()
    for sub in subs
    if sub != cname
]

# KNA/Presidency datelines, e.g. "NAIROBI, Oct 16 (KNA) –" or "Nairobi, 3rd March 2024"
_DATELINE = re.compile(r"^\s*[A-Z][A-Za-z' ]{2,30},\s*(?:\w+\s+\d{1,2}|\d{1,2}\w*\s+\w+)")


def _quote(text: str, start: int, end: int, width: int = 90) -> str:
    a, b = max(0, start - width), min(len(text), end + width)
    return re.sub(r"\s+", " ", text[a:b]).strip()


def match_units(text: str, title: str = "") -> list[UnitMatch]:
    doc = f"{title}\n{text}" if title else text
    dl = _DATELINE.match(text or "")
    dateline_end = dl.end() + len(title) + 1 if dl else -1

    county_hits: dict[str, list[re.Match]] = {}
    for code, pat in _COUNTY_PATTERNS.items():
        hits = list(pat.finditer(doc))
        if hits:
            county_hits[code] = hits

    out: list[UnitMatch] = []
    for code, hits in county_hits.items():
        body_hits = [h for h in hits if h.start() > dateline_end]
        n = len(body_hits)
        with_admin = any(re.match(r"\s+" + ADMIN_WORDS, doc[h.end():h.end() + 20]) for h in hits)
        if n == 0:
            score = 0.2  # only appears in the dateline (place of reporting, not necessarily the place affected)
        else:
            score = min(1.0, 0.5 + 0.1 * n + (0.2 if with_admin else 0))
        h0 = (body_hits or hits)[0]
        out.append(UnitMatch(f"KEN.{code}", "county", COUNTIES[code][0], COUNTIES[code][0],
                             len(hits), round(score, 2), _quote(doc, h0.start(), h0.end())))

    for code, sub, pat in _SUB_PATTERNS:
        hits = list(pat.finditer(doc))
        if not hits:
            continue
        county_present = code in county_hits
        if sub in AMBIGUOUS_SUBCOUNTIES and not county_present:
            continue
        score = (0.8 if county_present else 0.55) + min(0.2, 0.05 * (len(hits) - 1))
        out.append(UnitMatch(f"KEN.{code}.{_slug(sub)}", "subcounty", sub, COUNTIES[code][0],
                             len(hits), round(min(score, 1.0), 2), _quote(doc, hits[0].start(), hits[0].end())))
    out.sort(key=lambda m: (-m.match_score, m.unit_id))
    return out
