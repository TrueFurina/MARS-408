# 依赖安全审计报告（2026-10-29）

> **口径声明（先读，避免误引）**
> - 本文所有数字均为 **本机 Windows 实测**（`npm audit` / `pip-audit`），**不是 CI 口径**，也未在 Linux 上复跑。
> - 审计对象是**依赖树快照**，不是漏洞可利用性证明。可达性分级是人工判断，判断依据写在每条里。
> - 分支：`opt/frontend-security-20261029`，基线 `94ef6e7`（= `career-literacy` tip）。
> - 后端（`py-server/`）只做**只读审计**，未改动任何后端依赖声明——后端安全面属主 agent 域，见第 5 节待协调项。

---

## 1. 结论摘要

| 面 | 审计前 | 审计后 | 高危（high+critical） |
|---|---|---|---|
| 前端（npm） | 19 项 / 5 critical / 8 high | **6 项 / 3 critical / 0 high** | 13 → **3** |
| 后端（pip，本机 venv） | 112 项 / 13 个包 | 未改动（只读审计） | 见第 5 节 |

前端 high 级漏洞**已清零**；剩余 3 个 critical 全部落在**测试工具链**（不进生产包），且修复路径需要跨大版本，已书面豁免并给出触发条件。

后端 112 条中 **100 条（89.3%）是「本机 venv 未按 pyproject 下限重装」造成的陈旧状态，不是仓库声明缺陷** —— `pyproject.toml` 里已显式钉死修复版本（含 CVE 注释）。真正未被声明的只有 3 个包（filelock / certifi / setuptools），见第 5 节。

---

## 2. 前端：已修复项

修复方式统一为「semver 兼容范围内升到修复版」，未做任何大版本跃迁。

| 包 | 原 → 新 | 严重度 | 公告 | 可达性 |
|---|---|---|---|---|
| `dompurify` | 3.4.11 → **3.4.17** | critical | GHSA-p98j-92pf-mc4p 等 5 条（IN_PLACE 钩子移除后残留子树仍可执行 XSS / CUSTOM_ELEMENT_HANDLING 绕过 / SAFE_FOR_TEMPLATES 绕过） | **生产可达** —— `src/utils/markdown.ts` 直接调用 `DOMPurify.sanitize` 渲染评估报告与富文本，是本项目 XSS 的唯一净化层 |
| `vue` | 3.5.32 → **3.5.44** | high | `@vue/server-renderer` 属性名黑名单缺 CR 导致 XSS | 间接可达（SSR 路径本项目未启用，但 vue 运行时在包内） |
| `vite` | 6.4.3 → **6.4.5** | high | GHSA-698v-4r3x-3vcv 等 5 条（launch-editor 命令注入 / `fs.allow` 越界 / 自定义中间件跨源脚本执行） | 仅开发服务器（`vite dev`/`preview`），不进生产产物 |
| `postcss` | 8.5.20 → **8.5.32** | moderate | GHSA-6g55-p6wh-862q（sourceMappingURL 读任意 `.map`） | 构建期 |
| `brace-expansion` / `glob` / `nanoid` / `source-map-js` / `shell-quote` / `browserslist` / `baseline-browser-mapping` / `postcss-selector-parser` | 随 lock 更新 | critical~moderate | DoS / 命令注入 / 原型污染 | 传递依赖，均随直接依赖一并升级 |

另：**移除 `lucide-vue-next`**（depcheck 判定未使用）。核实方式不是只看 depcheck——全仓 `grep` 只命中两处**注释**里的「lucide 风格」字样，无任何 import；移除后 `vite build` 产物 hash 完全不变（`index-mqhT3C2p.js`），证明该包确实未进包。这属于供应链瘦身而非漏洞修复，单独记一笔避免被误读成安全收益。

---

## 3. 前端：剩余 6 条与豁免理由

