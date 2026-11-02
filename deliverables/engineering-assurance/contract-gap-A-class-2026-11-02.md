# API 响应契约缺口 · A 类可定型项的补丁规格（2026-11-02）

> 仓库：`E:\Program\MARL\study-help-pro` ｜ 分支：`merge/ws1-ws4-20261102` ｜ PR #86 → `career-literacy`
> 性质：**只读深度审计**。未修改 `py-server/` 与 `src/` 任何文件；未执行 `git add/commit/push`；未运行 `verify_metrics.py --update`；未跑 pytest（全量雷区回避）。
> 数据来源：`py-server/openapi.json`（CI 守护的运行时快照）+ `src/` 全量调用面 + 临时 DB 副本上的真实生产者调用（脚本在 `C:/Users/Lenovo/AppData/Local/Temp/contract_audit/`）。
> 所有数字均可用附录 A 的命令复跑；无法确认的项显式标「未验证」。

---

## ① 缺口总览（数字 + 命令来源）

### 1.1 权威口径（openapi 快照）

命令：

```bash
env -u PYTHONPATH -u PYTHONSTARTUP -u NODE_OPTIONS -u ELECTRON_RUN_AS_NODE \
  py-server/.venv/Scripts/python.exe scripts/audit_api_contract.py --contract-gaps
```

输出（截取首段，完整输出见脚本）：

```text
路由总数 262；有响应模型 30（11.5%）；缺口 232

=== 优先级最高：缺口且前端已用 api.*<any>() 调用（45 条）===
```

判定口径在 `scripts/audit_api_contract.py:142-158`：**不看源码有没有写 `response_model`，只看 openapi 里该操作 200 响应的 schema 是否为空对象**。因此「函数已经 `return XxxResponse(...)` 但装饰器没写 `response_model`」仍算缺口——这类恰恰是零成本修复项。

### 1.2 独立复核（AST，防止快照口径失真）

对 `py-server/api/*.py` 做 AST 统计：

| 指标 | 数值 | 说明 |
|---|---:|---|
| `api/*.py` 内路由装饰器 | 259 | 42 个文件 |
| 其中声明 `response_model=` | 30 | 与快照一致 |
| 缺口 | 229 | 259 − 30 |
| `api/` 之外注册的操作 | +3 | `/api/status`、`/api/status/competition`、`/metrics` |
| 快照总操作 | 262 | 229 + 3 = **232 缺口**，与 CLI 完全对齐 |

三条外部路由的位置：`py-server/main.py:107`（注释列出）、`py-server/app/status.py:241`（`app.get("/metrics")`）。差异来源已逐条定位，**不是快照漂移**。

### 1.3 前端 `any` 调用密度

```bash
grep -rnE "api\.(get|post|put|delete|patch)<any>" src/ | grep -v "__tests__" | wc -l   # 57
grep -rhoE "api\.(get|post|put|delete|patch)<any>\(\s*[\`'\"][^\`'\"]+" src/ \
  | sed -E "s/api\.(get|post|put|delete|patch)<any>\(\s*[\`'\"]//" \
  | sed -E 's/\$\{[^}]*\}/__/g' | sort -u | wc -l                                      # 51
```

- **57 个调用点 / 51 条去重路径**；其中 45 条落在「缺口且前端已用」清单（CLI 输出）。
- 按调用点排序的头部（`uniq -c`）：

| 调用点数 | 路径 | 裁定 |
|---:|---|---|
| 3 | `/engine/frugal-rag-full` | **C 类**（LLM 生成，见 `api/engine.py:26-29`） |
| 2 | `/rag/generate` | **已有 `response_model`**（`api/rag.py:93`），前端 any 是历史残留 |
| 2 | `/quiz/step-questions/{}` | 详情端点；**模型已存在**（`api/quiz.py:390-402`），只差装饰器 |
| 2 | `/profile/build` | **已有 `response_model`**（`api/profile.py:19`），any 是历史残留 |
| 1 | 其余 A 类候选 | 见 1.4 |

**结论：按密度硬排的 top1 是 C 类、top2/top4 已定型。** 所以「top5」不能照抄密度表，必须在 A 类内按「调用覆盖面 + 生产方 dict 可读性 + 补丁风险」重排。下面 1.4 的排序就是按此判据给出的。

### 1.4 Top 5（A 类内）

