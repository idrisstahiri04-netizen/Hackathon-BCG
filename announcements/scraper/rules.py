"""Rule-based relevance filter and event / severity / crop / evidence extraction.

Every extracted field is backed by a verbatim sentence from the source text
(`evidence[].quote`, with character offsets into the stored text). Nothing is
inferred without a quote; unknown fields stay None.

Severity scale (matches the spec's 0-3 announcement_severity):
  0  no shortage evidence (unrelated, mitigation-only, or reassurance)
  1  early anomaly language: drought / dry spell / poor rains / price rises / pests
  2  confirmed impact: food shortage, hunger, crop failure, livestock deaths,
     or >= 2 independent kinds of level-1 evidence in the same text
  3  emergency: official drought / disaster declaration, famine, starvation
The fusion model must still cap text-only evidence at level 1 (spec, risks table).
"""
import re
from dataclasses import dataclass, asdict

I = re.IGNORECASE

# ---------------------------------------------------------------- relevance
STRONG_TERMS = [
    r"drought", r"famine", r"food (?:in)?security", r"food shortages?", r"hunger", r"starv\w+", r"relief food",
    r"crop failure", r"failed rains", r"poor rains", r"below[- ]normal rain\w*", r"livestock deaths?",
    r"el ni[nñ]o", r"la ni[nñ]a", r"\bNDMA\b", r"food prices?", r"(?:maize|unga) (?:flour )?prices?", r"food aid",
    r"fertili[sz]ers?", r"locusts?", r"armyworm", r"harvests?", r"yields?", r"dry spell", r"water shortage",
    r"pasture", r"strategic food reserve", r"\bNCPB\b", r"food basket", r"food production",
]
WEAK_TERMS = [
    r"maize", r"wheat", r"\brice\b", r"beans", r"sorghum", r"millet", r"cassava", r"potato(?:es)?", r"farmers?",
    r"agricultur\w*", r"\bcrops?\b", r"livestock", r"irrigation", r"\bfood\b", r"rainfall", r"\brains\b",
    r"subsid\w+", r"\bseeds?\b", r"market prices?", r"imports?", r"value chains?", r"agro\w*",
]
_STRONG = [re.compile(p, I) for p in STRONG_TERMS]
_WEAK = [re.compile(p, I) for p in WEAK_TERMS]


def relevance(title: str, text: str) -> tuple[float, list[str]]:
    score, hits = 0.0, set()
    for pats, w in ((_STRONG, 3.0), (_WEAK, 1.0)):
        for p in pats:
            nb = len(p.findall(text or ""))
            nt = len(p.findall(title or ""))
            if nb or nt:
                hits.add(p.pattern)
                score += w * (min(nb, 5) ** 0.5) + 2 * w * min(nt, 1)
    return round(score, 1), sorted(hits)


RELEVANCE_THRESHOLD = 8.0

# ---------------------------------------------------------------- events
FOOD = (r"(?:food(?:stuffs?)?|maize(?:\s+flour)?|unga|flour|beans|rice|wheat|sugar|cereals?|grains?|milk"
        r"|cooking\s+oil|bread|potatoes|vegetables|basic\s+commodities)")

