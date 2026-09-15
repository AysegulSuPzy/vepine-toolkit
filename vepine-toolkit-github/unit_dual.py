#!/usr/bin/env python3
"""unit_dual.py NN [NN ...] — dual units in the Specifications list (added 2026-09-06, blr-batch26, user decision).

A measurement the source gives in ONE system only gets the other system as well — IMPERIAL FIRST, metric in parentheses,
whichever the source wrote (user decision 2026-09-06: a US shopper who sees cm first reads the listing as imported) — inside the
<h3>Specifications</h3> list items of final/dNN.json and nowhere else: metric -> imperial (cm/mm/m -> in/ft, g/kg -> oz/lb,
ml/l -> fl oz, °C -> °F) and imperial -> metric. A conversion is arithmetic, not an invented fact; the source figure stays
exactly as written and first. Items that already carry both systems ("15.2cm/5.98in", '75cm x 45cm (30" x 18")') are left
alone; electrical units, hours, lumens, mAh, percentages, sizes without a length unit are untouched. Idempotent — a re-run
changes nothing. Runs inside gate.py before value-check (the source value is still present verbatim, so value_check and
spec_cover are unaffected). Rounding: 1 decimal for in/ft/oz/lb/fl oz/cm/kg, integers for °F, °C, g, ml; trailing ".0" dropped.

2026-09-11 (user decision, ddl2 pregnancy pillow: the comparison table read "155 x 75 x 60 cm" on a US-only store):
the BUDGETED elements — where a "(155 cm)" parenthesis does not fit — no longer keep metric at all. `imperial_only()`
converts metric -> imperial and DROPS the metric figure: H2, the five benefit bullets, FAQ questions (this script),
comparison rows / name (compare_build.py), fit lines (fit_build.py). The metric source figure still stands verbatim in
the Specifications list (dual, above), so value_check / spec_cover still find it. Nothing metric is ever shown alone.
"""
import json, re, sys, html

METRIC = {"mm": ("in", 0.0393701), "cm": ("in", 0.393701), "m": ("ft", 3.28084), "g": ("oz", 0.035274), "kg": ("lb", 2.20462),
          "ml": ("fl oz", 0.033814), "l": ("fl oz", 33.814)}
IMPERIAL = {"in": ("cm", 2.54), "inch": ("cm", 2.54), "inches": ("cm", 2.54), '"': ("cm", 2.54), "ft": ("m", 0.3048), "feet": ("m", 0.3048),
            "oz": ("g", 28.3495), "lb": ("kg", 0.453592), "lbs": ("kg", 0.453592), "fl oz": ("ml", 29.5735)}
# 2026-09-15 (STR-DUB-2-batch10 p06 / p16 / p27): the spelled-out metric names are matched too. A source that writes
# "5000 meters" instead of "5000 m" fell straight through this regex and reached the final metric-only, while the SAME
# value written "800m" on the same product was converted — the one-line proof that the abbreviation was the only form read.
# The long names come FIRST: alternation is first-match, so with "m|…|meters" the bare "m" of "meters" would win and the
# trailing "eters" would fail the (?![\w/]) lookahead.
SPELLED_METRIC = r'millimet(?:er|re)s?|centimet(?:er|re)s?|kilograms?|metres?|meters?|grams?|lit(?:er|re)s?'
UNIT_RE = r'(' + SPELLED_METRIC + r'|fl\.? ?oz|inch(?:es)?|feet|mm|cm|kg|ml|oz|lbs|lb|ft|in|m|g|l|")'
# spelled name -> canonical symbol, applied in _skip() before the METRIC / IMPERIAL lookup
SPELLED = {"millimeter": "mm", "millimeters": "mm", "millimetre": "mm", "millimetres": "mm",
           "centimeter": "cm", "centimeters": "cm", "centimetre": "cm", "centimetres": "cm",
           "meter": "m", "meters": "m", "metre": "m", "metres": "m",
           "kilogram": "kg", "kilograms": "kg", "gram": "g", "grams": "g",
           "liter": "l", "liters": "l", "litre": "l", "litres": "l"}
