# 设计令牌采用差距报告（Design Token Adoption Gap Report）

> 生成日期：2026-10-09 · 状态：冻结期审计（仅物料/文档，不改 `src/`）
> 数据源：静态扫描 `src/**`（`.vue` / `.ts` / `.css`）· 国创赛「视觉一致性」证据页数据源

---

## 0. 一句话结论

**令牌系统已经建立且高采用**——中央源 `src/assets/styles/_variables.css` 定义了完整的
spacing / text / radius / transition / accent / color 家族（`--space-2` 被引用 431 次、
`--accent-primary` 329 次、`--text-sm` 276 次）。问题**不是"无令牌"**，而是**颜色令牌被组件/
脚本绕过**：在排除令牌定义文件后，仍有 **172 处硬编码色值**（hex/rgb），集中在 `.vue`（136）
与 `.ts`（34）。其中品牌紫族 4 个拼写变体共 **65 处**应统一收敛到既有 `--accent-primary`。

---

## 1. 令牌体系现状（好底子，勿动）

| 令牌族 | 代表令牌 | 全仓引用次数 | 采用度 |
|--------|----------|--------------|--------|
| 间距 | `--space-2` | 431 | ✅ 极高 |
| 强调色 | `--accent-primary`（`= var(--color-accent)`） | 329 | ✅ 极高 |
| 字号 | `--text-sm` | 276 | ✅ 极高 |
| 字重 | `--weight-semibold` | 244 | ✅ 高 |
| 文本色 | `--text-muted` / `--color-text` 族 | 218 / 148 | ✅ 高 |
| 圆角 | `--radius-sm` | 188 | ✅ 高 |
| 过渡 | `--transition` | 188 | ✅ 高 |

`--accent-*` 家族极完整：`--accent-1…6`、`--accent-primary{-05/-10/-15/-20/-30/-dark/-hover/-solid}`、
`--accent-danger/success/info/warning/amber/blue/cyan/pink/warm/tertiary` 等 40+ 令牌。
**结论：补齐颜色令牌的使用即可，无需新建令牌体系。**

---

## 2. 真实漂移量（排除令牌定义文件后）

| 范围 | hex + rgb 字面量数 | 说明 |
|------|--------------------|------|
| `src/**` 全量 | 394 | 含 `_variables.css` |
| `src/assets/styles/_variables.css`（令牌**定义**，非漂移） | 222 | 合法，应保留 |
| **真实漂移（排除令牌定义文件）** | **172** | ⬅️ 本报告治理对象 |
| ├─ `.vue` | 136 | 主要阵地 |
| ├─ `.ts` | 34 | 多为 `stores/` 内联样式 |
| └─ 其它 `.css` | 2 | 极少 |

> 口径说明：早期粗略统计曾报"449"（hex 281 + rgb 168 直接相加且含令牌定义文件），
> 经精确复核，按"hex+rgb 合并匹配、排除 `_variables.css`"的真实漂移为 **172**。本报告以 172 为准。

---

## 3. 品牌紫族漂移（最高优先 · 一致性硬伤）

全仓品牌紫族 **4 个拼写变体共 65 处**，应统一到既有令牌 `--accent-primary`（`var(--color-accent)`）：

| 硬编码紫 | 出现次数 | 应映射令牌 |
|----------|----------|------------|
| `#7c6af2` | 33 | `--accent-primary` |
| `#6b5cdb` | 15 | `--accent-primary`（或 `--accent-primary-dark`） |
| `#8B5CF6` | 10 | `--accent-primary` |
| `#A98CDD` | 7 | `--accent-primary-light` / `--accent-1-light` |
| **合计** | **65** | — |

> 这 4 个值肉眼接近、语义相同，却散落 4 种拼写——是典型令牌漂移，也是评审最容易肉眼抓到的不一致。

---

## 4. 硬编码热点文件（TOP，排除令牌定义文件）

| 文件 | 硬编码色值数 | 类型 | 治理建议 |
|------|--------------|------|----------|
| `stores/achievementStore.ts` | 27 | `.ts` | **最高优先**：TS 内联样式完全绕过 CSS 令牌，应在 TS 里引用令牌或改为 class |
| `views/DesignSystemView.vue` | 23 | `.vue` | ** ironic 反例**：设计系统演示页自身硬编码，应率先改成令牌示范 |
| `components/TcpHandshakeAnimation.vue` | 21 | `.vue` | 动画组件，色值固化在逻辑里 |
| `components/KnowledgeGraph.vue` | 15 | `.vue` | 图可视化，色板建议抽成令牌常量 |
| `views/ProfileView.vue` | 11 | `.vue` | |
| `views/DashboardView.vue` | 9 | `.vue` | |
| `views/AssessmentView.vue` | 7 | `.vue` | |
| `components/KnowledgeGraph3D.vue` | 7 | `.vue` | 3D 图色板 |
| `views/TeacherLiteracyReportView.vue` | 6 | `.vue` | |
| `components/icons.ts` | 6 | `.ts` | 图标颜色 |

---

## 5. 治理建议与冻结期处置

### 现在（10-28 前）· 仅物料/文档
- 本报告即可作为国创赛「视觉一致性 / 设计系统成熟度」证据页的**过程证据**。
- 在 `DesignSystemView.vue` 旁补一段说明：令牌体系已建成、当前为采用收口阶段。

### 10-28 窗口 · 可落地修复
1. **紫族归一**：把 4 个紫变体（65 处）替换为 `--accent-primary*` 系列——覆盖面广、风险低、收效直观。
2. **TS 内联样式改造**：`achievementStore.ts`（27 处）改为引用令牌或 class，彻底消除 `.ts` 源头漂移。
3. **热点 `.vue` 替换**：`DesignSystemView` → `TcpHandshakeAnimation` → `KnowledgeGraph*` 顺序替换，每改完跑一次 `npm run build` 确认无回归。

### 防回归（建议新增机检）
- 新增 `scripts/token_scan.py`：扫描 `src/**` 硬编码 hex/rgb（排除 `_variables.css` 与显式白名单），
  命中即告警；待 10-28 后接入 CI，阻断新增硬编码色值。可与现有 `brand_scan.py` 同档。
- 白名单需包含：合法的 `transparent`/`currentColor` 引用、第三方库样式、动画 keyframe 内必要的色值。

---

## 6. 核对口径（审计纪律）

- 漂移数 **172** = 全量 394 − `_variables.css` 定义 222，**非**早期误报的 449。
- 品牌紫族 **65** 处为全仓 4 变体计数，含 `_variables.css` 内少量定义；替换时仅针对组件/脚本内的硬编码，勿动令牌定义文件。
- 所有数字来自 2026-10-09 实跑静态扫描；重跑命令见 §5 防回归脚本，或 `grep -rnoE`。
