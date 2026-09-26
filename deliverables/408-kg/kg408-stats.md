# 408 知识图谱骨架 — 可引用统计（kg408）

> 本文件由 `scripts/build_kg408.py` **自动生成**，数字取自 `data/kg408/kg408.json` 真值。
>
> **防伪证（用哪条命令）**：`scripts/verify_kg408.py` **无参 = 全量**（关卡 1 结构自检 + 关卡 2 重跑逐字节比对 + 关卡 3 文档数字断言），任一不一致 → exit 1。**本项目要求以无参全量为准。**
> ⚠️ `--check-doc` 与 `--no-repro` 都是**弱模式**，仅供快速自查：`--check-doc` 只核文档数字，拦不住 `kg408_stats.json` 被篡改、拦不住 `kg408.json` 内容被改（只要数字自洽）；`--no-repro` 跳过逐字节比对，同样拦不住内容篡改。**防伪证必须跑无参全量。**

## 1. 溯源（provenance）

| 项 | 值 |
|---|---|
| 源骨架文件 | `E:/Program/MARL/SAGE/pdf/03_408知识图谱骨架.html` |
| 源骨架 sha256 | `a127702b519d54670517bf35a8b1c2ae0d2c917c4ec464d4e5e98246defcdee5` |
| 源骨架字节数 | 9995 |
| 源骨架 mtime (UTC) | 2026-09-20T15:42:37Z |
| 别名表 | `data/kg408/kg408_alias.json` |
| 别名表 sha256 | `d97bcdfe5e12c0ab8a225f3a437e90edec452d40e13235fa5f7cbfea78e3162f` |
| 章映射表 | `data/kg408/kg408_chapter_map.json` |
| 章映射表 sha256 | `f2a9e2a55c841247bc756f63e8c1d857aca65ab15070970109517b16c2aaf6ec` |
| 人工补充节点表 | `data/kg408/kg408_manual_nodes.json` |
| 人工补充节点表 sha256 | `767effe393b1d6b170a64ffd43ccfc8b17ecc8843055af923eb19fe84c8e2dc0` |
| 生成脚本 | `scripts/build_kg408.py` (v1.0.0) |
| 解析规则版本 | `kg408-parse-r1` |
| 生成命令 | `python scripts/build_kg408.py --source E:/Program/MARL/SAGE/pdf/03_408知识图谱骨架.html --out-dir data/kg408` |
| generated_at_utc | 2026-09-20T15:42:37Z |
| generated_at_utc 口径 | `source_file_mtime_utc__deterministic` |

> **全部产物刻意不含墙钟时刻**：`generated_at_utc` 取**源骨架 mtime(UTC)**，因此本文件、`kg408.json`、`unresolved.json`、`kg408_stats.json` 连跑两次**逐字节一致**（`git diff` 为空）。构建时刻不属于「结论」，不进入产物；如确需，看本次构建的 stdout 输出或 `kg408.json` 的 git 提交时间。

## 2. 核心数字（真值锚点，verify_kg408.py 逐项断言）

| 指标 | 数值 |
|---|---|
| 科目节点 | 4 |
| 章节点 | 26 |
| 考点节点 | 106 |
| 节点合计 | 136 |
| 其中·源骨架节点 | 135 |
| 其中·人工补充节点 | 1 |
| 其中·源骨架考点 | 105 |
| 其中·人工补充考点 | 1 |
| 先修边（已解析） | 14 |
| 跨科关联边（已解析） | 4 |
| 边合计 | 18 |
| 先修声明总数（源） | 23 |
| 跨科引用总数（源） | 18 |
| 未解析引用 | 17 |

> **源骨架节点 135 ≠ 节点合计 136**：差额 1 个是**人工补充节点**（学科负责人裁决补入，`origin="manual"`，见 `data/kg408/kg408_manual_nodes.json`）。两个数字**分开列出，不合并**，以便读者区分哪些来自源文档、哪些是人工判断。

## 3. 分科构成（真值锚点）

| 指标 | 数值 |
|---|---|
| DS 章数 | 8 |
| DS 考点数 | 35 |
| CO 章数 | 7 |
| CO 考点数 | 22 |
| OS 章数 | 5 |
| OS 考点数 | 21 |
| CN 章数 | 6 |
| CN 考点数 | 28 |
| 章数合计 | 26 |
| 考点数合计 | 106 |

## 4. 边的解析方式分布（真值锚点）

| resolution | 条数 |
|---|---|
| alias | 16 |
| exact | 2 |
| 边合计（resolution） | 18 |

| 依赖人工别名表的边 | 16 |
| 纯精确匹配（不依赖别名表）的边 | 2 |

> ⚠️ **口径说明**：`resolution` 取一条边**两端中最不确定的那一端**（只要任一端点靠人工别名表解析，整条边就记 `alias`）。因此 `alias=16` 与上表「依赖人工别名表的边 = 16」**是同一个数字**，不再是旧版那种「只记单端点、把 4 条靠别名解析的边误记成 exact」的误导口径。即：**16/18 条边依赖人工映射**，仅 2 条是两端都精确命中源文档原文。