# (event_type, polarity, base_severity, regex)
#   polarity: shortage | mitigation | reassurance
EVENT_RULES = [
    ("drought_declaration", "shortage", 3,
     r"declar\w*\s+(?:the\s+)?(?:\w+\s+){0,3}(?:drought|famine|hunger)\w*\s+(?:a\s+|as\s+a\s+)?(?:national\s+)?disaster"
     r"|(?:drought|famine|hunger)\w*\s+(?:\w+\s+){0,3}(?:declared|gazetted)\s+(?:a\s+)?(?:national\s+)?disaster"
     r"|declar\w*\s+(?:a\s+)?state\s+of\s+emergency"
     r"|declar\w*\s+(?:a\s+)?(?:national\s+)?(?:drought|food)\s+(?:emergency|disaster)"),
    # "(Catastrophe/Famine (Phase 5)" in IPC scale definitions is not a famine report
    ("famine", "shortage", 3, r"(?<!/)\bfamine\b(?!\s*\(?\s*phase)|\bstarvation\b|\bstarving\b|(?:died|deaths?)\s+(?:of|from|due\s+to)\s+hunger"),
    ("drought_alarm_phase", "shortage", 2, r"\b(?:alarm|emergency)\s+(?:phase|stage)\b|\bsevere\s+drought\b|\bIPC\s+phase\s+[345]\b"),
    ("food_shortage", "shortage", 2,
     r"food\s+shortages?|shortages?\s+of\s+(?:food|maize|unga|flour|grains?|wheat|rice|beans)|food\s+insecur\w+"
     r"|\bhunger\b|in\s+need\s+of\s+(?:relief\s+)?food|acute\s+food|food\s+crisis|food\s+deficit"),
    ("crop_failure", "shortage", 2,
     r"crop\s+failure|crops?\s+(?:have\s+|had\s+)?(?:failed|wither\w*|dried\s+up)|failed\s+harvests?|poor\s+harvests?"
     r"|low\s+yields?|reduced\s+(?:yields?|harvests?)|(?:decline|drop|fall)\s+in\s+(?:\w+\s+)?(?:production|yields?|output)"),
    ("livestock_deaths", "shortage", 2,
     r"livestock\s+deaths?|(?:livestock|cattle|goats|sheep|camels|animals|herds?)\s+(?:have\s+)?(?:died|dying|perish\w*)"
     r"|loss\s+of\s+(?:\d[\d,]*\s+)?(?:livestock|animals|cattle)"),
    ("drought_conditions", "shortage", 1,
     # "drought-resistant", "drought mitigation", ... are not drought conditions
     r"(?<!-)\bdrought\b(?![- ](?:resistant|tolerant|resilien\w*|mitigation|preparedness|management|relief|response"
     r"|interventions?|related|risk|insurance|proof|contingency|early\s+warning))"
     r"|dry\s+spells?|failed\s+rains|poor\s+rains|depressed\s+rain\w*|below[- ]normal\s+rain\w*|prolonged\s+dry"
     r"|water\s+scarcity|water\s+shortages?|lack\s+of\s+pasture|pasture\s+scarcity|(?:delayed|erratic)\s+rains"),
    # food prices only; farm-gate prices of cash crops (coffee, tea) rising is not a shortage signal
    ("price_increase", "shortage", 1,
     rf"(?:prices?|cost)\s+of\s+(?:\w+\s+){{0,2}}{FOOD}\s+(?:\w+\s+){{0,2}}(?:rose|risen|rising|increased?|increasing|soar\w*|skyrocket\w*|shot\s+up|hike\w*|doubled)"
     rf"|(?:rising|high|soaring|skyrocketing|exorbitant)\s+(?:cost\s+of\s+|prices\s+of\s+)?{FOOD}(?:\s+prices)?\b"
     rf"|{FOOD}\s+prices\s+(?:have\s+)?(?:rose|risen|increased|soared|shot\s+up|doubled|skyrocketed)"),
    ("pest_outbreak", "shortage", 1, r"locusts?\s+(?:invasion|swarms?|infestation)|desert\s+locusts?|fall\s+armyworm|quelea|maize\s+lethal\s+necrosis"),
    ("flood_crop_damage", "shortage", 1,
     r"floods?\s+(?:\w+\s+){0,3}(?:destroyed|swept\s+away|damaged|submerged)[^.]{0,80}(?:crops?|farms?|acres|livestock)"),
    # government mitigation / response
    ("relief_distribution", "mitigation", 0,
     r"relief\s+food|distribut\w+\s+(?:of\s+)?(?:\d[\d,]*\s+)?(?:bags\s+of\s+)?(?:relief\s+)?(?:food|maize|rice|beans|foodstuffs?)"
     r"|food\s+aid|cash\s+transfers?|Hunger\s+Safety\s+Net|\bHSNP\b|food\s+rations|water\s+trucking"),
    ("input_subsidy", "mitigation", 0,
     r"subsidi[sz]ed\s+fertili[sz]ers?|fertili[sz]er\s+subsidy|e-?voucher|free\s+(?:certified\s+)?seeds?|subsidy\s+programme"
     r"|distribut\w+\s+(?:of\s+)?(?:\w+\s+){0,3}(?:fertili[sz]ers?|seeds?|seedlings)"),
    ("food_import", "mitigation", 0,
     r"import\w*\s+(?:of\s+)?(?:\d[\d,]*\s+\w+\s+(?:of\s+)?)?(?:duty[- ]free\s+)?(?:maize|wheat|rice|sugar|edible\s+oil)"
     r"|duty[- ]free\s+(?:maize|wheat|rice)"),
    ("strategic_reserve_release", "mitigation", 0, r"strategic\s+food\s+reserve|\bNCPB\b|National\s+Cereals\s+and\s+Produce\s+Board"),
    ("livestock_offtake", "mitigation", 0, r"livestock\s+off-?take"),
    ("policy_announcement", "mitigation", 0, r"\b(?:policy|bill|regulations?|strategy|directive|gazette\s+notice)\b"),
    # reassurance / positive supply news
    ("production_increase", "reassurance", 0,
     r"bumper\s+harvests?|increased?\s+(?:\w+\s+){0,2}(?:production|yields?|harvests?|output)|food\s+surplus|surplus\s+(?:maize|food|grain)"
     r"|adequate\s+food\s+(?:stocks?|supply)|(?:prices?|cost)\s+of\s+(?:\w+\s+){0,3}(?:dropped|dropping|fell|fallen|declined|reduced|decreased)"
     r"|food\s+secure\b|self[- ]sufficien\w+"),
]
_EVENTS = [(e, pol, sev, re.compile(rx, I)) for e, pol, sev, rx in EVENT_RULES]

