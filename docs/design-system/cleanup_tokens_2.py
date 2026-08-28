import os, glob

ROOT = r"E:\Program\MARL\study-help-pro\src"
FILES = glob.glob(os.path.join(ROOT, "**", "*.vue"), recursive=True)

# 仅补首轮漏掉的透明度 + 调色板外色；不重跑 indigo 对齐/0.3 紫映射，避免二次误伤 Canvas
REPL = [
    ("rgba(239, 68, 68, 0.06)", "var(--accent-danger-10)"),
    ("rgba(239,68,68,0.06)",   "var(--accent-danger-10)"),
    ("rgba(239, 68, 68, 0.08)", "var(--accent-danger-10)"),
    ("rgba(239,68,68,0.08)",   "var(--accent-danger-10)"),
    ("rgba(34, 197, 94, 0.12)", "var(--accent-success-10)"),
    ("rgba(34,197,94,0.12)",  "var(--accent-success-10)"),
    # TeachingRulesPanel:216 学科色（#8b5cf6 = subject-ds）+ 其 15% tint
    ("rgba(139,92,246,0.15)", "color-mix(in srgb, var(--subject-ds) 15%, transparent)"),
    ("#8b5cf6", "var(--subject-ds)"),
    # 调色板外色 -> token
    ("#10b981", "var(--accent-success)"),
    ("#fecaca", "var(--accent-warm)"),
    ("#a5b4fc", "var(--accent-secondary)"),
]

total = 0
changed = []
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
        changed.append((os.path.relpath(f, ROOT), n))
        total += n

print(f"改动文件: {len(changed)}  替换总数: {total}")
for rel, n in changed:
    print(f"  {rel}: {n} 处")
