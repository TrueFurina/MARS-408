# 成效证据状态（自动生成，勿手改）

- 数据源：`/home/user/study-help-pro/py-server/data/pg_fallback.db`
- 判据：{"real_users": 5, "finished_sessions": 10, "max_bound_class": 3, "finished_with_task": 5}（见脚本 docstring，可审计）

## 裁决

❌ **不构成成效证据** —— 当前数据**不得**作为使用规模或教学成效引用。

未满足项：
- 真实用户数 0 < 5（排除测试账号后；当前全部账号样本：[]）
- 已完成场次 0 < 10
- 单个班最多已绑定非测试学生 0 < 3
- 教师任务发起且完成的场次 0 < 5

> 诚实口径：现有记录全部来自开发/测试/基线跑批，**不是真实用户试用**。对外表述应为「尚未开展真实试用」，而非引用这些条数。

## 原始统计

| 指标 | 值 |
|---|---|
| sessions_total | 0 |
| sessions_finished | 0 |
| sessions_finished_real | 0 |
| sessions_finished_with_task | 0 |
| distinct_users_all | 0 |
| distinct_users_real | 0 |
| classes_total | 0 |
| classes_with_bound_students | 0 |
| max_bound_class | 0 |