NEGATION = re.compile(
    r"\b(?:no|not|never|nor|without|dismiss\w*|den(?:y|ied|ies)|dispel\w*|unfounded|rule[sd]?\s+out|ruled\s+out"
    r"|avert\w*|prevent\w*|avoid\w*|end(?:ing|ed)?|eradicat\w*|eliminat\w*|zero|free(?:dom)?\s+from|combat\w*"
    r"|fight\w*\s+against|overcome|confront\w*|challenges?\s+of|tackl\w*)\b",
    I,
)
# shortage language about other countries / the whole continent is not a Kenyan district signal
FOREIGN = re.compile(
    r"\b(?:Sudan|Somalia|Ethiopia|Uganda|Tanzania|Rwanda|Burundi|DRC|Congo|Gaza|Ukraine|Yemen|Afghanistan|Haiti|Malawi"
    r"|Zambia|Zimbabwe|Mozambique|Madagascar|Nigeria|Mali|Niger|Chad|Sahel|Syria|Lebanon|continent|Africans?|the\s+world"
    r"|globally|global)\b")
KENYA_CTX = re.compile(r"\b(?:Kenya\w*|count(?:y|ies)|sub-county|our\s+country)\b", I)
FORECAST = re.compile(r"\b(?:expected|forecast\w*|predict\w*|likely|projected|anticipat\w*|outlook|warn\w*|may|could|risk\s+of)\b", I)
YEAR = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")

CROPS = {
    "maize": r"maize|\bunga\b|corn\b", "wheat": r"wheat", "rice": r"\brice\b|paddy", "beans": r"\bbeans\b",
    "sorghum": r"sorghum", "millet": r"millet", "cassava": r"cassava", "potatoes": r"potato(?:es)?",
    "green_grams": r"green\s+grams|ndengu", "cowpeas": r"cowpeas?", "sugar": r"sugar(?:cane)?", "tea": r"\btea\b",
    "coffee": r"coffee", "milk": r"\bmilk\b|dairy", "livestock": r"livestock|cattle|goats|camels|sheep",
    "vegetables": r"vegetables", "avocado": r"avocados?", "macadamia": r"macadamia", "edible_oil": r"edible\s+oils?",
    "pyrethrum": r"pyrethrum", "cotton": r"cotton", "fish": r"\bfish\b|aquaculture",
}
_CROPS = {k: re.compile(v, I) for k, v in CROPS.items()}
STAPLES = {"maize", "wheat", "rice", "beans", "sorghum", "millet", "cassava", "potatoes", "green_grams", "cowpeas", "milk", "livestock"}

# sentence = run of chars up to . ! ? or newline; a "." inside numbers (2.5 million) or after common
# abbreviations (Dr. Hon. No. 5) does not end a sentence
_SENT = re.compile(
    r"(?:[^.!?\n]|(?<=\d)\.(?=\d)|(?<=\bDr)\.|(?<=\bMr)\.|(?<=\bMrs)\.|(?<=\bMs)\.|(?<=\bHon)\.|(?<=\bProf)\.|(?<=\bNo)\.(?=\s*\d))+"
    r"(?:[.!?]+[\"”’)]*|\n|$)"
)


@dataclass
class Evidence:
    event_type: str
    polarity: str
    severity: int
    quote: str
    start: int
    end: int
    matched: str
    negated: bool
    forecast: bool
    historical: bool
    foreign: bool


def sentences(text: str):
    for m in _SENT.finditer(text):
        s = m.group(0)
        lead = len(s) - len(s.lstrip())
        s2 = s.strip()
        if len(s2) > 15:
            yield m.start() + lead, s2


def extract_events(text: str, title: str, pub_year: int | None) -> list[Evidence]:
    out: list[Evidence] = []
    seen = set()
    for src, offset_base in ((title or "", None), (text or "", 0)):
        for start, sent in sentences(src):
            for etype, pol, sev, rx in _EVENTS:
                m = rx.search(sent)
                if not m:
                    continue
                key = (etype, sent[:80])
                if key in seen:
                    continue
                seen.add(key)
                before = sent[max(0, m.start() - 45):m.start()]
                negated = bool(NEGATION.search(before)) and pol != "mitigation"
                years = [int(y) for y in YEAR.findall(sent)]
                historical = bool(pub_year and years and max(years) < pub_year - 1 and pol == "shortage")
                foreign = pol == "shortage" and bool(FOREIGN.search(sent)) and not KENYA_CTX.search(sent)
                out.append(Evidence(
                    etype, pol, sev, sent,
                    -1 if offset_base is None else start,  # -1 => quote is from the title
                    -1 if offset_base is None else start + len(sent),
                    m.group(0), negated, bool(FORECAST.search(sent)), historical, foreign,
                ))
    return out