| 包 | 严重度 | 公告 | 为什么没修 | 豁免是否成立 |
|---|---|---|---|---|
| `vitest` | critical | GHSA-82fw-gwwq-j7x9（`@vitest/mocker` 重定向 mock 路径穿越 / 任意文件读） | 唯一修复版本是 **vitest 5.0.5**，它会强制 `vite` 升到 7.x（本项目在 6.x）。属「大版本破坏性升级」，与本轮「零回归」目标冲突 | ✅ 成立：`vitest` 是 devDependency，不进生产包；触发条件是运行**不受信任的测试用例**，本仓库测试全部为自有代码 |
| `tinypool` | critical | GHSA-5gmw-xhrv-c9v3 / GHSA-85c8-ppgw-ccpr（worker 选项原型污染 → RCE） | 随 vitest 5 才能升级（vitest 3 依赖 tinypool 1.x，1.x 全系受影响，无修复版可覆盖） | ✅ 成立：同上，测试期依赖 |
| `happy-dom` | critical | GHSA-37j7-fg3j-429f 等 3 条（VM 上下文逃逸 → RCE / fetch 凭证域错配） | **实测过 21.0.4，不可用**：vitest 3.2.7 + happy-dom 21 在本机直接 `FATAL ERROR: Zone Allocation failed - process out of memory`，整个测试进程崩溃、一条用例都跑不完（回退 15.11.7 后 33 文件 235 用例全绿） | ✅ 成立：devDependency，仅测试 DOM 环境；且升级路径已被实测证否，不是「懒得升」 |
| `@vitest/mocker` | moderate | GHSA-qxg6-89mg-rqv8（未鉴权 manual mock 注册导致代码注入） | 随 vitest 5 | ✅ 同上 |
| `katex` | low | GHSA-238p-pmpm-9mq7（原型污染可绕过 `trust` 限制） | 修复需 0.18.2+，但 `@sigodenjs/marked-katex-extension@1.0.0` 的 peer 约束是 `katex >=0.16 <0.17`，升 katex 必须同时换渲染扩展 | ✅ 成立：**前提不成立** —— 该公告的利用前提是渲染不可信 LaTeX 且开启 `trust: true`；`src/utils/markdown.ts` 未设置 `trust`（KaTeX 默认 `false`），不可达 |
| `@sigodenjs/marked-katex-extension` | low | 无独立公告（其风险来自 katex） | 上游无修复版本 | ✅ 同上 |

**这三条 critical 的解除条件（写死在这里，避免以后被当成"已经没事了"）**：
当且仅当 `vite` 升到 7.x 时，同批升 `vitest@5` + `happy-dom@21`，一次清掉 `vitest` / `tinypool` / `@vitest/mocker` / `happy-dom` 四条。届时必须重跑：`vue-tsc --build`、`vitest run`、`vite build`、`vite preview` 冒烟。

### 3.1 关于「GitHub 提示 62 个 CVE」的口径说明

推送本分支时远端回显：`GitHub found 62 vulnerabilities on TrueFurina/MARS-408's default branch (9 critical, 32 high, 18 moderate, 3 low)`。

这个 **62 与本文的 19（修复后 6）不是同一口径的两个值**，不能互相"修正"：

| | Dependabot（62） | 本文 npm audit（19 → 6） |
|---|---|---|
| 扫描对象 | **默认分支**（本仓库默认分支是 `main`，即 408 那条线） | 当前分支 `opt/frontend-security-20261029` 的 `package-lock.json` 解析结果 |
| 计数单位 | 每条 advisory 计一次（同一包的多条公告分别计数） | 每个受影响**包节点**计一次（`via` 里挂着该包的全部公告） |
| 是否含 dev 依赖 | 含 | 含，但已按可达性分级 |

所以对外**不要**写「项目有 62 个 CVE」，也不要写「已清零」——正确的说法是：**当前分支的 npm audit 从 19 项降到 6 项，其中生产包内可达项为 0**；默认分支（`main`）的 Dependabot 计数（62）本轮未处理，因为 `main` 不在本 agent 的改动范围内（分支同步方向唯一：`main` → `career-literacy`，禁止反向）。

