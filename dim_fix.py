#!/usr/bin/env python3
"""dim_fix.py — rewrite wrong / mixed-unit measurements in live descriptions (2026-10-21, user decision:
"a measurement never mixes units"). Every fixed measurement leaves as  <figures> in (<figures> cm|mm|m).

Rules
 1. Pair "A (B)" whose sides disagree by >12 % on any figure: rebuild from the clean metric side (the source);
    if the two sides match once one is reordered, keep the imperial figures and reorder the metric ones.
    A metric side with one more figure than the imperial side (lost axis) is also the source.
 2. Pair whose sides agree but either side mixes units ("18 in × 4 ft (46 × 122 cm)", "18"x18" (45.7"x45.7 cm)"):
    each side re-expressed in one unit from its own figures.
 3. Per-axis slash runs ("24" / 60.96 cm x 43" / 109.22 cm"): -> "24 × 43 in (61 × 109.2 cm)".
 4. A second identical "(…)" within 40 characters of the first is dropped.
 Rounding / supplier differences of ≤12 % are NOT touched. Pack counts ("(2 × 50×75 cm)"), "Dia" prefixes and fractions
 ("5/8 inch (16 mm)") are not pairs. Anything else ambiguous is printed MANUAL and left as it is.

  python3 dim_fix.py plan out/active.json   -> out/dimfix/plan.json + mutation files out/dimfix/mutN.json
"""
import json, re, sys, os, html as H

TO_MM = {"mm": 1, "cm": 10, "m": 1000, "in": 25.4, "inch": 25.4, "inches": 25.4, '"': 25.4, "ft": 304.8, "feet": 304.8}
SYS = {"mm": "M", "cm": "M", "m": "M", "in": "I", "inch": "I", "inches": "I", '"': "I", "ft": "I", "feet": "I"}
U = r'(?:mm|cm|m|inches|inch|in|ft|feet|")'
N = r'\d+(?:[.,]\d+)?'
S = r'\s*(?:x|×|\*)\s*'
RUN = N + r'\s*' + U + r'?(?:' + S + N + r'\s*' + U + r'?)*'
PAIR = re.compile(r'(?<![\w./"])(' + RUN + r')\s*\((' + RUN + r')\)(?=$|[^\w])', re.I)
SLASH_AX = N + r'\s*' + U + r'\s*/\s*' + N + r'\s*' + U
SLASH = re.compile(r'(?<![\w./])(' + SLASH_AX + r'(?:' + S + SLASH_AX + r')+)(?![\w])', re.I)

def num(s): return float(s.replace(",", "."))
def figs(run):
    ps = re.split(S, run.strip()); out = []; last = None
    for p in reversed(ps):
        m = re.fullmatch(r'(' + N + r')\s*(' + U + r')?', p.strip(), re.I)
        if not m: return None
        u = (m.group(2) or last); last = u
        out.append((num(m.group(1)), u.lower() if u else None))
    out.reverse()
    return out if all(u for _, u in out) else None
def system(fs): s = {SYS[u] for _, u in fs}; return s.pop() if len(s) == 1 else None
def mixed(fs): return len({u for _, u in fs}) > 1
def apart(fa, fb):
    w = 0
    for (a, ua), (b, ub) in zip(fa, fb):
        x, y = a * TO_MM[ua], b * TO_MM[ub]
        if max(x, y): w = max(w, abs(x - y) / max(x, y))
    return w
def g(v):  # trim number
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s
def r1(v): return f"{v:.1f}".rstrip("0").rstrip(".")
def imp_str(mm_list):
    ins = [x / 25.4 for x in mm_list]
    if max(ins) > 120: return " × ".join(r1(i / 12) for i in ins) + " ft"
    return " × ".join(r1(i) if i >= 0.1 else f"{i:.2f}".rstrip("0") for i in ins) + " in"
def met_str(mm_list):
    if max(mm_list) >= 1000 and all(x % 100 == 0 for x in mm_list): return " × ".join(g(x / 1000) for x in mm_list) + " m"
    if max(mm_list) < 10: return " × ".join(g(x) for x in mm_list) + " mm"
    return " × ".join((f"{x/10:.0f}" if x >= 300 else r1(x / 10)) for x in mm_list) + " cm"
def own_imp(fs):   # imperial side in one unit from its own figures
    if not mixed(fs): return " × ".join(g(v) for v, _ in fs) + (" in" if fs[0][1] in ("in", "inch", "inches", '"') else " ft")
    return imp_str([v * TO_MM[u] for v, u in fs])
def own_met(fs):
    if not mixed(fs): return " × ".join(g(v) for v, _ in fs) + " " + fs[0][1]
    return met_str([v * TO_MM[u] for v, u in fs])