NUM = r'(?:(?<!\d)-)?\d+(?:[.,]\d+)?'
# a run of numbers joined by x / × / * / - / to, then one unit: "28.8 * 27.8 * 0.3 cm", "5-7 in", "145 g"
# 2026-09-07 (STR-DUB-2-batch3): an inner unit is only a unit when a separator (x / - / to) follows it — without the lookahead
# "49mm" backtracked into run "49m" + unit "m" (-> 160.8 ft) and "250ml" into "250m" + "l".
MEAS = re.compile(r'(?<![\w.-])(' + NUM + r'(?:\s*' + UNIT_RE + r'(?=\s*(?:x|×|\*|-|–|to)\b|\s*(?:x|×|\*|-|–)))?(?:\s*(?:x|×|\*|-|–|to)\s*' + NUM + r'(?:\s*' + UNIT_RE + r'(?=\s*(?:x|×|\*|-|–|to)\b|\s*(?:x|×|\*|-|–)))?)*)\s*(?P<unit>' + UNIT_RE + r')(?![\w/])', re.I)
TEMP = re.compile(r'(?<![\w.-])(' + NUM + r'(?:\s*(?:-|–|to|/|,)\s*' + NUM + r'(?:\s*°\s*[CF]\b)?)*)\s*°\s*([CF])\b')
INT_UNITS = {"°F", "°C", "g", "ml"}
# 2026-09-15 (review): for a VOLUME or WEIGHT unit a leading "N x" is a pack count, never a dimension — only length units
# form a dimension run. "Pack of 2 x 500 ml" was read as the run 2 x 500 and both figures were converted (-> "0.1 x 16.9
# fl oz"); the count is now kept and only the value converted -> "2 x 16.9 fl oz (2 x 500 ml)".
COUNT_UNITS = {"ml", "l", "g", "kg", "oz", "lb", "lbs", "fl oz"}
COUNT_RUN = re.compile(r'^\s*(\d+)\s*[x×*]\s*(.+)$')
# 2026-09-15 (review): an axis label after the unit ("9.45 in L x 7 in W") took the conversion between the figure and its
# label -> "9.45 in (24 cm) L". The parenthesis belongs after the label.
AXIS_PAREN = re.compile(r'\s*\(([^()]{1,40})\)\s+([LWHD])(?![A-Za-z])')

def _num(s):
    # A comma followed by exactly three digits is a thousands separator ("3,280 feet", "1,500 ml"),
    # not a European decimal comma ("1,5 cm"). Before this (STR-DUB-2-batch5, 2026-09-08) every
    # figure written with a thousands comma was parsed as a decimal: "3,280 feet" -> 3.28 -> "(1 m)"
    # reached the live copy of p40 twice.
    s = s.strip()
    if re.fullmatch(r'-?\d{1,3}(?:,\d{3})+', s):
        return float(s.replace(",", ""))
    return float(s.replace(",", "."))


def fmt(v, unit):
    s = f"{v:.0f}" if unit in INT_UNITS else f"{v:.1f}".rstrip("0").rstrip(".")
    return s

def convert_run(numrun, factor, unit):
    numrun = re.sub(r'\s*' + UNIT_RE + r'(?=\s*(?:x|×|\*|-|–|to)\b|\s*$)', '', numrun, flags=re.I)   # drop repeated inner units
    return re.sub(NUM, lambda m: fmt(_num(m.group(0)) * factor, unit), numrun)

def has_both(text):
    t = text.lower()
    metric = re.search(r'\d\s*' + MET_U + r'\b', t); imp = re.search(r'\d\s*(?:in|inch|inches|ft|feet|oz|lb|lbs|")', t)
    if '°' in t and re.search(r'°\s*c', t) and re.search(r'°\s*f', t): return True
    return bool(metric and imp)

LIQUID = re.compile(r'\b(capacity|tank|volume|spray|water|liquid|reservoir|mist|output|fill)\b', re.I)
# 2026-09-09 (STR-DUB-2-batch9 p36, found during the dimension-image re-run): "Waterproof Rating: 3000mm" is a hydrostatic-head
# PRESSURE rating written in mm of water column, not a length — it reached the live page as "118.1 in (3000mm)". A mm/m figure
# whose item name, the 30 characters before it or the 20 after it name a waterproof / water-column / hydrostatic rating is left as written.
RATING = re.compile(r'\b(waterproof(?:ness)?|water[- ]?(?:resist(?:ant|ance)|column|proof)|hydrostatic|hh\b|rating|pressure)\b', re.I)

