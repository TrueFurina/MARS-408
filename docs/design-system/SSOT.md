# MARS-408 设计系统 · 单一真相源（SSOT）契约

> 收口日期：2026-07-13 ｜ 主理人：画统筹（Hua）
> 配套：`src/assets/styles/_variables.css`（权威源）· `check_tokens.py`（漂移门禁）· `audit-report.md`（Vue 应用侧已 10/10 清零）

---

## 0. 一句话结论

**`_variables.css` 的 `:root` 块是 MARS-408 设计系统唯一的、可被修改的令牌真相源。**
其余一切（文档 / 原型 / 可视化 Style Guide）都是它的**消费者或派生物**，严禁成为独立真相源。

---

## 1. 分层与职责

| 层 | 文件 | 角色 | 能否改 token |
|----|------|------|--------------|
| **权威源 (SSOT)** | `src/assets/styles/_variables.css` 的 `:root` + `[data-theme="light"]` | 应用真正在跑的令牌；语义层 `--color-*` + 兼容别名 + 品牌色 + 408 分色 + 浅色覆盖 | ✅ **唯一可改处** |
| 文档派生 | `DESIGN_TOKENS.md` | 落地页原型生成规范 = `_variables.css` base **+ 落地页专用扩展**（`--space-*`/`--fs-*`/`--z-*`/组件令牌/`--container`/`--gradient-ds`） | ❌ 只读参考；来源须标注 `_variables.css` |
| 可视化参考 | `design-system/showcase.html` | Living Style Guide，可视化全部令牌，双主题实时切换；**不参与构建** | ❌ 只读；其 `:root` 必须与权威源对齐 |
| 消费者 | `public/showcase/*.html`（4 原型） | 内联 `_variables.css` 的 `:root` 拷贝 + 各自表面扩展 token | ❌ **严禁手改内联 token** |

> `DESIGN.md`（v8  prose 文档）是**人的可读说明**，不是可执行源；可执行真相源是 `_variables.css`。

---

## 2. 铁律（改 token 时遵守）

1. **只改 `_variables.css`**：新增 / 修改 / 删除令牌，一律在 `:root`（深色默认）与 `[data-theme="light"]`（浅色）两处同步。
2. **组件只引用语义层**：Vue 组件用 `--color-*` / `--accent-*` / `--subject-*` / `--glass-*` 等语义与品牌令牌，禁止硬编码 hex / rgba（手写 tint、品牌漂移等 P1/P2/P3 卫生债已在 `audit-report.md` 清零）。
3. **原型/文档/Style Guide 的内联 `:root` 必须与 `_variables.css` 对齐**，由 `check_tokens.py` 门禁保证（见 §3）。
4. **表面专用 token 集中定义**：落地页等表面的扩展令牌（`--space-*`、`--container`、`--gradient-ds` 等）只在对应扩展块声明，命名空间自解释，不污染 base。

---

## 3. 防漂移机制（已生效）

**`design-system/check_tokens.py`**
- 解析 `_variables.css` 的 `:root` 为权威字典（解析 `var()` 链）。
- 对每个消费者 HTML 提取内联 `:root`，解析其 `var()` 链后与权威做**值级比对**（归一化：去空格/换行、渐变默认停靠位 `0%`/`100%` 视为冗余）。
- 同名 token 值不同 → **DRIFT**；仅存在于一侧 → 扩展(EXT)/子集(SUB)，预期不报。
- 退出码：`0` = 零漂移；`1` = 有漂移；`2` = 解析失败。

**运行**
```bash
python design-system/check_tokens.py
```

**收口现状（2026-07-13）**
```
[canonical] _variables.css :root 解析到 113 个令牌
[OK] public/showcase/MARS-408_dachuang_deck.html     (对齐 29 · 扩展 0)
[OK] public/showcase/MARS-408_dashboard.html         (对齐 28 · 扩展 1)
[OK] public/showcase/MARS-408_official_site.html     (对齐 30 · 扩展 1)
[OK] public/showcase/MARS-408_softwarecup_landing.html(对齐 32 · 扩展 7)
[OK] design-system/showcase.html                     (对齐 70 · 扩展 7)
=== 零漂移 (ZERO DRIFT) ===
```

**修复流程**：发现 DRIFT → 判断该值应属 canonical 还是表面扩展 → 改 `_variables.css`（或改原型扩展块）→ 重跑至退出码 0。

---

## 4. 可选增强（未做，按需）

若要将原型从"自包含拷贝"升级为"运行时单一源"，可在构建期抽取 `_variables.css` 的 `:root` 注入原型 `<style>`（保持自包含的同时消除拷贝）。当前采用 **自包含 + `check_tokens.py` 门禁** 已足够防漂移，暂不引入构建耦合。

---

## 5. 相关资产

- `src/assets/styles/_variables.css` — **权威源**
- `DESIGN_TOKENS.md` — 落地页生成规范（base + 扩展）
- `design-system/showcase.html` — Living Style Guide（可视化参考）
- `design-system/check_tokens.py` — 漂移门禁
- `design-system/audit-report.md` — Vue 应用侧一致性自检（10/10，零卫生债）
- `design-system/cleanup_tokens*.py` — 历史清零脚本（品牌漂移/手写 tint/死 fallback）
