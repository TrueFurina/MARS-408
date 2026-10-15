# 归档：gomarl_bridge.py（2026-10-15）

## 归档原因（P1-E 风险①：死代码）

`py-server/engines/gomarl_bridge.py` 经全仓核查确认**零引用**：

- `grep -rn "gomarl_bridge" --include="*.py" --include="*.yml" --include="*.sh" .`
  （排除文件自身、node_modules、.git）→ **命中 0**
- 双分支核查：`career-literacy`（当前）与 `main` 均无任何 import / 动态导入 / 测试引用
- 该模块原设计为桥接外部科研项目 `E:/Program/MARL/GoMARL-main` 的训练管线，
  但生产链路（`agents/career_nodes.py` / `engines/career_policy.py` 等）从未接入

## 归档方式

`git mv`（非删除）——完整历史保留在 git 中，随时可恢复：

```bash
git mv archive/dead-code-2026-10-15/gomarl_bridge.py py-server/engines/gomarl_bridge.py
```

## 恢复前提

若未来 GoMARL 科研管线确需与推理引擎打通，恢复前应先评估：
当前 `engines/career_policy.py` 已自建 MAPPO 网络构建路径（经 `mappo_policy.build_networks`
公开别名），与该桥接模块职责重叠。