| # | 接口 | 前端调用点 | any 点数 | 生产方 | 静态性证据 |
|---|---|---|---:|---|---|
| 1 | `GET /api/subjects` | `src/stores/studyStore.ts:743` | 1 | `api/subjects.py:20` + seed 包 | 纯种子常量；29 科、643 节点、639 边，字段集合完全一致 |
| 2 | `GET /api/achievement/list` | `src/stores/achievementStore.ts:307` | 1 | `api/achievement.py:53-196` | 逐字段 append 构造；27 条成就 + `stats` |
| 3 | `GET /api/review/summary` | `src/views/ReviewView.vue:65` | 1 | `api/review.py:122-194` | **函数已返回 `ReviewSummaryResponse`**，仅缺 `response_model=` |
| 4 | `GET /api/quiz/step-questions` | `src/components/StepQuiz.vue:47`（同组件详情 71/104、答题 86） | 1 | `api/quiz.py:405-424` | 显式列表投影，9 条题目、6 个键 |
| 5 | `GET /api/teacher/students/overview` | `src/views/TeacherView.vue:27` | 1 | `api/teacher.py:19-57` | 5 个聚合标量 + 5 字段学生行；26 行真实数据 |

> 选择说明：`/api/resource/list` 同为 A 类且已给出规格（附录 C），但生产库 `learning_resources` **0 行**（临时副本实测）、仅 1 个调用点，排在下一批；`/api/quiz/step-questions/{id}` 与 `/answer` 的模型已存在，归入「零成本批次」（⑤.3）。

---

## ② Top 5 逐条补丁规格（可直接照抄）

### 2.1 `GET /api/subjects` → `SubjectsResponse`

**调用点**：`src/stores/studyStore.ts:743`，消费 `data.subjects[key].name/chapters`；前端已有同形类型 `SubjectsMap`（`src/stores/studyStore.ts:128-130`）。

**产出方**：

- `py-server/api/subjects.py:17-20`：
  ```python
  @router.get("/subjects")
  async def subjects_list(user: dict = Depends(get_current_user)):
      return {"subjects": SEED_SUBJECTS, "knowledge_graph": KNOWLEDGE_GRAPH}
  ```
- `SEED_SUBJECTS` 的合并：`py-server/seed/__init__.py:205-211`（net/ds/co/os/ai 五份 dict 合并，29 科）。
- 单科定义形状：`py-server/seed/net.py:378-386`（典型 `{"name": str, "chapters": list[str]}`）；其余四科同形：`seed/ds.py:139`、`seed/co.py:106`、`seed/os.py:104`、`seed/ai.py:134`。
- `KNOWLEDGE_GRAPH` 由 `seed/__init__.py` 合并派生；节点 643、边 639。

**补丁（`py-server/api/subjects.py`）**：

```python
from pydantic import BaseModel


class SubjectInfo(BaseModel):
    name: str
    chapters: list[str]


class KGNode(BaseModel):
    id: str
    label: str
    group: int


class KGEdge(BaseModel):
    source: str
    target: str


class KnowledgeGraph(BaseModel):
    nodes: list[KGNode]
    edges: list[KGEdge]


class SubjectsResponse(BaseModel):
    subjects: dict[str, SubjectInfo]
    knowledge_graph: KnowledgeGraph
```

装饰器改为：

```python
@router.get("/subjects", response_model=SubjectsResponse)
async def subjects_list(user: dict = Depends(get_current_user)):
```

**字段规格**：

| 字段 | 类型 | Optional | 默认值 | 来源 |
|---|---|---|---|---|
| `subjects` | `dict[str, SubjectInfo]` | 否 | — | `api/subjects.py:20` |
| `subjects.*.name` | `str` | 否 | — | `seed/net.py:379` 等 29 处 |
| `subjects.*.chapters` | `list[str]` | 否 | — | 同上 |
| `knowledge_graph` | `KnowledgeGraph` | 否 | — | `api/subjects.py:20` |
| `knowledge_graph.nodes[].id` | `str` | 否 | — | 643/643 实测 |
| `knowledge_graph.nodes[].label` | `str` | 否 | — | 643/643 非空 |
| `knowledge_graph.nodes[].group` | `int` | 否 | — | 643/643 为 int |
| `knowledge_graph.edges[].source` | `str` | 否 | — | 639/639 |
| `knowledge_graph.edges[].target` | `str` | 否 | — | 639/639 |

**可空核查**：

- 29 个科目的键集合为 `{name, chapters}` 的**唯一集合**（脚本输出 `all_keys {'name','chapters'}`），无 `icon/description` 等可选键。
- 节点键集合唯一 `{id,label,group}`；边唯一 `{source,target}`；`label` 空值 0 条。
- 节点 `id` 有 21 个重复（643 节点 / 622 唯一 id），但模型不做唯一性约束，不影响序列化；如果未来要加唯一校验，那是另一件事。
- 无 `.get()` 默认值、无 SQL、无 Postgres 分支（该端点纯常量）。

