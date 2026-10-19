# P0 安全宣称独立审计报告（2026-10-19）

> 审计方式：不采信任何既有文档结论，逐条到代码取证（REA 证据纪律：结论必须带出处）。
> 审计对象：`plans/r1-decision-brief-2026-10-18.md` §「拍板前前置项实测」六条宣称 + 旧「14 个 P0」清单中的非安全项现状。
> 审计人：AI（WorkBuddy），只读审计，零代码改动。

## 一、安全项逐条取证结果

| # | 宣称 | 裁决 | 独立取证（文件:行） |
|---|---|---|---|
| 1 | 令牌签名密钥已 fail-closed | ✅ **属实** | `py-server/shared/auth.py:19-64`：硬编码旧密钥已移除（F-005）；生产缺 `AUTH_SECRET` → `RuntimeError`；dev 随机生成 + warning；**任何模式 <32 字符 → raise**（:57-61） |
| 2 | 启动期 fail-fast | ✅ **属实**（简报未列，本次补证） | `py-server/app/lifespan.py:295-304`：密钥校验在任何写操作之前，`except` 记录后**原样 raise**，不吞异常 |
| 3 | admin 口令环境注入、无硬编码默认 | ✅ **属实** | `py-server/db/user_store.py:269-278`：`ensure_admin(username, password)` 双双必填，无默认值分支 |
| 4 | PBKDF2-HMAC + compare_digest | ✅ **属实**（本次补证迭代次数） | `py-server/db/user_store.py:199-217`：`pbkdf2$sha256$600000$<salt>$<hash>`，`hmac.compare_digest` 比验；`:247` 有 `_DUMMY_HASH` 防时序探测 |
| 5 | 密钥不落盘 | ✅ **属实** | `py-server/config.py:406-425`：`_strip_secrets` 递归剥离 `_SECRET_FIELDS`，`save_config` 落盘前必经 |
| 6 | 硬编码密钥残留扫描 | ✅ **干净**（本次新增） | 全 py-server 正则扫描 `(secret\|password\|api_key\|token)\s*[=:]\s*"..."`（排除测试/dummy/占位）→ **0 命中** |
| 7 | 速率限制在位 | ⚠️ **机制属实，简报引用失实** | `py-server/api/auth.py:43-55`：注册 **20 次/小时/IP**（非 3 次），2026-10-15 真人演练校准（同一教室 NAT 出口第 4 人被拦）；登录 10 次/分 + 账户级 5 次/15 分 |

## 二、简报失实一处（不影响安全 posture）

`r1-decision-brief` 写「速率限制 ✅ 在位（README:78 宣称与实现一致）」——**该引用不成立**：

- README:78 实际是 FrugalRAG 段落，全文**没有任何限流宣称**（grep「限流/速率/每小时」0 命中）
- 实现阈值是 **20 次/小时**（10-15 从 3 次上调，代码内有完整缘由注释），不是简报暗示的 3 次

**性质**：取证链接错指 + 数字陈旧，安全机制本身比宣称更强（有真人场景校准）。建议后续引用限流时以 `api/auth.py` docstring 为准，勿引 README。

## 三、旧「14 P0」非安全项现状

| 旧 P0 项 | 现状裁决 | 取证 |
|---|---|---|
| 区块链桩代码 | ✅ **已不存在** | py-server 全目录 grep「blockchain/区块链」**0 命中** |
| AI 导师零调用 | ✅ **已接线** | `api/langgraph.py:63`（主链）+ `api/tutor.py:53`（懒加载，注释说明为何不进顶层）+ `agents/tutor_enhanced.py:12` 叠加 |
| 伪造证书 | ✅ **从未存在/已清除** | 「证书」命中均为英语词库数据（`api/english.py:44` certificate=证书）与成就系统 `api/achievement.py`，无任何伪造凭证逻辑 |

## 四、stub 现状（与台账裁定一致，无新发现）

- `db/graph_db.py` 5× `NotImplementedError`：NetLearn 时代 KG 存储，**全仓零 import**（10-17 孤儿函数审计已裁定保留，被 `agents/knowledge_graph.py` 取代）
- `engines/algorithm_factory.py` T1  stub：注释明示「T1 仅留清晰标注的 stub，真算法在 T2/T3」，被测试引用（10-14 B2 裁定保留）
- `engines/marl_dqn.py`：legacy MARL，生产 `algorithm_factory` 路径在用（B2 同裁定）

## 五、结论

1. **安全面可以宣布闭环**：六项安全机制逐条代码级证实，另补证两项（启动 fail-fast 时序、PBKDF2 迭代与防时序），密钥残留扫描干净。选 A（VPS 上线）的代码前置确已就绪。
2. **需修正的只有文档**：`r1-decision-brief` 限流一行的引用失实（README:78 错指 + 3→20 陈旧），建议改注 `api/auth.py:43`。
3. **旧「14 P0」叙事可以退役**：区块链桩/导师零调用/伪造证书三项在当前代码中分别「不存在/已接线/从未存在」——对外再引「14 个 P0」会虚增历史包袱，建议统一改述为「安全项已于 10-18 前代码级闭环（本次独立审计证实）」。

## 附：复核命令（可自行重跑）

```bash
cd E:/Program/MARL/study-help-pro
# 1) 密钥 fail-closed 三态
grep -n "AUTH_SECRET" py-server/shared/auth.py | head -6
# 2) 启动 fail-fast
sed -n '295,304p' py-server/app/lifespan.py
# 3) 限流真实阈值
sed -n '43,55p' py-server/api/auth.py
# 4) 密钥残留扫描（应 0 命中）
cd py-server && grep -rnE "(secret|password|api_key|token)\s*[=:]\s*[\"'][^\"'{}$]{8,}[\"']" --include="*.py" . | grep -vE "test_|/tests/|\.venv|dummy|example|占位"
```
