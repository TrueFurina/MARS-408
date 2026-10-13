# 拼图② 缺口盘点：教师侧最小教学闭环（2026-10-14）

> 方法：**静态代码核查**（后端端点 + 前端调用面逐环对齐），未做真实浏览器走查（那是 B5 待办）。
> 目标闭环：**布置场景 → 学生对抗 → 自动评分 → 班级报告**。

## 一句话结论

后端与教师端**全齐**，闭环却**断在学生侧最后一米**：没有"输入任务码并带 `task_id` 发起实训"的前端入口。
后果——**教师发的任务永远收不到学生数据，班级看板恒为空**。

## 逐环核对（附 file:line 证据）

| # | 环节 | 后端 | 教师端 | 学生端 | 判定 |
|---|---|---|---|---|---|
| 1 | 建班 | ✅ `POST /career/classes`（`api/career_training.py:459`） | ✅ `TeacherCareerView.vue:54` | — | 🟢 通 |
| 2 | 导花名册 | ✅ `POST /career/classes/{id}/students`（:477） | ✅ `:72` | — | 🟢 通 |
| 3 | 布置任务（发任务码） | ✅ `POST /career/tasks`（:507，生成 6 位码） | ✅ `:104`，界面展示任务码（`:190`） | — | 🟢 通 |
| 4 | **学生凭码加入** | ✅ `POST /career/task/join`（:543） | — | **❌ 无任何入口** | 🔴 **断** |
| 5 | **带 `task_id` 发起实训** | ✅ `StartRequest.task_id`（:27，注释"教师任务（自主练习为空）"） | — | **❌ 不传**（`CareerTrainingView.vue:62` 只传 scenario_id/difficulty/max_turns） | 🔴 **断** |
| 6 | 对抗 + 自动评分 | ✅ `session/start·answer·end` + `_finish` 六维 ECD | — | ✅ 自由练习路径跑得通 | 🟡 通但不入班级 |
| 7 | 班级看板 | ✅ `GET /career/classes/{id}/dashboard`（:533） | ✅ `:122` | — | 🟡 端点通、**数据必空** |

**断点成因（连锁）**：看板的统计口径是
`WHERE s.user_id=? AND s.task_id IN (SELECT id FROM career_tasks WHERE class_id=?)`
（`db/career_store.py:511`）——只认**带 task_id 的会话**。而学生端发起会话时 `task_id` 恒为空
⇒ 即使学生做了实训，也**不会**进班级看板。

## 补齐所需的最小改动（评估，未实施）

1. **学生端任务码入口**（必需）：一个输入框 → `POST /career/task/join` → 拿到 `task_id` /
   `scenario_id` / `difficulty` / `max_turns` / `roster_bound` → 用这些参数发起实训。
2. **会话发起透传 `task_id`**（必需）：`CareerTrainingView.vue:62` 的 start 载荷补 `task_id`。
   后端无需改动（字段已就位）。
3. 学生端需要显示"这是老师布置的任务"（场景已由任务码决定，不再是自由选场景）。

> 也就是说：**这条闭环的最后一米是纯前端工作量，后端零改动**。这修正了"缺后端能力"的预判。

## 第二梯队缺口（不挡跑通，但影响"报告能不能回答教学问题"）

| # | 缺口 | 证据 | 影响 |
|---|---|---|---|
| A | **`bind_student` docstring 与实现不符** | `db/career_store.py:541` 写「**按姓名匹配**未绑定行」，实现是 `WHERE user_id IS NULL LIMIT 1`（取**第一个**未绑定行，无姓名比对） | 30 人同时凭码加入时，绑定顺序不确定 ⇒ 看板上"哪个学生是哪一行"可能**张冠李戴**；且 `roster_bound=False`（花名册人数不足）时会静默不绑定 |
| B | **看板无班级级聚合** | `career_store.class_dashboard` 仅返回 per-student `dimension_avg` / `overall_best` / `sessions[:5]` | 没有"全班最弱维度""需干预学生名单" ⇒ **不满足**路线图要求的"报告能回答教学问题" |
| C | **无班级级导出** | 只有 `GET /career/session/{id}/export-report`（学生级） | 教师无法一键导出全班成绩 |
| D | 学生加入后与花名册的**姓名绑定无校验** | 同 A | 看板里 `bound=false` 的学生会显示为未认领 |

## 建议的最小闭环（1 场景 / 1 班）

按"能讲成一条故事"的标准，补齐 A→B 两项即可演示：

```
教师建班 → 导花名册 → 发任务（拿到任务码）
   ↓
学生输入任务码 → 发起实训（task_id 透传）→ 多轮对抗
   ↓
自动六维评分（已就绪）
   ↓
教师看板：每生六维均分 + 班级最弱维度 + 需干预学生
```

前 4 步的后端**已全部存在**；第 5 步的"班级位最弱维度/需干预"需要新增一个**聚合视图**
（不改数据模型，纯读聚合）。

## 诚实标注

- 本盘点为**静态核查**：未启动服务、未真实点击。存在"代码看着接通但运行时另有分支"的可能，
  故均附 file:line 以便复核。
- 第 6 环的"对抗+自动评分"在**自由练习**路径已被本会话的 mock/真实/混态基线验证（4 场景 × 3 模式，
  见 `py-server/experiments/results/career_baseline_结论-2026-10-13.md`）；**但那条路径不带 task_id**，
  与班级看板无关。
- 未评估工作量（不排期）；未涉及教师身份获取路径（`_require_teacher` 要求 `role ∈ {teacher, admin}`，
  `career_training.py:67`）——teacher 账号如何产生不在本盘点范围。
