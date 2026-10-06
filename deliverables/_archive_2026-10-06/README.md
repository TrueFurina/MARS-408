# 归档说明（2026-10-06）

本目录存放**已被取代、但保留可追溯**的旧交付物。请勿从这里取件提交。

| 文件 | 为何归档 |
|------|----------|
| `作品演示PPT-最终版.pptx` | 2026-08-29 的 **12 页 408 考研老片**：实测「芒得很职」0 次、「国创赛」0 次、「职业素养」0 次，而旧串 MARS 13 次、408 16 次。与当前主线完全不符，因其与新交付件**同名**（`作品演示PPT-最终版.pptx`）易造成取件陷阱，故移出 `deliverables/` 根目录。 |

## 当前有效件在哪

| 用途 | 路径 | 规格 |
|------|------|------|
| 对外提交件 | `submission/01_演示PPT/作品演示PPT-最终版.pptx` | 11 页，国创赛主线 |
| 物料线留档 | `deliverables/芒得很职-国创赛路演PPT-5分钟黄金路径.pptx` | 与上者同源 |

两份均由 `deliverables/build_roadshow_pptx.py` 生成，口径一致
（芒得很职 / 国创赛·高教主赛道·创意组 / 244 operations / 227 paths /
默认集 1389 → 1178 passed / 覆盖率 54.96% / 共识分 7.0446）。

## ⚠️ 相关陷阱：`scripts/make_roadshow_ppt.py` 会重新生成 408 老片

该脚本（旧名，git 跟踪）末尾硬编码输出到**已归档的旧路径**：

```python
OUT = r"E:/Program/MARL/study-help-pro/deliverables/作品演示PPT-最终版.pptx"
```

若有人运行它，会把 408 老片重新生成回 `deliverables/` 根目录，绕过本归档。
**当前主线请只用 `deliverables/build_roadshow_pptx.py`。**
（该脚本的去留待定，本轮未改动。）