ENGINE = re.compile(r'\b(engines?|displacement|cylinders?|diesel|gasoline|petrol|motor)\b', re.I)
# 2026-09-15 (STR-DUB-2-batch10 p07 / p08): a BAG capacity is written in litres worldwide, the US included — it is not a
# liquid volume. "The main compartment holds a 3.5L capacity" reached the final as "118.3 fl oz (3.5L)" and a 50L pack as
# "1690.7 fl oz backpack". Same class as the ENGINE exception above. An l/ml figure in a text that names a pack, bag or
# compartment is left as written — unless that text also names a tank, reservoir, bladder or bottle, where the litres
# really are a liquid (a hydration pack). Deliberately NOT keyed on "water": "water-resistant fabric" sits in almost
# every backpack description and would cancel the exception.
# "capacity" is deliberately NOT a bag word (review, 2026-09-15): a water bottle also says "Capacity: 1 L" and there the
# litres really are a liquid. The case it was meant to cover — a fit line or comparison row converted on its own, with no
# product around it ("the 50 liter capacity has room for it") — is covered by the PRODUCT-LEVEL flag below instead.
# "pack of" / "packs of" is a COUNT phrase ("Pack of 2 x 500 ml"), never the bag itself — hence the lookahead.
BAG = re.compile(r'\b(?:backpacks?|rucksacks?|daypacks?|knapsacks?|packs?(?!\s+of\b)|packable|bags?|luggage|suitcases?|duffels?|duffles?|totes?|pouch(?:es)?|sacks?|compartments?|carry[- ]?ons?|holdalls?)\b', re.I)
# "water" counts as a liquid word only when it is not "water-resistant" / "waterproof" / "water-repellent" — those sit in
# almost every backpack description and would cancel the exception on exactly the products it exists for.
BAG_LIQUID = re.compile(r'\b(?:tanks?|reservoirs?|bladders?|hydration|bottles?|jugs?|pitchers?|kettles?|flasks?|thermos|humidifiers?|diffusers?|steamers?|sprayers?|dispensers?|coolers?|watering|mist|spray|drink\w*|beverages?|coffee|tea'
                        r'|water(?!\s*-?\s*(?:resistant|resistance|proof|repellent|repellency)))\b', re.I)
# 2026-09-12 (DDL2-Batch3 p17): a temperature RANGE the source already wrote in both scales — "-20°F to 70°F / -29°C to 21°C" —
# was converted piecewise into "-20°F (-29°C) to 70°F / -29°C to 70°F (21°C)". A text that already carries both °C and °F is
# never temperature-converted again (dual); imperial_only drops the "/ …°C" half of such a range instead (DROP_SLASH_T).
def has_both_temp(text): return bool(re.search(r'°\s*C\b', text) and re.search(r'°\s*F\b', text))

# Product-level bag flag (2026-09-15, review). When the PRODUCT itself is a bag — its title, productType, H2 or bullets say
# so — every LITRE figure in its copy is a pack capacity, including the spec line "Volume: 3.5 liters" that carries no bag
# word of its own and the fit line converted in isolation by fit_build.py. Litres only: a 500 ml bottle sold with a backpack
# is still a liquid, and an item that names a tank / bottle / mist of its own is still converted.
PRODUCT_BAG = False
def looks_like_bag(text):
    text = text or ""
    return bool(BAG.search(text)) and not BAG_LIQUID.search(text)
def set_product_bag(flag):
    """Called by process() from the H2 + bullets, and by compare_build.py / fit_build.py from the product title, before a
    block is rendered on its own. Module-level because each of those scripts runs in its own process."""
    global PRODUCT_BAG; PRODUCT_BAG = bool(flag)

def adjacent_dual(text, start, end):
    """True when this measurement already sits next to its conversion: followed by "(" or "/" + a number, or itself
    inside a "(" / "/" conversion — '75cm x 45cm (30" x 18")', '15.2cm/5.98in', 'Weight: 145g (5.1 oz)'."""
    # 2026-09-15 (review): an axis label may sit between the figure and its conversion — "9.45 in L (24 cm)" — because the
    # parenthesis is moved after the label. Without this the second pass converts the figure again and doubles the bracket.
    after = text[end:end + 10]; before = text[max(0, start - 3):start]
    return bool(re.match(r'\s*(?:[LWHD]\b\s*)?(?:\(|/)\s*-?\d', after) or re.search(r'(?:\(|/)\s*$', before))

