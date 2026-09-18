import os, re, json, collections

ROOT = r"E:\Program\MARL\study-help-pro\src"
vue_files = []
for dp, dn, fn in os.walk(ROOT):
    for f in fn:
        if f.endswith(".vue") or f.endswith(".ts") or f.endswith(".css"):
            vue_files.append(os.path.join(dp, f))

rows = []
tot_lines = 0
for p in vue_files:
    try:
        s = open(p, encoding="utf-8", errors="ignore").read()
    except Exception:
        continue
    n = s.count("\n") + 1
    tot_lines += n
    rel = os.path.relpath(p, ROOT).replace("\\", "/")
    # style block lines
    style_lines = 0
    for m in re.finditer(r"<style[^>]*>(.*?)</style>", s, re.S):
        style_lines += m.group(1).count("\n")
    script_lines = 0
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", s, re.S):
        script_lines += m.group(1).count("\n")
    hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", s)
    # filter out charset/urls
    hexes = [h for h in hexes if len(h) in (4, 7, 9)]
    varuses = len(re.findall(r"var\(--", s))
    aria = len(re.findall(r"\baria-[a-z]+=", s))
    role = len(re.findall(r'\brole="', s))
    tabindex = len(re.findall(r"\btabindex=", s))
    onclick_no_key = len(re.findall(r"@click=", s)) - len(re.findall(r"@keydown|@keyup|@keypress", s))
    inline_style = len(re.findall(r'\s:style="', s)) + len(re.findall(r'\sstyle="', s))
    px_hard = len(re.findall(r":\s*\d+px", s))
    rows.append(dict(f=rel, n=n, style=style_lines, script=script_lines,
                     hex=len(hexes), varuse=varuses, aria=aria, role=role,
                     tabindex=tabindex, click=onclick_no_key, inline=inline_style, px=px_hard))

rows.sort(key=lambda r: -r["n"])
print("TOTAL FILES:", len(rows), "TOTAL LINES:", tot_lines)
print("\n=== TOP 25 LARGEST FILES (lines | style% | hexColors | var() | aria) ===")
print(f"{'file':52} {'lines':>6} {'style':>6} {'script':>7} {'hex':>5} {'var()':>6} {'aria':>5} {'inline':>7} {'px':>5}")
for r in rows[:25]:
    print(f"{r['f'][:52]:52} {r['n']:6} {r['style']:6} {r['script']:7} {r['hex']:5} {r['varuse']:6} {r['aria']:5} {r['inline']:7} {r['px']:5}")

print("\n=== AGGREGATE ===")
agg = collections.OrderedDict()
for k in ("n", "style", "script", "hex", "varuse", "aria", "role", "tabindex", "click", "inline", "px"):
    agg[k] = sum(r[k] for r in rows)
for k, v in agg.items():
    print(f"  {k:10} {v}")

print("\n=== FILES WITH >20 HEX COLORS ===")
for r in rows:
    if r["hex"] > 20:
        print(f"  {r['f']:55} hex={r['hex']:4} var={r['varuse']:4} lines={r['n']}")

print("\n=== FILES WITH 0 aria AND >150 lines ===")
for r in rows:
    if r["aria"] == 0 and r["n"] > 150:
        print(f"  {r['f']:55} lines={r['n']}")

print("\n=== SIZE DISTRIBUTION ===")
buckets = [(0,100),(100,300),(300,600),(600,1000),(1000,2000),(2000,99999)]
for a,b in buckets:
    c = sum(1 for r in rows if a <= r["n"] < b)
    print(f"  {a}-{b}: {c}")
