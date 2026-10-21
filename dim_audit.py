#!/usr/bin/env python3
"""dim_audit.py — scan live descriptions for wrong unit conversions (2026-10-21).

Finds every "<measurement> (<conversion>)" pair in descriptionHtml text and checks that the two sides agree
(each figure within 3 %, same figure count). Catches the unit_dual.py mixed-unit bug
("18 in × 4 ft (5.5 in × 1.2 m) per roll (46 × 122 cm)") and any other wrong pair.
Fix = drop the wrong parenthesis; if no correct conversion sits next to it, re-run unit_dual.dual() on the bare figure.

  python3 dim_audit.py scan  out/active.json         # fetch all ACTIVE products -> out/active.json
  python3 dim_audit.py check out/active.json         # -> out/dim_findings.json + summary
  python3 dim_audit.py fix   out/active.json         # -> out/dim_push/mutN.json (10 products per file)
"""
import json, re, sys, os, html as H
from shopify_api import gql
import unit_dual as U

TO_MM = {"mm": 1, "cm": 10, "m": 1000, "in": 25.4, "inch": 25.4, "inches": 25.4, '"': 25.4, "ft": 304.8, "feet": 304.8}
NUMU = r'(\d+(?:[.,]\d+)?)\s*(mm|cm|m|inches|inch|in|ft|feet|")?'
SEP = r'\s*(?:x|×|\*)\s*'
RUN = r'\d+(?:[.,]\d+)?\s*(?:mm|cm|m|inches|inch|in|ft|feet|")?(?:' + SEP + r'\d+(?:[.,]\d+)?\s*(?:mm|cm|m|inches|inch|in|ft|feet|")?)*'
PAIR = re.compile(r'(?<![\w.])(' + RUN + r')\s*\((' + RUN + r')\)', re.I)

def figs(run):
    out = []; parts = re.split(SEP, run.strip()); last = None
    for p in reversed(parts):
        m = re.fullmatch(NUMU, p.strip(), re.I)
        if not m: return None
        u = (m.group(2) or last); last = u
        out.append((float(m.group(1).replace(",", ".")), u.lower() if u else None))
    return list(reversed(out))

def bad_pair(a, b):
    fa, fb = figs(a), figs(b)
    if not fa or not fb or any(u is None for _, u in fa + fb): return None
    if len(fa) != len(fb): return "figure count differs"
    for (va, ua), (vb, ub) in zip(fa, fb):
        x, y = va * TO_MM[ua], vb * TO_MM[ub]
        if max(x, y) == 0: continue
        if abs(x - y) / max(x, y) > 0.03 and abs(x - y) > 1.5: return f"{va} {ua} ≠ {vb} {ub}"
    return None

def text_issues(t):
    iss = []
    for m in PAIR.finditer(t):
        why = bad_pair(m.group(1), m.group(2))
        if why: iss.append({"text": m.group(0), "why": why})
    return iss

def fix_text(t):
    def rep(m):
        if not bad_pair(m.group(1), m.group(2)): return m.group(0)
        rest = t[m.end():m.end() + 40]
        # a correct conversion follows later in the same item ("... per roll (46 × 122 cm)") -> just drop the wrong one
        nxt = re.match(r'[^<(]{0,20}\((' + RUN + r')\)', rest)
        if nxt and not bad_pair(m.group(1), nxt.group(1)): return m.group(1)
        return U.dual(m.group(1))
    return PAIR.sub(rep, t)

def fix_html(h):
    return re.sub(r'>([^<]+)<', lambda m: ">" + fix_text(m.group(1)) + "<", h)

Q = """query($after:String){ products(first:100, after:$after, query:"status:active"){
  pageInfo{hasNextPage endCursor} nodes{ id handle title descriptionHtml } } }"""

def scan(path):
    out, after = [], None
    while True:
        d = gql(Q, {"after": after})["data"]["products"]; out += d["nodes"]
        if not d["pageInfo"]["hasNextPage"]: break
        after = d["pageInfo"]["endCursor"]
    json.dump(out, open(path, "w")); print(f"fetched {len(out)} active products")

def check(path):
    ps = json.load(open(path)); res = []
    for p in ps:
        iss = text_issues(H.unescape(re.sub(r'<[^>]+>', ' ', p["descriptionHtml"] or "")))
        if iss: res.append({"id": p["id"], "handle": p["handle"], "issues": iss})
    os.makedirs("out", exist_ok=True); json.dump(res, open("out/dim_findings.json", "w"), indent=1, ensure_ascii=False)
    print(f"{len(ps)} products scanned, {len(res)} with wrong conversions, {sum(len(r['issues']) for r in res)} pairs")
    return res

def fix(path):
    ps = {p["id"]: p for p in json.load(open(path))}; res = check(path); os.makedirs("out/dim_push", exist_ok=True)
    items = []
    for r in res:
        old = ps[r["id"]]["descriptionHtml"]; new = fix_html(old)
        left = text_issues(H.unescape(re.sub(r'<[^>]+>', ' ', new)))
        if new != old and not left: items.append((r["id"], new))
        else: print("MANUAL", r["handle"], left or "no change")
    for i in range(0, len(items), 10):
        chunk = items[i:i + 10]
        q = "mutation(" + ",".join(f"$p{j}:ProductUpdateInput!" for j in range(len(chunk))) + "){" + \
            " ".join(f"p{j}:productUpdate(product:$p{j}){{userErrors{{field message}}}}" for j in range(len(chunk))) + "}"
        json.dump({"query": q, "variables": {f"p{j}": {"id": pid, "descriptionHtml": h} for j, (pid, h) in enumerate(chunk)}},
                  open(f"out/dim_push/mut{i // 10}.json", "w"))
    print(f"{len(items)} products ready to push in {(len(items) + 9) // 10} files")

if __name__ == "__main__":
    {"scan": scan, "check": check, "fix": fix}[sys.argv[1]](sys.argv[2])