MET_U = r'(?:' + SPELLED_METRIC + r'|mm|cm|kg|ml|m|g|l)'   # 2026-09-15: spelled names first, same reason as UNIT_RE
MET_RUN = r'-?[\d.,]+(?:\s*' + MET_U + r')?(?:\s*(?:x|×|\*|-|–|to|/)\s*-?[\d.,]+(?:\s*' + MET_U + r')?)*\s*' + MET_U
IMP_RUN = r'-?[\d.,]+(?:\s*(?:in|inch(?:es)?|"|ft|feet|oz|lbs?|fl oz))?(?:\s*(?:x|×|\*|-|–|to|/)\s*-?[\d.,]+(?:\s*(?:in|inch(?:es)?|"|ft|feet|oz|lbs?|fl oz))?)*\s*(?:in|inch(?:es)?|"|ft|feet|oz|lbs?|fl oz)'
SWAP = re.compile(r'(?<![\w.-])(' + MET_RUN + r')\s*\((' + IMP_RUN + r')\)', re.I)
SWAP_T = re.compile(r'(?<![\w.-])(-?[\d.,]+(?:\s*(?:-|–|to|/|,)\s*-?[\d.,]+(?:\s*°\s*C)?)*\s*°\s*C)\s*\((-?[\d.,]+(?:\s*(?:-|–|to|/|,)\s*-?[\d.,]+(?:\s*°\s*F)?)*\s*°\s*F)\)')

SWAP_SLASH = re.compile(r'(?<![\w.-])(-?[\d.,]+(?:\s*[x×]\s*[\d.,]+)*\s*' + MET_U + r')\s*/\s*(-?[\d.,]+(?:\s*[x×]\s*[\d.,]+)*\s*(?:in|inch(?:es)?|"|ft|feet|oz|lbs?|fl oz))(?![\w])', re.I)

def imperial_first(text):
    text = SWAP.sub(lambda m: f"{m.group(2)} ({m.group(1)})", text)
    text = SWAP_SLASH.sub(lambda m: f"{m.group(2)}/{m.group(1)}", text)   # "15.2cm/5.98in" -> "5.98in/15.2cm"
    return SWAP_T.sub(lambda m: f"{m.group(2)} ({m.group(1)})", text)

def _skip(item, m, liquid=False, bagctx=None):
    """Shared exemptions: 4G/5G, 'L' as a length label, waterproof mm ratings. Returns (skip, unit)."""
    if m.group("unit") == "G": return True, None   # 2026-09-07 (STR-DUB-2-batch3): "4G" / "5G" is a network generation, not grams — grams are written lowercase
    # 2026-09-07: "9.45 in L" / "23.99 cm L" — L is the length label after a unit, not litres. 2026-09-15 (review): the run
    # separator x is a letter too, so "3 x 1.5 L" (three 1.5-litre bottles) was wrongly read as a length label and skipped.
    if m.group("unit") == "L" and re.search(r'[a-zA-Z"]', re.sub(r'[x×*]', '', m.group(1))): return True, None
    unit = m.group("unit").lower().replace(".", "").replace(" ", "")
    unit = SPELLED.get(unit, unit)   # 2026-09-15: "5000 meters" -> "m", "50 liters" -> "l" before any lookup below
    # 2026-09-15: pack / bag / compartment litres are not a liquid volume (see BAG above)
    bc = bagctx if bagctx is not None else item
    if unit in ("l", "ml") and BAG.search(bc) and not BAG_LIQUID.search(bc): return True, None
    if unit == "l" and PRODUCT_BAG and not BAG_LIQUID.search(bc): return True, None
    # 2026-09-12 (DDL2-Batch3 p17): "12V gasoline engines up to 10.0 L" is engine DISPLACEMENT, written in litres in the US too —
    # it reached the final as "338.1 fl oz (10.0 L)". An l/ml figure whose 40 characters before or 25 after name an engine is left as written.
    if unit in ("l", "ml") and (ENGINE.search(item[max(0, m.start() - 40):m.start()]) or ENGINE.search(item[m.end():m.end() + 25])): return True, None
    if unit in ("mm", "m") and (RATING.search(item.split(":")[0] if ":" in item else "") or RATING.search(item[max(0, m.start() - 30):m.start()]) or RATING.search(item[m.end():m.end() + 20])): return True, None
    if unit == "floz": unit = "fl oz"
    if unit == "oz" and liquid: unit = "fl oz"      # a tank / capacity in oz is fluid ounces -> ml
    return False, unit