def fix_pair(a, b):
    """returns (new_text or None, note)"""
    fa, fb = figs(a), figs(b)
    if not fa or not fb: return None, None
    sa, sb = system(fa), system(fb)
    if not sa and not sb: return None, "MANUAL both sides mix systems"
    if not sa or not sb:   # one side mixes in and cm (e.g. "(5.5 in × 1.2 m)", "(45.7"x45.7 cm)"): the clean side is the source
        src = fa if sa else fb
        if len(fa) != len(fb): return None, "MANUAL figure count differs"
        mm = [v * TO_MM[u] for v, u in src]
        if system(src) == "I": return f"{own_imp(src)} ({met_str(mm)})", "rebuilt from imperial (other side mixed)"
        return f"{imp_str(mm)} ({own_met(src)})", "rebuilt from metric (other side mixed)"
    if sa == sb: return None, None
    imp, met = (fa, fb) if sa == "I" else (fb, fa)
    if system(met) != "M": return None, None
    if len(imp) != len(met):
        if len(imp) >= 2 and len(met) == len(imp) + 1 and apart(imp, met[:len(imp)]) <= 0.12:
            return f"{imp_str([v * TO_MM[u] for v, u in met])} ({own_met(met)})", "lost axis restored from metric"
        return None, None   # pack counts, Dia, frame sizes
    w = apart(imp, met)
    if w <= 0.12:
        if mixed(imp) or mixed(met): return f"{own_imp(imp)} ({own_met(met)})", "units unified"
        return None, None
    # swapped order?
    if len(imp) > 1 and apart(sorted(imp, key=lambda f: f[0] * TO_MM[f[1]]), sorted(met, key=lambda f: f[0] * TO_MM[f[1]])) <= 0.12:
        order = sorted(range(len(imp)), key=lambda i: imp[i][0] * TO_MM[imp[i][1]])
        msort = sorted(met, key=lambda f: f[0] * TO_MM[f[1]]); newm = [None] * len(imp)
        for rank, i in enumerate(order): newm[i] = msort[rank]
        return f"{own_imp(imp)} ({own_met(newm)})", "metric order fixed"
    return f"{imp_str([v * TO_MM[u] for v, u in met])} ({own_met(met)})", f"rebuilt from metric ({w:.0%} off)"

def fix_slash(run):
    axes = re.split(S, run); I, M = [], []
    for ax in axes:
        m = re.fullmatch(r'(' + N + r')\s*(' + U + r')\s*/\s*(' + N + r')\s*(' + U + r')', ax.strip(), re.I)
        (a, ua, b, ub) = m.groups(); ua, ub = ua.lower(), ub.lower()
        if SYS[ua] == SYS[ub]: return None
        if SYS[ua] == "M": a, ua, b, ub = b, ub, a, ua
        I.append((num(a), ua)); M.append((num(b), ub))
    if apart(I, M) > 0.12: return None
    return f"{own_imp(I)} ({met_str([v * TO_MM[u] for v, u in M])})"

DUP = re.compile(r'(\(([^()<]{3,40})\))([^()<]{0,40}?)\s*\(\2\)')
def fix_text(t, log):
    def ps(m):
        new, note = fix_pair(m.group(1), m.group(2))
        if note and note.startswith("MANUAL"): log.append((m.group(0), note)); return m.group(0)
        if new and new != m.group(0): log.append((m.group(0), new)); return new
        return m.group(0)
    def ss(m):
        new = fix_slash(m.group(1))
        if new: log.append((m.group(1), new)); return new
        log.append((m.group(1), "MANUAL slash run")); return m.group(1)
    t2 = SLASH.sub(ss, t)
    t2 = PAIR.sub(ps, t2)
    if t2 != t: t2 = DUP.sub(lambda m: m.group(1) + m.group(3), t2)
    return t2

def fix_html(h, log):
    return re.sub(r'>([^<]+)<', lambda m: ">" + fix_text(m.group(1), log) + "<", h)

def plan(path):
    ps = json.load(open(path)); os.makedirs("out/dimfix", exist_ok=True); plan, items = [], []
    for p in ps:
        log = []; h = p["descriptionHtml"] or ""; new = fix_html(h, log)
        if log: plan.append({"id": p["id"], "handle": p["handle"], "changes": log})
        if new != h: items.append((p["id"], new))
    json.dump(plan, open("out/dimfix/plan.json", "w"), indent=1, ensure_ascii=False)
    for i in range(0, len(items), 10):
        ch = items[i:i + 10]
        q = "mutation(" + ",".join(f"$p{j}:ProductUpdateInput!" for j in range(len(ch))) + "){" + \
            " ".join(f"p{j}:productUpdate(product:$p{j}){{userErrors{{field message}}}}" for j in range(len(ch))) + "}"
        json.dump({"query": q, "variables": {f"p{j}": {"id": pid, "descriptionHtml": hh} for j, (pid, hh) in enumerate(ch)}},
                  open(f"out/dimfix/mut{i // 10:03d}.json", "w"))
    man = sum(1 for p in plan for c in p["changes"] if c[1].startswith("MANUAL"))
    print(f"{len(items)} products to update ({(len(items) + 9) // 10} files), {man} manual items")

if __name__ == "__main__":
    {"plan": plan}[sys.argv[1]](sys.argv[2])