**实测（TestClient 走真实 FastAPI 序列化）**：

```text
/subjects: status=200 bytes=65234
dropped: NONE
added:   NONE
subjects=29 nodes=643 edges=639
```

模型校验开销：`SubjectsResponse.model_validate(raw)` 平均 **3.74 ms/次**（20 次循环，本机；未做生产压测）。

---

### 2.2 `GET /api/achievement/list` → `AchievementListResponse`

**调用点**：`src/stores/achievementStore.ts:307`；读取 `achievements[].{id,icon,category,color,unlocked,unlockedAt,progress,progressLabel}`（`src/stores/achievementStore.ts:316-322`）。前端类型 `Achievement` 在 `src/stores/achievementStore.ts:6-23`，`category` 是 5 值联合。

**产出方**：`py-server/api/achievement.py:53-196`。

- 已解锁分支：`api/achievement.py:75-86`，含 `unlocked=True`、`unlockedAt=saved_achievements[ach_id].get("unlockedAt")`（可能为 `None`）、`progress=100`、`progressLabel="已解锁"`。
- 未解锁分支：`api/achievement.py:155-165`，**不含 `unlockedAt` 键**；`progress=round(progress, 1)`（float）。
- 聚合：`api/achievement.py:187-196`；`stats` 是 `{"totalQuestions", "totalCorrect", **saved_stats}`（`194`）。`saved_stats` 的全部写入键在 `api/achievement.py:209-242`（15 个键，含 `subjectsCovered: list[str]`）。
- `ACHIEVEMENTS` 定义：`api/achievement.py:16-44`；`category` 实测取值恰为 `milestone/practice/knowledge/streak/master`（各 5/7/5/5/5 条），与前端联合类型一致。
- 成就总数 27（`total = len(ACHIEVEMENTS)`，`api/achievement.py:188`）。

**补丁（`py-server/api/achievement.py`）**：

```python
from typing import Any, Literal, Optional

AchievementCategory = Literal["milestone", "practice", "knowledge", "streak", "master"]


class AchievementItem(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    category: AchievementCategory
    color: str
    unlocked: bool
    unlockedAt: Optional[str] = None
    progress: float
    progressLabel: str


class AchievementListResponse(BaseModel):
    total: int
    unlocked_count: int
    achievements: list[AchievementItem]
    stats: dict[str, Any]   # 关键：saved_stats 是动态键，不能窄化成固定键集合
```

装饰器改为：

```python
@router.get("/list", response_model=AchievementListResponse)
async def get_achievements(user: dict = Depends(get_current_user)):
```

**字段规格**：

| 字段 | 类型 | Optional | 默认值 | 来源 |
|---|---|---|---|---|
| `total` | `int` | 否 | — | `api/achievement.py:188` |
| `unlocked_count` | `int` | 否 | — | `185`、`189` |
| `achievements` | `list[AchievementItem]` | 否 | — | `190` |
| `achievements[].id` | `str` | 否 | — | `76`/`156` |
| `achievements[].name` | `str` | 否 | — | `77`/`157` |
| `achievements[].description` | `str` | 否 | — | `78`/`158` |
| `achievements[].icon` | `str` | 否 | — | `79`/`159` |
| `achievements[].category` | `Literal[...]`（5 值） | 否 | — | `80`/`160` |
| `achievements[].color` | `str` | 否 | — | `81`/`161` |
| `achievements[].unlocked` | `bool` | 否 | — | `82`/`162` |
| `achievements[].unlockedAt` | `Optional[str]` | **是** | `None` | 仅 `83`（已解锁分支） |
| `achievements[].progress` | `float` | 否 | — | `84`（int 100）/`163`（round→float） |
| `achievements[].progressLabel` | `str` | 否 | — | `85`/`164` |
| `stats` | `dict[str, Any]` | 否 | — | `191-195` |

**可空核查**：