def dual(item, ctx=""):
    liquid = bool(LIQUID.search(item.split(":")[0] if ":" in item else item)) or bool(re.search(r'\d\s*(?:fl\.? ?)?oz\s+(?:water\s+)?(?:tank|reservoir|capacity|bottle)', item, re.I))   # 2026-09-07: "60 oz tank" in prose/FAQ is fluid ounces even when the item has a Name: prefix
    def rep(m):
        if adjacent_dual(item, m.start(), m.end()): return m.group(0)
        skip, unit = _skip(item, m, liquid, (item + " " + ctx) if ctx else item)
        if skip: return m.group(0)
        run = m.group(1)
        if unit in METRIC: tu, f = METRIC[unit]
        elif unit in IMPERIAL: tu, f = IMPERIAL[unit]
        else: return m.group(0)
        cr = COUNT_RUN.match(run)
        if unit in COUNT_UNITS and cr:   # 2026-09-15: "2 x 500 ml" — keep the pack count, convert the value
            conv = f"{cr.group(1)} x {convert_run(cr.group(2), f, tu)} {tu}"
        else:
            conv = f"{convert_run(run, f, tu)} {tu}"
        # US store (user decision 2026-09-06): imperial first, metric in parentheses — whichever the source wrote
        return f"{conv} ({m.group(0)})" if unit in METRIC else f"{m.group(0)} ({conv})"
    new = AXIS_PAREN.sub(lambda m: f" {m.group(2)} ({m.group(1)})", MEAS.sub(rep, item))   # 2026-09-15: "9.45 in L (24 cm)"
    def rept(m):
        if adjacent_dual(new, m.start(), m.end()): return m.group(0)
        return _temp(m, m.group(2).upper())
    if not has_both_temp(new): new = TEMP.sub(rept, new)
    return imperial_first(new)

def _temp(m, scale):
    run = m.group(1)
    def cv(x):
        v = _num(x.group(0))
        return fmt(v * 9 / 5 + 32, "°F") if scale == "C" else fmt((v - 32) * 5 / 9, "°C")
    inner = re.sub(r'\s*°\s*[CF]\b', '', re.sub(NUM, cv, run))
    conv = f"{inner}°{'F' if scale == 'C' else 'C'}"
    return f"{conv} ({m.group(0)})" if scale == "C" else f"{m.group(0)} ({conv})"

# ---- imperial only (2026-09-11, user decision) -------------------------------------------------------------------------
DROP_PAREN = re.compile(r'(' + IMP_RUN + r')\s*\((?:' + MET_RUN + r')\)', re.I)
DROP_PAREN_T = re.compile(r'(-?[\d.,]+(?:\s*(?:-|–|to|/|,)\s*-?[\d.,]+(?:\s*°\s*F)?)*\s*°\s*F)\s*\((?:-?[\d.,]+(?:\s*(?:-|–|to|/|,)\s*-?[\d.,]+(?:\s*°\s*C)?)*\s*°\s*C)\)')
DROP_SLASH_T = re.compile(r'((?:-?[\d.,]+(?:\s*°\s*F)?\s*(?:-|–|to|,)\s*)*-?[\d.,]+\s*°\s*F)\s*/\s*(?:(?:-?[\d.,]+(?:\s*°\s*C)?\s*(?:-|–|to|,)\s*)*-?[\d.,]+\s*°\s*C)(?![\w])')
DROP_SLASH = re.compile(r'(' + IMP_RUN + r')\s*/\s*(?:' + MET_RUN + r')(?![\w])', re.I)