def crops_in(text: str) -> dict[str, int]:
    counts = {k: len(p.findall(text)) for k, p in _CROPS.items()}
    return {k: v for k, v in counts.items() if v}


def classify(title: str, text: str, pub_year: int | None) -> dict:
    rel_score, rel_terms = relevance(title, text)
    ev = extract_events(text, title, pub_year)
    live_short = [e for e in ev if e.polarity == "shortage" and not (e.negated or e.historical or e.foreign)]
    mitig = [e for e in ev if e.polarity == "mitigation"]
    reass = [e for e in ev if e.polarity == "reassurance"] + [e for e in ev if e.polarity == "shortage" and e.negated]

    # distinct sentences carrying live shortage evidence (an event stated in the title counts double)
    n_sent = len({e.quote for e in live_short}) + (1 if any(e.start == -1 for e in live_short) else 0)
    # an explicit declaration is strong evidence even when stated once
    weak = 0 < n_sent < 2 and not any(e.event_type == "drought_declaration" for e in live_short)

    is_relevant = rel_score >= RELEVANCE_THRESHOLD or bool(n_sent >= 2 and rel_score >= RELEVANCE_THRESHOLD / 2)

    severity = 0
    if live_short:
        severity = max(e.severity for e in live_short)
        kinds = {e.event_type for e in live_short}
        if severity == 1 and len(kinds) >= 2:
            severity = 2
        # level 3 needs an explicit declaration, or famine language backed by several other sentences
        if severity == 3 and "drought_declaration" not in kinds and n_sent < 3:
            severity = 2
        # only-forecast evidence ("rains expected to be below normal") is an early anomaly, not a confirmed impact
        if all(e.forecast for e in live_short) and severity > 1:
            severity = 1
        # one incidental sentence is not enough to call the document a shortage signal
        if weak:
            severity = min(severity, 1)

    # mitigation-only policy mentions are too generic to classify a document by themselves
    substantive_mitig = [e for e in mitig if e.event_type != "policy_announcement"]
    if not is_relevant:
        signal_class = "unrelated"
        severity = 0
    elif live_short and not weak:
        signal_class = "shortage_signal"
    elif live_short:
        signal_class = "weak_shortage_mention"
    elif substantive_mitig:
        signal_class = "mitigation_only"
    elif reass:
        signal_class = "reassurance"
    else:
        signal_class = "agriculture_general"

    # event types, most severe first
    order = sorted({(e.severity, e.event_type) for e in live_short}, reverse=True)
    event_types = [t for _, t in order] + sorted({e.event_type for e in substantive_mitig}) + sorted({e.event_type for e in reass if e.polarity == "reassurance"})

    # commodity: prefer crops mentioned inside shortage evidence, then the whole doc
    ev_text = " ".join(e.quote for e in live_short) or " ".join(e.quote for e in ev)
    crop_ev = crops_in(ev_text)
    crop_doc = crops_in(f"{title} {text}")
    ranked = sorted(crop_ev, key=lambda k: (-crop_ev[k], k)) or sorted(crop_doc, key=lambda k: (-crop_doc[k], k))
    staples = [c for c in ranked if c in STAPLES]
    commodity = (staples or ranked or [None])[0] if is_relevant else None

    if not is_relevant:
        primary = None
    else:
        primary = event_types[0] if event_types else None

    evidence = sorted(ev, key=lambda e: (e.negated or e.historical or e.foreign, e.polarity != "shortage", -e.severity))
    return {
        "is_relevant": is_relevant,
        "relevance_score": rel_score,
        "relevance_terms": rel_terms,
        "signal_class": signal_class,
        "severity": severity,
        "event_type": primary,
        "event_types": event_types,
        "commodity": commodity,
        "affected_crops": ranked if is_relevant else [],
        "has_mitigation": bool(substantive_mitig),
        "is_forecast": bool(live_short) and all(e.forecast for e in live_short),
        "evidence": [asdict(e) for e in evidence[:40]],
    }


def detect_language(text: str) -> str | None:
    words = re.findall(r"[a-z]+", (text or "").lower())[:600]
    if len(words) < 20:
        return None
    sw = {"na", "ya", "wa", "kwa", "katika", "ni", "za", "la", "cha", "hii", "kuwa", "serikali", "wakulima", "chakula"}
    en = {"the", "and", "of", "to", "in", "is", "for", "that", "with", "on"}
    s, e = sum(w in sw for w in words), sum(w in en for w in words)
    return "sw" if s > e else "en"