- `unlockedAt` **必须 Optional**：已解锁但 `saved_achievements[id]` 没有 `unlockedAt` 时返回 `None`（真实夹具里 `profile_built/first_chat/...` 即如此）；未解锁分支根本没有这个键。
- `stats` **必须 `dict[str, Any]`**：`saved_stats` 是用户画像 JSON 的原样展开，键集合随 `POST /achievement/record` 的事件类型变化（`api/achievement.py:209-242`）。若写成固定字段模型，所有未登记键会被**静默丢弃**。
- `progress` 用 `float` 会把已解锁的 `100`（int）序列化为 `100.0`；前端类型是 `number`，无影响。若要严格保形，可写 `int | float`（Pydantic v2 smart union 会保留原类型），但 OpenAPI 会变成 `anyOf`，收益不大。
- `category` 用 Literal 的风险：未来新增类别而未同步联合类型 → 响应校验 500。若不想承担，降级为 `str`，代价是生成类型不再收窄。**建议保留 Literal**，并加一条断言 `{a["category"] for a in ACHIEVEMENTS} <= set(get_args(AchievementCategory))`。

**实测**：

```text
/achievements: status=200 bytes=5761
dropped: NONE
added:   achievements[].unlockedAt   （27 条未解锁成就各补一个 null）
demo: 27 条成就 / stats 2 键
夹具: stats 15 键全部保留；unlockedAt 同时出现 ISO 字符串与 null
```

---

### 2.3 `GET /api/review/summary` → `ReviewSummaryResponse`（零成本）

**调用点**：`src/views/ReviewView.vue:65`（整个 `res` 赋给 `summary`）。

**现状**：**函数已经返回 Pydantic 实例**（`api/review.py:186-194`），模型定义在 `api/review.py:19-47`；但装饰器 `api/review.py:122` 没有 `response_model`，所以 openapi 200 schema 仍是 `{}`。

**补丁（仅一行）**：

```python
@router.get("/summary", response_model=ReviewSummaryResponse)
async def get_review_summary(user: dict = Depends(get_current_user)):
```

**字段规格**（模型已存在，无需新增）：

| 字段 | 类型 | Optional | 默认值 | 来源 |
|---|---|---|---|---|
| `total_questions` | `int` | 否 | — | `api/review.py:187` |
| `total_wrong` | `int` | 否 | — | `188` |
| `overall_accuracy` | `float` | 否 | — | `189`（`round(...,2)`） |
| `by_subject` | `list[SubjectSummary]` | 否 | — | `190`；元素定义 `31-37` |
| `weak_topics` | `list[str]` | 否 | — | `191` |
| `wrong_questions` | `list[WrongQuestion]` | 否 | — | `192`；元素定义 `19-28` |
| `recommendation` | `str` | 否 | — | `193` |

**可空核查**：

- `get_quiz_history` 只返回 4 个键：`subject/correct/difficulty/timestamp`（`db/profile_store.py:137-150`）。`question/user_answer/correct_answer/hint` 全部走 `record.get(..., "")`，`error_type` 走 `record.get("error_type","unknown")`（`api/review.py:149-155`）——**永远是 str，不会是 None**。
- `timestamp` 在库里 `TEXT NOT NULL`（`db/user_store.py:72-79`），不会为 null。
- `topic` 缺失时回退科目中文名（`api/review.py:146`），仍为 str。
- `by_subject` 为空、`wrong_questions` 为空均合法（模型接受空 list）。
- 无 Postgres 分支：`grep -rn "pg_client|postgres" db/profile_store.py db/user_store.py services/user_service.py` **零匹配**。

**实测**：31 条答题记录 / 13 条错题；HTTP 200 / 4,689 bytes；字段零丢弃、零新增。

---

### 2.4 `GET /api/quiz/step-questions` → `StepQuestionListResponse`

**调用点**：`src/components/StepQuiz.vue:47`（列表）；同组件 `71`、`104` 调详情，`86` 调答题——这三处是同一屏的连锁 any，适合同批收口。

**产出方**：`api/quiz.py:405-424`：

```python
return {
    "questions": [
        {"id": q.id, "subject": q.subject, "chapter": q.chapter,
         "difficulty": q.difficulty, "question_text": q.question_text,
         "step_count": len(q.steps)}
        for q in questions
    ],
    "total": len(questions),
}
```

数据源 `STEP_QUESTIONS` 来自 `engines/quiz_engine.py`（`api/quiz.py:17` 导入），实测 9 条。

**补丁（`py-server/api/quiz.py`，放在 `StepQuestionResponse` 之后、路由之前）**：

```python
class StepQuestionItem(BaseModel):
    id: str
    subject: str
    chapter: str
    difficulty: str
    question_text: str
    step_count: int


class StepQuestionListResponse(BaseModel):
    questions: list[StepQuestionItem]
    total: int
```

装饰器改为：