def imperial_only(text, ctx=""):
    """Metric -> imperial with the metric figure DROPPED (no parenthesis). For the budgeted elements only: H2, benefit
    bullets, FAQ questions, comparison rows, fit lines — the places where "(155 cm)" would break a limit or read as an
    import on a US-only store. '155 x 75 x 60 cm' -> '61 x 29.5 x 23.6 in'; '61 in (155 cm)' -> '61 in'; '5.98in/15.2cm'
    -> '5.98in'; '40°C' -> '104°F'. Imperial-only text is returned unchanged, so the pass is idempotent. Exemptions are
    the same as dual(): 4G/5G, 'L' as a length label, waterproof mm ratings, and liquid oz."""
    t = imperial_first(text)
    t = DROP_PAREN.sub(lambda m: m.group(1), t)
    t = DROP_PAREN_T.sub(lambda m: m.group(1), t)
    t = DROP_SLASH.sub(lambda m: m.group(1), t)
    t = DROP_SLASH_T.sub(lambda m: m.group(1), t)
    liquid = bool(LIQUID.search(t)) or bool(re.search(r'\d\s*(?:fl\.? ?)?oz\s+(?:water\s+)?(?:tank|reservoir|capacity|bottle)', t, re.I))
    def rep(m):
        skip, unit = _skip(t, m, liquid, (t + " " + ctx) if ctx else t)
        if skip or unit not in METRIC: return m.group(0)
        tu, f = METRIC[unit]
        cr = COUNT_RUN.match(m.group(1))
        if unit in COUNT_UNITS and cr: return f"{cr.group(1)} x {convert_run(cr.group(2), f, tu)} {tu}"
        return f"{convert_run(m.group(1), f, tu)} {tu}"
    t = MEAS.sub(rep, t)
    def rept(m):
        if m.group(2).upper() != "C": return m.group(0)
        run = re.sub(r'\s*°\s*[CF]\b', '', re.sub(NUM, lambda x: fmt(_num(x.group(0)) * 9 / 5 + 32, "°F"), m.group(1)))
        return f"{run}°F"
    return t if has_both_temp(t) else TEMP.sub(rept, t)

def convert_segment(seg, fn=None, ctx=None):
    """Convert text nodes only (tags, attributes, img alts untouched). Returns (new_seg, changed_count).
    fn defaults to dual(); pass imperial_only for the budgeted elements."""
    fn = fn or dual
    # 2026-09-15: every text node is judged with the WHOLE segment as context. `<strong>Capacity:</strong> 50 liters.`
    # splits the attribute name and its value into two nodes, so a node-local BAG test could not see "Capacity" while
    # converting "50 liters" — p08's Specifications line and p07's FAQ answer both leaked that way.
    if ctx is None: ctx = html.unescape(re.sub(r'<[^>]+>', ' ', seg))
    parts = re.split(r'(<[^>]+>)', seg); n = 0
    for i, p in enumerate(parts):
        if not p or p.startswith('<'): continue
        txt = html.unescape(p); new = fn(txt, ctx)
        if new != txt: parts[i] = html.escape(new, quote=False); n += 1
    return ''.join(parts), n

try:
    from compare_build import BLOCK_RE as _CB
    from fit_build import BLOCK_RE as _FB
    BLOCK = re.compile('(?:%s)|(?:%s)' % (_CB.pattern, _FB.pattern))
except Exception:   # outside the toolkit dir: a conservative fallback
    BLOCK = re.compile(r'<div class="vp-compare"[\s\S]*?</table>\s*</div>|<div class="vp-fit"[\s\S]*?</div>\s*</div>\s*</div>')

