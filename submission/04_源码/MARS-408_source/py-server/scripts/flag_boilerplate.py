import json, re, shutil, os, sys
sys.path.insert(0, '.')

SRC = 'vectordb_data/netlearn_kb.json'
BAK = 'vectordb_data/netlearn_kb.json.boilerplate_bak'

# 模板废话特征短语（空内容填充条目独有）
BOILER = [
    "的工作原理和实现方法。掌握核心算法/机制",
    "需要理解其内涵和外延，区分易混淆概念",
    "掌握核心算法/机制，能进行定量分析和计算",
    "的工作原理和实现方法。掌握核心",
    "本知识点属于",
]
pat = re.compile("|".join(re.escape(b) for b in BOILER))

d = json.load(open(SRC, encoding='utf-8'))
texts, metas = d['texts'], d['metas']
flagged = 0
for i, (t, m) in enumerate(zip(texts, metas)):
    # 短文本 + 命中模板 = 废话填充
    is_boil = bool(pat.search(t)) or (len(t) < 40 and ('原理方法' in t or '概念定义' in t))
    if is_boil:
        m['exclude_retrieval'] = True
        flagged += 1
    else:
        m.pop('exclude_retrieval', None)

print(f"总条数 {len(texts)}，标记废话 {flagged} 条 ({flagged/len(texts)*100:.1f}%)")

# 备份原文件（遵守红线：不删除任何东西）
shutil.copy2(SRC, BAK)
print(f"已备份原文件 -> {BAK}")

# 写回（仅增加 metadata 标记，文本/向量不动）
with open(SRC, 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False)
print("已写回（增加 exclude_retrieval 标记）")

# 抽查：被标记的是否确实废话
print("\n=== 被标记样本（前5条）===")
c = 0
for i, m in enumerate(metas):
    if m.get('exclude_retrieval'):
        print(f"  [{metas[i].get('subject','?')}] {texts[i][:60].replace(chr(10),' ')}")
        c += 1
        if c >= 5:
            break
print("\n=== 未被标记样本（前3条 ds_sort）===")
c = 0
for i, m in enumerate(metas):
    if m.get('subject') == 'ds_sort' and not m.get('exclude_retrieval'):
        print(f"  {texts[i][:60].replace(chr(10),' ')}")
        c += 1
        if c >= 3:
            break