```python
@router.get("/step-questions", response_model=StepQuestionListResponse)
async def get_step_questions(subject: str = "", user: dict = Depends(get_current_user)):
```

**字段规格**：

| 字段 | 类型 | Optional | 默认值 | 来源 |
|---|---|---|---|---|
| `questions` | `list[StepQuestionItem]` | 否 | — | `api/quiz.py:412-422` |
| `questions[].id` | `str` | 否 | — | `414` |
| `questions[].subject` | `str` | 否 | — | `415` |
| `questions[].chapter` | `str` | 否 | — | `416` |
| `questions[].difficulty` | `str` | 否 | — | `417` |
| `questions[].question_text` | `str` | 否 | — | `418` |
| `questions[].step_count` | `int` | 否 | — | `419`（`len(q.steps)`） |
| `total` | `int` | 否 | — | `423` |

**可空核查**：9/9 条键集合唯一 `{id,subject,chapter,difficulty,question_text,step_count}`；无 Optional。`step_count` 至少 1（详情端点对 `not q.steps` 抛 500，`api/quiz.py:433-434`）。

**实测**：HTTP 200 / 2,234 bytes；9 条；零丢弃、零新增。

**同批顺手（模型已存在，只差装饰器）**：

| 接口 | 模型 | 定义 | 路由 |
|---|---|---|---|
| `GET /api/quiz/step-questions/{question_id}` | `StepQuestionResponse` | `api/quiz.py:390-402` | `427` |
| `POST /api/quiz/step-questions/{question_id}/answer` | `StepAnswerResponse` | `api/quiz.py:381-388` | `445` |

---

### 2.5 `GET /api/teacher/students/overview` → `StudentsOverviewResponse`

**调用点**：`src/views/TeacherView.vue:27`（与 `:28`、`:29` 三个 any 并行请求；本条只覆盖 `:27`）。

**产出方**：`py-server/api/teacher.py:19-57`。

- 学生行构造：`api/teacher.py:38-44`。
- 聚合：`51-57`。
- `list_all_users()` 的字段来源：`db/user_store.py:453-470`；其中 `id` 来自 `users.id TEXT PRIMARY KEY`（`db/user_store.py:58-66`），`quiz_total` 是 `len(quiz_rows)` 的 int（`459`），`quiz_accuracy` 是 `round(...,3)` 的 float（`461`）。
- 行字段：`id=u["id"]`、`name=display_name or username`、`progress=quiz_total`、`mastery=round(quiz_accuracy*100)`、`last_active=history[-1]["timestamp"][:10]`（无历史时 `"—"`）。

**补丁（`py-server/api/teacher.py`，放在 router 之后、路由之前）**：

```python
class StudentOverviewRow(BaseModel):
    id: str
    name: str
    progress: int
    mastery: int
    last_active: str


class StudentsOverviewResponse(BaseModel):
    total_students: int
    active_today: int
    avg_mastery: float
    avg_progress: float
    students: list[StudentOverviewRow]
```

装饰器改为：

```python
@router.get("/students/overview", response_model=StudentsOverviewResponse)
@cached(ttl=120)
async def get_students_overview(user: dict = Depends(require_teacher_or_demo_open)):
```

> 装饰器顺序保持 `router.get` 在最外层；`response_model` 作用于 `cached` 包装后的返回值，缓存里存的仍是 dict，每次请求做一次校验。

**字段规格**：

| 字段 | 类型 | Optional | 默认值 | 来源 |
|---|---|---|---|---|
| `total_students` | `int` | 否 | — | `api/teacher.py:52` |
| `active_today` | `int` | 否 | — | `53` |
| `avg_mastery` | `float` | 否 | — | `54`（`round(...,1)`） |
| `avg_progress` | `float` | 否 | — | `55`（`round(...,1)`） |
| `students` | `list[StudentOverviewRow]` | 否 | — | `56` |
| `students[].id` | `str` | 否 | — | `39`；库列 TEXT |
| `students[].name` | `str` | 否 | — | `40`（两级回退，兜底 `"学生"`） |
| `students[].progress` | `int` | 否 | — | `41`；`quiz_total` 恒为 int |
| `students[].mastery` | `int` | 否 | — | `42`；`round(float*100)` |
| `students[].last_active` | `str` | 否 | — | `43`；无历史时 `"—"` |

**可空核查**：