def process(h):
    """Scope (user decision 2026-09-06; Usage Tips + How to Use added 2026-09-07; every other source section added 2026-09-08): prose paragraphs, the Key Features intro + list,
    the Specifications list, EVERY <h3> section after Package Includes (How to Use, Usage Tips, and the additional source sections
    of description-format-rule.md §7c — Care Instructions, Safety Warnings, Materials …; Package Includes itself is not converted),
    and FAQ ANSWERS — DUAL (imperial first, metric in parentheses).
    Budgeted elements — the H2, the five benefit bullets (the first <ul>), FAQ questions — get IMPERIAL ONLY (2026-09-11, user
    decision: metric never stands alone on a US-only store; a parenthesis would break a limit or push a keyword out of the
    first 500 chars, so the metric figure is dropped here and lives on in the Specifications list). Comparison / fit blocks are
    converted by their own build scripts; img alts and SEO fields are never touched.
    Returns (html, dual_count, imperial_only_count)."""
    n = 0; k2 = 0
    # 2026-09-15 (review): the product-level bag flag, read from the H2 + the five bullets — the text that names what the
    # product IS. A spec line "Volume: 3.5 liters" carries no bag word of its own and used to be converted to fluid ounces.
    head = re.sub(r'<[^>]+>', ' ', h[:h.find('</ul>') + 5] if '</ul>' in h else h[:600])
    set_product_bag(looks_like_bag(html.unescape(head)))
    blocks = []
    def hold(m): blocks.append(m.group(0)); return f"\x00BLOCK{len(blocks)-1}\x00"
    h = BLOCK.sub(hold, h)
    first_ul_end = h.find('</ul>'); kf = h.find('<h3>Key Features</h3>'); spec = h.find('<h3>Specifications</h3>')
    pkg = h.find('<h3>Package Includes'); faq = h.find('<h3>FAQs</h3>')
    out = h
    def conv_range(a, b, fn=None):
        nonlocal out, n, k2
        if a < 0 or b < 0 or b <= a: return
        seg, k = convert_segment(out[a:b], fn)
        if fn is None: n += k
        else: k2 += k
        out = out[:a] + seg + out[b:]
    # work from the end backwards so earlier offsets stay valid
    if faq >= 0:   # FAQ answers: text after <br> inside each Q/A paragraph (dual); questions: imperial only
        head, tail = out[:faq], out[faq:]
        def qa(m):
            nonlocal n, k2
            qa_ctx = html.unescape(re.sub(r'<[^>]+>', ' ', m.group(0)))   # the question is context for its own answer
            q, kq = convert_segment(m.group(1), imperial_only, qa_ctx); k2 += kq
            ans, k = convert_segment(m.group(2), None, qa_ctx); n += k; return q + ans + m.group(3)
        tail = re.sub(r'(<p>\s*<strong>Q:.*?</strong>\s*<br\s*/?>)(.*?)(</p>)', qa, tail, flags=re.S)
        out = head + tail
    # Every <h3> section after Package Includes (How to Use, Usage Tips, additional source sections — 2026-09-07 / 2026-09-08,
    # user decision): between Package Includes and the fit block / FAQs — not budgeted. Package Includes itself is skipped.
    # Sections are converted last-to-first so earlier offsets stay valid.
    heads = [m.start() for m in re.finditer(r'<h3[^>]*>', out) if m.start() > pkg and not out.startswith('<h3>FAQs</h3>', m.start())] if pkg >= 0 else []
    for p0 in sorted(heads, reverse=True):
        nxt = [x for x in (out.find('<h3', p0 + 5), out.find('<div class="vp-', p0), out.find('\x00BLOCK', p0)) if x > p0]
        conv_range(p0, min(nxt) if nxt else len(out))
    if spec >= 0: conv_range(spec, pkg if pkg > spec else (faq if faq > spec else len(out)))
    if kf >= 0 and spec > kf: conv_range(kf, spec)
    if first_ul_end >= 0 and kf > first_ul_end: conv_range(first_ul_end, kf)   # prose paragraphs (+ images: alts are attributes, untouched)
    # H2 + benefit bullets (everything before the first </ul>): imperial only (2026-09-11)
    if first_ul_end >= 0: conv_range(0, first_ul_end, imperial_only)
    out = re.sub(r'\x00BLOCK(\d+)\x00', lambda m: blocks[int(m.group(1))], out)
    return out, n, k2

if __name__ == "__main__":
    total = 0; total2 = 0
    for a in sys.argv[1:]:
        n = int(a); p = f"final/d{n:02d}.json"; d = json.load(open(p))
        h2, k, k2 = process(d["descriptionHtml"])
        if k or k2: d["descriptionHtml"] = h2; json.dump(d, open(p, "w"), ensure_ascii=False, indent=1)
        print(f"{n:02d} unit-dual: {k} item(s) given the second unit, {k2} budgeted element(s) made imperial-only"); total += k; total2 += k2
    print(f"unit-dual: {total} item(s) converted, {total2} made imperial-only across {len(sys.argv) - 1} products")
