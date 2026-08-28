import os, glob, re

ROOT = r"E:\Program\MARL\study-help-pro\src"
FILES = glob.glob(os.path.join(ROOT, "**", "*.vue"), recursive=True)
# 不含 _variables.css / main.css（已单独处理）

REPL = [
    # ---- 危险 tint -> token（先处理，避免与品牌紫混淆）----
    ("rgba(239, 68, 68, 0.4)", "var(--accent-danger-20)"),
    ("rgba(239,68,68,0.4)",   "var(--accent-danger-20)"),
    ("rgba(239, 68, 68, 0.3)", "var(--accent-danger-20)"),
    ("rgba(239,68,68,0.3)",   "var(--accent-danger-20)"),
    ("rgba(239, 68, 68, 0.2)", "var(--accent-danger-20)"),
    ("rgba(239,68,68,0.2)",   "var(--accent-danger-20)"),
    ("rgba(239, 68, 68, 0.15)", "var(--accent-danger-20)"),
    ("rgba(239,68,68,0.15)",  "var(--accent-danger-20)"),
    ("rgba(239, 68, 68, 0.12)", "var(--accent-danger-10)"),
    ("rgba(239,68,68,0.12)",  "var(--accent-danger-10)"),
    ("rgba(239, 68, 68, 0.1)", "var(--accent-danger-10)"),
    ("rgba(239,68,68,0.1)",   "var(--accent-danger-10)"),
    # ---- 成功 tint -> token ----
    ("rgba(34, 197, 94, 0.15)", "var(--accent-success-20)"),
    ("rgba(34,197,94,0.15)",  "var(--accent-success-20)"),
    ("rgba(34, 197, 94, 0.1)",  "var(--accent-success-10)"),
    ("rgba(34,197,94,0.1)",   "var(--accent-success-10)"),
    ("rgba(34, 197, 94, 0.08)", "var(--accent-success-10)"),
    ("rgba(34,197,94,0.08)",  "var(--accent-success-10)"),
    # ---- 品牌漂移 indigo -> 我们的 accent 色相 ----
    ("rgba(99,102,241,",  "rgba(124,106,242,"),
    ("#6366f1",             "#7c6af2"),
    # ---- 品牌紫 tint（已对齐色相）-> token ----
    ("rgba(124,106,242,0.06)", "var(--accent-primary-10)"),
    ("rgba(124,106,242,0.08)", "var(--accent-primary-10)"),
    ("rgba(124,106,242,0.1)",  "var(--accent-primary-10)"),
    ("rgba(124,106,242,0.15)", "var(--accent-primary-20)"),
    ("rgba(124,106,242,0.2)",  "var(--accent-primary-20)"),
    ("rgba(124,106,242,0.3)",  "var(--accent-primary-30)"),
    # ---- 危险文字 #fca5a5 -> token（浅色自动变深红）----
    ("#fca5a5", "var(--text-danger)"),
    # ---- P3 调色板外 teal -> 成功 tint ----
    ("rgba(15,118,110,0.04)", "var(--accent-success-10)"),
    # ---- 死 fallback 清理 ----
    ("var(--border-color, rgba(120,130,170,0.25))", "var(--border-color)"),
    ("var(--glass-bg, rgba(255,255,255,0.04))",    "var(--glass-bg)"),
]

total = 0
changed_files = []
for f in FILES:
    with open(f, "r", encoding="utf-8") as fh:
        s = fh.read()
    orig = s
    for old, new in REPL:
        if old in s:
            s = s.replace(old, new)
    if s != orig:
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(s)
        n = sum(orig.count(o) for o, _ in REPL if o in orig)
        changed_files.append((os.path.relpath(f, ROOT), n))
        total += n

print(f"处理文件: {len(FILES)}")
print(f"改动文件: {len(changed_files)}")
print(f"替换总数: {total}")
for rel, n in changed_files:
    print(f"  {rel}: {n} 处")
