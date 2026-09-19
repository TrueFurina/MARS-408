#!/usr/bin/env python3
# CRLF-safe, line-based: replace hardcoded subtle-surface rgba with var(--color-surface-2),
# and a stray color:#fff with var(--color-text-on-accent).
import os
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SURF2 = "background: var(--color-surface-2);"

SPEC = {
    "src/views/WrongQuestionsView.vue": [
        ("replace", "background: rgba(255,255,255,0.03);", SURF2),
        ("replace", "background: rgba(255,255,255,0.05);", SURF2),
    ],
    "src/views/DailyPlanView.vue": [
        ("replace", "background: rgba(255,255,255,0.08);", SURF2),
        ("replace", "background: rgba(255,255,255,0.06);", SURF2),
    ],
    "src/views/BenchmarkView.vue": [
        ("replace", "background: rgba(255,255,255,0.03);", SURF2),
        ("replace", "background: rgba(255,255,255,0.02);", SURF2),  # 582 + 600
    ],
    "src/components/KnowledgeGraph.vue": [
        ("replace", "background: rgba(255,255,255,0.02);", SURF2),
        ("replace", "color: #fff;", "color: var(--color-text-on-accent);"),
    ],
}

for rel, ops in SPEC.items():
    p = os.path.join(REPO, rel)
    with open(p, "rb") as f:
        data = f.read()
    text = data.decode("utf-8")
    lines = text.splitlines(keepends=True)
    out = []
    for line in lines:
        nl = line
        for op in ops:
            if op[0] == "replace":
                _, old, new = op
                if old in nl:
                    nl = nl.replace(old, new)
        out.append(nl)
    result = "".join(out)
    if result != text:
        with open(p, "wb") as f:
            f.write(result.encode("utf-8"))
    for op in ops:
        if op[0] == "replace" and op[1] in result:
            print(f"  [MISS] {rel}: still contains -> {op[1]}")
    print(f"  patched {rel}")
print("done.")
