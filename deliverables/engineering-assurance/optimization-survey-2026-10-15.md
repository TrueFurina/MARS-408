# 优化现状裁定 · 2026-10-15（机验版）

> 性质：对 `plans/next-steps-2026-10-14.md` 分层台账的**逐条磁盘复核**结论。
> 方法：不信计划信磁盘——每项以 grep / ls / git ls-remote / verify_metrics 实测裁定。
> 本文件只记录「与 10-14 台账的差异」与「待用户拍板项」，不重复台账原文。

## 一、台账已过期（实际已完成，勿再当待办）

| 台账项 | 10-14 状态 | **磁盘实测（2026-10-15）** | 证据 |
|---|---|---|---|
| P0-A 推送同步 | ✅ 已完成 | ✅ 仍同步（本回合又推 `648c115..538db7e`） | `ls-remote` == 本地 HEAD |
| P2-A GLM 兜底通道 | ⬜ 待办 | ✅ **已落地**：env_map 有 GLM/ZHIPU 四键 + auto 链四通道 | `config.py:503-508` / `llm_provider.py:184` |
| P1-C 班级 CSV 导出 | ⬜ 待办 | ✅ **已落地**（648c115 拼图②收尾） | `TeacherCareerView.vue` `exportDashCsv` + 走查 D 步 |
| P0-D §1.1 README 45/47 | ⬜ 未清 | ✅ **已自愈**：README 10-14 重写后 4 处统一 48 views / 87 .vue | 实测 `ls src/views`=48、`find src`=87，与 README 4 处全吻合 |
| P1-H A1 清账 | ✅ 已完成 | ✅ 确认 | `plans/current.md` 无矛盾残留 |

## 二、本回合已执行（均已提交推送，远端==本地机验）

| 提交 | 内容 | 验证 |
|---|---|---|
| `268f8d1` | 上午 Docker 三修复落库：milvus `command: ["milvus","run","standalone"]`（镜像 ENTRYPOINT=[/tini --] CMD 空，漏写则 tini 无程序可跑直接退出）/ docker_pkgbuild MSYS 路径转换（cygpath -w + MSYS_NO_PATHCONV）/ 走查脚本补 CSV 导出校验 D 步 | 7 道 pre-commit 门禁全过 |
| `e4fa014` | **P1-E 清账**：① `gomarl_bridge.py` 全仓零引用（grep 代码/CI/脚本 + 双分支核查）→ `git mv` 归档至 `archive/dead-code-2026-10-15/`（附恢复命令，可逆）；② `_build_networks` 跨模块私有 API 耦合 → `mappo_policy.py` 公开别名 `build_networks`，`career_policy.py` 优先导入公开名（ImportError 兜底旧名） | 别名同一性断言 / venv 导入冒烟 / `test_career_policy*.py` 28 passed / `verify_metrics --update` 复绿（362→361 文件、84528→84413 行） |

**P1-E 剩余风险③**（`py-server/models/` gitignore 致 CI 必降级）：现状维持——E5 模型 437MB 不入库是既定纪律，CI 走"跳过"路径可接受；如要"不降级"需服务器侧验证，非本机事项。

**工程账**：`verify_metrics.py` 本回合跑 3 次（GREEN → 漂移 → `--update` 复绿），CI 阻断项无债。

## 三、待用户拍板（本回合未动，均需一句话决策）

| # | 事项 | 选项 | 建议 |
|---|---|---|---|
| D1 | R1 部署可达性（拼图③唯一技术阻塞） | ① 校园网同网段 ② 公网托管 ③ 仅局域网演示 | ②（deploy/career-pilot 痕迹指向它）；退 ①+课内真实学生 |
| D2 | 在飞部署物 `deploy/career-pilot/` + `vite.deploy.config.ts` | ① 入库 ② 忽略保留 ③ 删除并记录重建方式 | 随 D1 ②/① → ③；确需复用 → ② |
| D9 | 演示脚本虚构百分比（`_内部参考_勿提交/演示视频脚本.md:141-142`「总体掌握度 72%/计网 45%/计组 38%」） | 改示意值 / 标注"演示示意" / 移出仓库 | 至少标注——属发生型数据近旁，留着会被误引（该目录被 honesty_scan 豁免，机检抓不到，只能人工） |
| D8 | `review_intensity` / `difficulty` 接线 | 接线 / 标注暂不支持 | 先标注"暂不支持"，待坐标口径统一 |
| D4 | B3 孤儿视图（已复核非孤儿、全部保留） | 定 views 计数口径即可 | 口径 = `ls src/views/*.vue` 实计数（当前 48），README 已吻合，**实质已闭环，只需在 decisions.md 记一句** |
| D3 | 三拼图优先级 | 赛事导向 ②③ / 产品导向 ①② | 赛事导向 ②③ |
| — | 真实试用（P1-B） | 需真实学生 + ≥1 天时间窗 | 依赖 D1；样本量须随结论引用 |
| — | 云 BaaS（P2-B） | 平台方 invalid_grant 阻塞 | 冻结本轮承诺 |

## 四、卫生事项（红线未动，待裁示）

| 项 | 状态 | 说明 |
|---|---|---|
| `Video_1790082368458_48.mp4`（95MB，根目录） | gitignored，未跟踪 | 疑似录屏素材；占磁盘但无仓库风险 |
| `py-server;D/`（空目录） | 未跟踪 | mkdir 误建残留（semicolon 事故），空目录删/留均无影响 |
| `_e2e_tmp_mdhz/` | gitignored，未跟踪 | E2E 临时产物；含 `cloud_credentials.json`（已被 ignore，无入库风险，但凭据落Temp目录建议尽快轮换） |

## 五、结论

项目健康度：**结构门禁全绿（verify_metrics GREEN / brand / token / a11y 七道钩子过 / 远端同步）/ 测试 28+ 目标集过 / 无未提交 WIP（本回合清零）**。
真正未闭环的只剩两类：**需用户拍板的决策项**（第三节）与**外部阻塞项**（平台方 / 真实学生）。代码侧可自主执行的优化项本回合已全部收口。