- `users.display_name` 是 `NOT NULL DEFAULT ''`（`db/user_store.py:63`），`username` 是 `NOT NULL UNIQUE`（`60`），`name` 不会 None。
- `quiz_total` / `quiz_accuracy` 由 `list_all_users` 现算（`db/user_store.py:459-461`），**不使用数据库可空列**；因此当前恒为 int/float。
- `last_active` 是字符串切片，空历史走 `"—"`，不会 None。
- 无 Postgres 分支（同上 grep 零匹配）。
- **唯一隐患**：`progress = u.get("quiz_total", 0)`。如果未来 `list_all_users` 改成直接映射可空列且值为 `None`，`.get` 会返回 `None` 而不是默认 0，Pydantic `int` 校验失败 → 500。当前实现是 `total = len(...)`，不会发生。

**实测**：26 名学生；HTTP 200 / 2,661 bytes；零丢弃、零新增；夹具学生行 `progress=3, mastery=67, last_active="2026-11-01"`。

---

## ③ 被丢弃字段核查表（模型 vs 原始 JSON）

方法：真实生产者 + 真实数据 → 候选模型 `model_validate` → 再经 FastAPI `response_model` 序列化（TestClient），双向比对键路径。**「丢弃」= 原始有、响应没有；「新增」= 原始没有、响应有。**

| 接口 | 数据 | 原始键（顶层 / 元素） | 被模型丢弃 | 被模型新增 | 类型漂移 |
|---|---|---|---:|---|---|
| `/api/subjects` | 29 科 / 643 节点 / 639 边 | 2 / 2,3,2 | **0** | 0 | 无 |
| `/api/achievement/list` | demo 27 条 / stats 2 键 | 4 / 9 或 10 | **0** | `unlockedAt: null` × 27（未解锁条目） | 已解锁 `progress: 100(int) → 100.0(float)` |
| `/api/review/summary` | 31 条记录 / 13 错题 | 7 / 6,9 | **0** | 0 | 无 |
| `/api/quiz/step-questions` | 9 条 | 2 / 6 | **0** | 0 | 无 |
| `/api/teacher/students/overview` | 26 行 | 5 / 5 | **0** | 0 | 空班级时 `avg_*: 0(int) → 0.0(float)`（本次数据非空，未触发） |
| `/api/resource/list`（附录 C） | 生产 0 行；夹具 1 行 | 3 / 10 | **0** | 0 | 无 |

补充说明：

1. `stats` 若被写成固定字段模型，**会丢弃** `saved_stats` 的 13 个扩展键；本规格用 `dict[str, Any]` 规避，夹具 15 键全部保留（实测）。
2. FastAPI 的过滤是**静默**的：小实验 `{"a":1,"b":"X"}` + `response_model` 只含 `a` → 响应 `{"a":1}`（200）。因此上表「0 丢弃」只对**当前数据**成立；未来生产者加字段不会报错，会直接消失。
3. 校验失败不是 422 而是 **500**：小实验把 `int` 字段喂成字符串 → `status 500`（`raise_server_exceptions=False`）。这是本批补丁最主要的运行时风险。
4. `subjects` 的 HTTP body 为 65,234 bytes；模型校验 3.74 ms/次。数据量级（1,282 个嵌套对象）是这批里最大的，但没有丢弃/新增。

---

## ④ 风险与回滚

### 4.1 通用机制（五条共同）

| 风险 | 说明 | 证据 |
|---|---|---|
| **收窄即过滤** | `response_model` 只输出模型声明字段；模型外字段静默消失 | TestClient 小实验：`{"a":1,"b":...}` → `{"a":1}` |
| **校验失败 → 500** | 生产者类型漂移（None/str/新增枚举）会让原本 200 的接口 500 | 小实验 `int` 喂 str → 500 |
| **openapi 快照会漂移** | 补 `response_model` 会改 `components.schemas` 与 5 个 operation；CI 的 `verify_openapi_snapshot.py` 会红 | 再生成命令写在 `scripts/verify_openapi_snapshot.py:299-302` |
| **前端类型未自动更新** | 必须重跑 `npm run types:generate`（`package.json:26`），否则 `any` 换不掉 | `package.json:26` |
| **打包物** | 快照重生成后需同步重打包，否则包内仍旧快照 | `verify_openapi_snapshot.py:303-304` |

### 4.2 逐条风险等级

