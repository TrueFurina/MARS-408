#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""临时：把两个新门禁接入 ci.yml —— 基于 HEAD 版本插入步骤并暂存（不碰工作树里的并发 WIP）。"""
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REL = ".github/workflows/ci.yml"

head = subprocess.run(["git", "show", f"HEAD:{REL}"], cwd=ROOT,
                      capture_output=True, text=True, encoding="utf-8").stdout

ANCHOR = ("      - name: Run SSOT drift checker (fail on any drift)\n"
          "        run: python design-system/check_tokens.py")

ADD = ANCHOR + ("\n"
                "      - name: Run component raw-value gate (fail on hardcoded hex/rgb)\n"
                "        run: python design-system/check_raw_values.py\n"
                "      - name: Run prose-doc token drift gate (fail if doc cites non-token color)\n"
                "        run: python design-system/check_doc_tokens.py")

if ANCHOR not in head:
    raise SystemExit("ERROR: anchor not found in HEAD ci.yml")
if "check_raw_values.py" in head:
    raise SystemExit("ERROR: already wired in HEAD (unexpected)")

new = head.replace(ANCHOR, ADD, 1)
tmp = os.path.join(ROOT, ".workbuddy", "_ci_yml_tmp")
with open(tmp, "w", encoding="utf-8", newline="") as f:
    f.write(new)

sha = subprocess.run(["git", "hash-object", "-w", tmp], cwd=ROOT,
                     capture_output=True, text=True).stdout.strip()
subprocess.run(["git", "update-index", "--cacheinfo", "100644", sha, REL], cwd=ROOT, check=True)
os.remove(tmp)
print(f"staged ci.yml -> {sha[:10]} (HEAD + 2 gate steps)")