## 5. 未解析引用（如实挂起，禁止模糊匹配兜底）（真值锚点）

| 指标 | 数值 |
|---|---|
| absent_in_skeleton | 11 |
| ambiguous_multi_match | 1 |
| chapter_level_only | 5 |
| 未解析合计 | 17 |
| 先修声明已解析（声明数口径） | 14 |
| 先修声明成功率(%) | 60.9 |

| 类型 | 原文 | 所在行 | 上下文 | 原因 | 建议 |
|---|---|---|---|---|---|
| prerequisite_target | `归并/快排` | 227 | 归并/快排 | absent_in_skeleton | 人工裁定：拆分为多个独立声明后重跑（本阶段**不自动拆分**），或删除该声明。 |
| prerequisite | `递归` | 227 | 归并/快排 | absent_in_skeleton | 人工裁定：补考点节点（resolution=manual），或删除该声明。 |
| prerequisite | `分治` | 227 | 归并/快排 | absent_in_skeleton | 人工裁定：补考点节点（resolution=manual），或删除该声明。 |
| prerequisite | `查找` | 235 | B 树 | chapter_level_only | 人工裁定：改为章级先修（补章级边），或补具体考点节点后重跑。 |
| prerequisite | `指令系统` | 239 | 指令流水线 | chapter_level_only | 人工裁定：改为章级先修（补章级边），或补具体考点节点后重跑。 |
| prerequisite | `资源分配` | 251 | 死锁 | absent_in_skeleton | 人工裁定：补考点节点（resolution=manual），或删除该声明。 |
| prerequisite | `队列/栈` | 255 | 页面置换 LRU | absent_in_skeleton | 人工裁定：拆分为多个独立声明后重跑（本阶段**不自动拆分**），或删除该声明。 |
| prerequisite | `数据链路层差错/流量控制` | 259 | TCP 可靠传输 | absent_in_skeleton | 人工裁定：拆分为多个独立声明后重跑（本阶段**不自动拆分**），或删除该声明。 |
| prerequisite | `流量控制` | 263 | TCP 拥塞控制 | ambiguous_multi_match | 人工裁定：补章前缀后重跑，或删除该声明。 |
| prerequisite | `滑动窗口` | 263 | TCP 拥塞控制 | absent_in_skeleton | 人工裁定：补考点节点（resolution=manual），或删除该声明。 |
| cross_subject | `页面-快表 TLB` | 300 | 散列/相联查找 | absent_in_skeleton | 人工裁定：补考点节点（resolution=manual），或删除该声明。 |
| cross_subject | `内容寻址` | 300 | 散列/相联查找 | absent_in_skeleton | 人工裁定：补考点节点（resolution=manual），或删除该声明。 |
| cross_subject | `排序` | 307 | 磁盘调度「电梯算法」 | chapter_level_only | 人工裁定：改为章级先修（补章级边），或补具体考点节点后重跑。 |
| cross_subject | `输入输出` | 307 | 磁盘调度「电梯算法」 | chapter_level_only | 人工裁定：改为章级先修（补章级边），或补具体考点节点后重跑。 |
| cross_subject | `队列/栈` | 314 | 页面置换 LRU | absent_in_skeleton | 人工裁定：拆分为多个独立声明后重跑（本阶段**不自动拆分**），或删除该声明。 |
| cross_subject | `概述-系统调用/内核态` | 321 | 中断/系统调用 | absent_in_skeleton | 人工裁定：拆分为多个独立声明后重跑（本阶段**不自动拆分**），或删除该声明。 |
| cross_subject | `排序` | 328 | 排序与流水线 | chapter_level_only | 人工裁定：改为章级先修（补章级边），或补具体考点节点后重跑。 |

> 先修声明解析成功率 60.9%（14/23 条声明；分子分母同为单位「声明」，不是「边数 ÷ 声明数」），其余全部如实挂起于 `data/kg408/unresolved.json`，并通过 `GET /kg408/unresolved` 对外可见。**未做任何模糊相似度兜底匹配。**

## 5b. 人工补充节点清单（origin=manual，非源数据）

| id | label | 挂载 | origin |
|---|---|---|---|
| `408:OS:CH04:KP05` | 磁盘调度 | OS/文件管理 | manual |

## 6. 权重口径（诚信声明）

- 源文档 §4 文字写「权重=关联强度」，但 §3 表头只有「关联/DS/CO/OS/CN」五列，**没有任何权重数值列**。
- 因此全部 18 条边的 `weight` 均为 `null`（实测 null 数 = 18），`weight_source` = `not_applicable`（先修边）/ `not_provided_by_source`（跨科边）。
- **禁止**填 0.5/1.0 假装是关联强度。
