import os, re

ROOT = r"E:\Program\MARL\study-help-pro\src"

bad = []
ok = []
for dp, dn, fn in os.walk(ROOT):
    for f in fn:
        if not f.endswith(".vue"):
            continue
        p = os.path.join(dp, f)
        lines = open(p, encoding="utf-8", errors="ignore").read().split("\n")
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        for i, ln in enumerate(lines):
            if not re.search(r"<div[^>]*@click", ln):
                continue
            # 取该标签完整文本（可能跨行，向后最多接 6 行找 '>'）
            tag = ln
            j = i
            while ">" not in tag and j + 1 < len(lines) and j - i < 6:
                j += 1
                tag += "\n" + lines[j]
            has_role = "role=" in tag
            has_tab = "tabindex" in tag
            # 键盘处理：在本标签后 12 行内找 @keydown/@keyup
            ctx = "\n".join(lines[i : i + 12])
            has_key = bool(re.search(r"@keydown|@keyup|@keypress", ctx))
            rec = (rel, i + 1, tag.strip().split("\n")[0][:80], has_role, has_tab, has_key)
            if has_role and has_tab and has_key:
                ok.append(rec)
            else:
                bad.append(rec)

print(f"=== <div @click> 假按钮审计 ===")
print(f"完全合规(role+tabindex+键盘): {len(ok)}")
print(f"存在缺口:                    {len(bad)}")
print("\n--- 缺口明细 (file:line | role | tabindex | 键盘) ---")
for rel, ln, txt, r, t, k in bad:
    flags = f"role={'Y' if r else 'N'} tabindex={'Y' if t else 'N'} key={'Y' if k else 'N'}"
    print(f"  {rel}:{ln}  [{flags}]")
    print(f"      {txt}")
