import os, re, collections, difflib

ROOT = r"E:\Program\MARL\study-help-pro"

# ---------- 1. 硬编码 px / 手写字号 vs token ----------
src = os.path.join(ROOT, "src")
px_font = collections.Counter()
px_gap = collections.Counter()
files_px = collections.Counter()
for dp, dn, fn in os.walk(src):
    for f in fn:
        if not f.endswith(".vue"):
            continue
        p = os.path.join(dp, f)
        t = open(p, encoding="utf-8", errors="ignore").read()
        styles = "".join(re.findall(r"<style[^>]*>(.*?)</style>", t, re.S))
        if not styles:
            continue
        fs = re.findall(r"font-size:\s*(\d+(?:\.\d+)?)px", styles)
        for v in fs:
            px_font[v] += 1
        gp = re.findall(r"(?:gap|padding|margin)(?:-top|-bottom|-left|-right)?:\s*[^;]*?(\d+)px", styles)
        for v in gp:
            px_gap[v] += 1
        files_px[os.path.relpath(p, src)] = len(fs) + len(gp)

print("=== 1. 手写 font-size px 值分布（应收敛到 token 刻度）===")
for k, c in sorted(px_font.items(), key=lambda x: -x[1])[:18]:
    print(f"   font-size {k}px  x{c}")
print(f"   >>> 不同字号档位数量: {len(px_font)}")

print("\n=== 手写 gap/padding/margin px 值分布 TOP ===")
for k, c in sorted(px_gap.items(), key=lambda x: -x[1])[:12]:
    print(f"   {k}px  x{c}")
print(f"   >>> 不同间距档位数量: {len(px_gap)}")

print("\n=== 硬编码 px 最多的视图 TOP10 ===")
for k, c in files_px.most_common(10):
    print(f"   {k:45} {c}")

# ---------- 2. 跨文件重复 CSS 声明块 ----------
print("\n\n=== 2. 跨文件重复的 CSS 声明块（复制粘贴证据）===")
def decl_blocks(s):
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", s):
        sel, body = m.group(1).strip(), m.group(2).strip()
        if not body or body.startswith("@"):
            continue
        decls = tuple(sorted(d.strip() for d in body.split(";") if d.strip()))
        if len(decls) >= 3:
            out.append((sel, decls))
    return out

file_blocks = {}
for dp, dn, fn in os.walk(src):
    for f in fn:
        if not f.endswith(".vue"):
            continue
        p = os.path.join(dp, f)
        t = open(p, encoding="utf-8", errors="ignore").read()
        st = "".join(re.findall(r"<style[^>]*>(.*?)</style>", t, re.S))
        if st:
            file_blocks[os.path.relpath(p, src)] = decl_blocks(st)

# 按声明体聚合
body_map = collections.defaultdict(list)
for fname, blocks in file_blocks.items():
    for sel, decls in blocks:
        body_map[decls].append((fname, sel))

dup = [(d, v) for d, v in body_map.items() if len(set(f for f, _ in v)) >= 3]
dup.sort(key=lambda x: -len(set(f for f, _ in x[1])))
print(f"出现在 >=3 个不同文件的声明体: {len(dup)} 组")
for decls, v in dup[:12]:
    files = sorted(set(f for f, _ in v))
    print(f"\n   [{len(files)} 文件] {'; '.join(list(decls)[:5])}")
    for f in files[:5]:
        sels = [s for ff, s in v if ff == f][:2]
        print(f"        {f}  ->  {', '.join(sels)}")

# ---------- 3. 主题机制 ----------
print("\n\n=== 3. 主题 / 深色模式机制 ===")
for name in ("_variables.css", "_base.css", "_components.css", "_layout.css"):
    p = os.path.join(src, "assets", "styles", name)
    if os.path.exists(p):
        t = open(p, encoding="utf-8", errors="ignore").read()
        print(f"   {name}: {t.count(chr(10))+1} 行 | "
              f"data-theme={t.count('data-theme')} | .dark={len(re.findall(r'[.:]dark', t))} | "
              f"prefers-color-scheme={t.count('prefers-color-scheme')}")
    else:
        print(f"   {name}: 不存在")

# ---------- 4. dist 体积 ----------
print("\n\n=== 4. 构建产物体积 ===")
d = os.path.join(ROOT, "dist", "assets")
if os.path.isdir(d):
    items = []
    for f in os.listdir(d):
        fp = os.path.join(d, f)
        items.append((os.path.getsize(fp), f))
    items.sort(reverse=True)
    tot = sum(i[0] for i in items)
    print(f"   dist/assets 总计 {tot/1024/1024:.2f} MB, {len(items)} 个文件")
    for sz, f in items[:12]:
        print(f"   {sz/1024:9.1f} KB  {f}")
else:
    print("   dist/assets 不存在（未构建）")

# ---------- 5. 测试 ----------
print("\n\n=== 5. 测试覆盖 ===")
tests = []
for dp, dn, fn in os.walk(src):
    for f in fn:
        if "spec" in f or "test" in f:
            tests.append(os.path.relpath(os.path.join(dp, f), src))
print(f"   src 下测试文件: {len(tests)}")
for t in tests:
    print("    ", t)

# ---------- 6. 懒加载 / 无障碍 / 语义化 ----------
print("\n\n=== 6. 其他体检 ===")
allvue = []
for dp, dn, fn in os.walk(src):
    for f in fn:
        if f.endswith(".vue"):
            allvue.append(os.path.join(dp, f))
tot = 0
div_click = 0
btn = 0
lazy = 0
reduce_motion = 0
focus_visible = 0
media_q = 0
for p in allvue:
    t = open(p, encoding="utf-8", errors="ignore").read()
    tot += 1
    div_click += len(re.findall(r"<div[^>]*@click", t))
    btn += len(re.findall(r"<button", t))
    lazy += len(re.findall(r"defineAsyncComponent|\(\)\s*=>\s*import\(", t))
    reduce_motion += t.count("prefers-reduced-motion")
    focus_visible += t.count("focus-visible")
    media_q += len(re.findall(r"@media", t))
print(f"   .vue 总数                {tot}")
print(f"   <button> 出现次数         {btn}")
print(f"   <div @click>（假按钮）    {div_click}")
print(f"   异步组件/懒加载           {lazy}")
print(f"   使用 prefers-reduced-motion 的文件数 {reduce_motion}")
print(f"   使用 :focus-visible 的文件数         {focus_visible}")
print(f"   @media 查询总数           {media_q}")
router_p = os.path.join(src, "router", "index.ts")
if os.path.exists(router_p):
    rt = open(router_p, encoding="utf-8", errors="ignore").read()
    print(f"   router 中 () => import(   {len(re.findall(r'=>\s*import\(', rt))}")
    print(f"   router 中静态 import       {len(re.findall(r'^import .*views/', rt, re.M))}")