---

## 4. 复现命令

```bash
# 前端（在仓库根执行）
npm audit --json | node -e "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>console.log(JSON.stringify(JSON.parse(s).metadata.vulnerabilities)))"

# 前端未使用依赖（注意：postcss/autoprefixer 会被误报，它们在 postcss.config.js 里以字符串键引用）
npx --yes depcheck --json

# 后端（审计已安装环境；仓库无 requirements.txt，依赖声明在 py-server/pyproject.toml）
uvx pip-audit --path py-server/.venv/Lib/site-packages -f json
```

---

## 5. 后端：审计结果与待协调项（**未改动，需主 agent 决策**）

`pip-audit` 对本机 `py-server/.venv` 报告 **112 条漏洞 / 13 个包**：

| 包 | 已装版本 | 条数 | 修复版本 | 是否已在 `pyproject.toml` 声明下限 |
|---|---|---|---|---|
| pillow | 12.2.0 | 64 | 12.3.0 | ✅ `pillow>=12.3.0` |
| pyjwt | 2.13.0 | 15 | 2.15.0 | ✅ `pyjwt>=2.15.0` |
| filelock | 3.29.1 | 9 | 4.0.9 / 4.2.1 | ❌ 仅 `>=3.13.0`，修复需跨大版本 |
| mcp | 1.28.0 | 6 | 1.28.1 | ✅ `mcp[cli]>=1.28.1` |
| starlette | 1.2.1 | 4 | 1.3.1 | ✅ `starlette>=1.3.1` |
| urllib3 | 2.7.0 | 3 | 2.8.0 | ✅ `urllib3>=2.8.0` |
| anyio | 4.13.0 | 2 | 4.14.2 | ✅ `anyio>=4.14.2` |
| certifi | 2026.5.20 | 2 | 2026.10.19 | ❌ 未声明 |
| cryptography | 49.0.0 | 2 | 50.0.0 | ✅ `cryptography>=50.0.0` |
| langgraph-sdk | 0.4.2 | 2 | 0.4.4 | ✅ `langgraph-sdk>=0.4.4` |
| fsspec | 2026.4.0 | 1 | 2026.6.0 | ✅ `fsspec>=2026.6.0` |
| pydantic-settings | 2.14.1 | 1 | 2.14.2 | ✅ `pydantic-settings>=2.14.2` |
| setuptools | 83.0.0 | 1 | 84.1.0 | ❌ 构建工具，未声明 |

**判读**：112 条里 **100 条（89.3%）** 命中的是「已声明下限但本机 venv 没重装」的陈旧环境，`pip install -e .` 即可消除——**不是仓库缺陷，不要据此对外说"项目有 100 个 CVE"**。

真正需要决策的是 3 个：

1. **`filelock` 9 条**（修复需 4.x，当前约束 `>=3.13.0`）——大版本升级，需确认 `langgraph` / 本地文件锁调用点兼容性。
2. **`certifi` 2 条**——补 `certifi>=2026.10.19` 下限即可，属低风险改动。
3. **`setuptools` 1 条**——构建工具，只在装包时生效，可不动。

按分工约定（WS5/WS6 不跨域改后端），以上三条**只登记不修改**，等主 agent 在合并窗口统一处理。

---

## 6. 未纳入本次范围

- **`puppeteer-core` / `playwright`**：`scripts/e2e/*.cjs` 里引用但未进 `package.json`。这是既有的 e2e 工具约定（按需本机安装），不是本次引入的缺失，故未擅自加进依赖清单——加了会让每次 `npm ci` 多拉几百 MB 浏览器运行时。
- **后端全量依赖重装验证**：需要按 `pyproject.toml` 重装 venv 并跑全量 pytest，属主 agent 域与本机 torch `c10.dll` 环境限制范围。