| # | 接口 | 收窄面 | 触发条件 | 等级 | 回滚 |
|---|---|---|---|---|---|
| 1 | `/api/subjects` | 29 科 × 2 键；1,282 个图对象 | 未来 seed 给科目加 `icon` 等键 → 静默消失 | 🟢 | 删 `response_model=` 一处；无需回滚数据 |
| 2 | `/api/achievement/list` | 成就项 + `stats`（Any 兜底） | 新增 `category` 未进 Literal → 500；`stats` 无风险 | 🟡 | 同上；或把 `category` 降为 `str` |
| 3 | `/api/review/summary` | 已由模型产出，零收窄 | 仅多一次校验 | 🟢 | 删一处 |
| 4 | `/api/quiz/step-questions` | 已显式投影 6 键 | 未来列表要加字段 → 需同步模型 | 🟢 | 删一处 |
| 5 | `/api/teacher/students/overview` | 5+5 键 | `quiz_total` 变 None/str → 500；`mastery` 非数值 → 500 | 🟡 | 删一处 |

**为什么不是 🔴**：五条都已在真实数据上跑通、零字段丢失；风险是「未来漂移」而非「当下破坏」。真正 🔴 的是 **漏掉快照重生成** 导致 CI 假红/包内契约过期——这是流程风险，不是单条接口风险。

### 4.3 建议落地顺序与回滚步骤

1. 先落 **3（review）** 与 **4（quiz list）**：模型已存在/显式投影，改动最小，用来验证 CI 快照链路。
2. 再落 **1（subjects）**：字段最稳定，但 payload 最大，观察 3.74 ms 校验开销在生产是否可接受（未压测）。
3. 最后落 **2（achievement）** 与 **5（teacher）**：两者有聚合/动态键，先加一条「生产者形状」单测再上。
4. 每次改完必须：
   ```bash
   cd py-server && python -c "import json;from main import app;open('openapi.json','w',encoding='utf-8',newline='').write(json.dumps(app.openapi(),ensure_ascii=False,indent=2))"
   npm run types:generate
   ```
   （命令原文见 `scripts/verify_openapi_snapshot.py:299-302`；本轮**未执行**，因为红线禁止改文件。）
5. 回滚：删除对应 `response_model=` 参数即可；模型类可保留（无引用也不影响运行）。openapi 快照用 `git restore py-server/openapi.json` 回到上一版；无 DB 迁移、无前端强依赖。

---

## ⑤ 不建议动的项及理由

### 5.1 C 类：LLM/厂商输出，形状不稳定

| 接口 | any 点数 | 理由 |
|---|---:|---|
| `POST /api/engine/frugal-rag-full` | 3 | 完整 FrugalRAG（SFT + 停止决策 + 重写），输出随检索/模型变化；`api/engine.py:26-29` 明确它是 LLM 端点。定型会把「模型换了字段」变成 500。 |
| `POST /api/engine/gomarl-consensus` | 1 | GoMARL 共识，同上。 |
| `POST /api/engine/conflict-check` | 1 | 冲突检测 + 消解，同上。 |
| `POST /api/xfyun/*`（9 条） | 9 | 讯飞厂商响应透传，字段由外部服务决定。 |
| `POST /api/quiz/generate` | 1 | 含 LLM 补充（`api/quiz.py:656` 起，`require_llm_quota`），题目结构随模型变化。 |

### 5.2 B 类：状态机 / 运行时聚合

| 接口 | 理由 |
|---|---|
| `GET /api/memory/context` | 三层记忆拼装（L1/L2/L3）的上下文块，内容随会话/记忆条数变化（`api/memory.py:240-251`）；同文件的 `/overview` 已有模型，可作对照。 |
| `GET /api/career/session/{id}/report` | 报告由 `career_service.get_report` 聚合评分结果（`api/career_training.py:295-301`），字段随 rubric/会话阶段变化；属 B 类。 |
| `POST /api/career/session/start|answer|end` | 会话状态机，返回下一步/分数，形状随阶段变化。 |

### 5.3 先修前端、再补模型的项（不要现在补）

| 接口 | 问题 | 证据 |
|---|---|---|
| `GET /api/teacher/knowledge-base/stats` | 前端读 `kbStats.total_docs`，后端字段是 `total_chunks`，**永远 undefined** | 前端 `src/views/TeacherView.vue:135`；后端 `api/teacher.py:127-135` |
| `GET /api/teacher/analytics/class-performance` | 前端读 `classPerf.chapter_perf || classPerf.by_subject` 与 `classPerf.weak_areas`，后端只返回 `weakest_chapters/strongest_chapters/common_weak_points/activity_trend` | 前端 `src/views/TeacherView.vue:53`、`:156`；后端 `api/teacher.py:220-227` |

先补 `response_model` 只会把「字段名错配」固化成契约，UI 仍然空白；正确顺序是**先对齐字段名（前端或后端加别名），再补模型**。

### 5.4 零成本批次（模型已存在，只差一行装饰器）

| 接口 | 模型 | 路由 |
|---|---|---|
| `GET /api/review/summary` | `ReviewSummaryResponse`（`api/review.py:40-47`） | `api/review.py:122`（已列入 top5） |
| `GET /api/quiz/step-questions/{id}` | `StepQuestionResponse`（`api/quiz.py:390-402`） | `api/quiz.py:427` |
| `POST /api/quiz/step-questions/{id}/answer` | `StepAnswerResponse`（`api/quiz.py:381-388`） | `api/quiz.py:445` |
| `GET /api/config` | `ConfigResponse`（`models.py:11-20`） | `api/config_routes.py:35` |
| `GET /api/diagnostic/start` | `DiagnosticStartResponse`（`api/diagnostic.py:115-119`） | `api/diagnostic.py:149` |
| `GET /api/sessions/load/{conv_id}` | `SessionLoadResponse`（`api/sessions.py:38-42`） | `api/sessions.py:119` |

> 这 6 条的风险均为 🟢：函数本来只返回该模型实例（或 `questions: list[dict]` 的宽松类型），加装饰器不改变字段集合，只生成 schema。

---

## 附录 A · 复现命令

```bash
# 1) 缺口总览
env -u PYTHONPATH -u PYTHONSTARTUP -u NODE_OPTIONS -u ELECTRON_RUN_AS_NODE \
  py-server/.venv/Scripts/python.exe scripts/audit_api_contract.py --contract-gaps

# 2) any 调用点 / 去重路径
grep -rnE "api\.(get|post|put|delete|patch)<any>" src/ | grep -v "__tests__" | wc -l
grep -rhoE "api\.(get|post|put|delete|patch)<any>\(\s*[\`'\"][^\`'\"]+" src/ \
  | sed -E "s/api\.(get|post|put|delete|patch)<any>\(\s*[\`'\"]//" \
  | sed -E 's/\$\{[^}]*\}/__/g' | sort | uniq -c | sort -rn

# 3) 三条 api/ 之外的操作
#    /api/status、/api/status/competition → py-server/main.py:107
#    /metrics → py-server/app/status.py:241

# 4) 真实数据验证（临时 DB 副本 + 真实生产者）
#    C:/Users/Lenovo/AppData/Local/Temp/contract_audit/verify_models.py
#    C:/Users/Lenovo/AppData/Local/Temp/contract_audit/verify_fixture.py
#    C:/Users/Lenovo/AppData/Local/Temp/contract_audit/verify_fastapi.py
```

## 附录 B · 限制与未验证

- **未跑 pytest**：遵守全量 429/mock_auth 雷区，未执行任何测试文件；本报告的验证全部来自临时脚本（不写仓库）。
- **未重生成 openapi.json**：会改文件，违反只读红线；因此「补丁后缺口归零」是规格推演，**未在快照上实测**。
- **未做生产压测**：3.74 ms 是本机 20 次循环的平均 `model_validate` 开销，不是 HTTP p95。
- **Postgres 差异**：本批 5 条的生产者均在 SQLite（`db/user_store.py`、`db/profile_store.py`）；三文件 grep `pg_client|postgres` 零匹配，故「sqlite vs Postgres」在本批**不适用**，不是遗漏。
- **`/api/resource/list` 生产库为空**：`learning_resources` 0 行；行形状验证用的是临时副本插入 1 条符合 schema 的夹具（附录 C），不代表生产已有数据。

## 附录 C · `/api/resource/list` 备用规格（下一批）

**产出方**：`api/resource.py:61-67` → `db/user_store.py:718-741`。
**表结构**：`db/user_store.py:143-155`（仅 `quality_score REAL` 可空；其余 `NOT NULL`）。

```python
class LearningResource(BaseModel):
    id: int
    owner_user_id: str
    resource_type: str
    title: str
    content: dict[str, Any]
    quality_score: Optional[float] = None
    status: str
    visibility: str
    version: int
    created_at: str


class ResourceListResponse(BaseModel):
    status: str          # 生产方恒为 "ok"；可进一步用 Literal["ok"]
    resources: list[LearningResource]
    total: int
```

装饰器：`@router.get("/list", response_model=ResourceListResponse)`（`api/resource.py:61`）。

实测：生产 0 行 → `{"status":"ok","resources":[],"total":0}`，零丢弃；夹具 1 行（`quality_score=88.5`、`content` 嵌套 dict）零丢弃。风险 🟢（`content` 用 `dict[str, Any]`，不窄化生成内容）。
