# 07 题库选题、开放题转换与标签编辑

> 迭代日期：2026-11-12
> 对话工具：DeepSeek Harness
> 模型：`deepseek-flash`（DeepSeek 官方 Chat Completions）
> 对应提交：`5db9bcf`（题库 v2：草稿导入、全量候选、开放题转换、标签）
> 相关测试：`pytest -q` 71 项通过

本文记录这一轮“题库题目选不准”的完整 Prompt 链：用户如何指出问题、AI 如何定位、如何改、以及修 Bug 的过程。用户 Prompt 为原话（节选），AI 回复按轮次归纳。

## 背景

题库里已经导入了同一套模拟卷的 5 道题（二次函数、概率估计、因式分解、坐标、反比例函数）。开始练习后：

- 用户想要“二次函数”，实际却出了“反比例函数”；
- 开放题（填空/证明/计算）没有选项，不能直接当选择题判分；
- 选择题和开放题都只按本地词面过滤，模型看不到被过滤掉的候选。

## Prompt 链

### 第 1 轮：选题只匹配到“函数”，不是“二次函数”

**用户：**

> 目前选出来的题目不符合用户想要搜索的知识点，仅满足了函数，而用户想要的是二次函数

**AI 诊断：**

- `matching_questions` 用 FTS 召回，课程标题、问题、摘要都会生成 3-gram/2-gram；
- `EXAM_SELECT_PROMPT` 之前把 `lesson.title` 当主要依据，标题里只要有“函数”，反比例函数也会被选中；
- 需要把 `context.lesson.question`（学生实际问的知识点）作为第一依据，并明确：候选都不是该知识点时返回空。

**AI 修改：**

- `backend/exams.py`：强化 `EXAM_SELECT_PROMPT`，要求“以 context.lesson.question 的知识点为准；lesson.title 只是展示主题；候选都不是该知识点时返回 `{"questions": []}`”；
- 复测：二次函数课程选中第 8 题（二次函数），反比例函数课程选中第 11 题。

**验证：**

- `tests/test_papers.py` 的选题用例；
- 真实 DeepSeek 调用返回第 8 题，`correct=[2]`（C）。

### 第 2 轮：不用 RAG，全部候选交给 API

**用户：**

> 使用 deepseek v4flash 的 api 即可

随后进一步明确：

> 被筛选掉的选择题和开放题都需要经过 api 选择

**AI 建议：**

- 不引入向量库/RAG，避免多一套索引和召回误差；
- 本地 FTS 只负责“召回”，不再做“知识点硬过滤”；
- 选择题全部候选交 `select_questions`；开放题全部候选先交 `select_open_questions`，被选中的才转换；
- 仍然由 API 判断相关性，候选都不相关时返回空。

**落地：**

- `backend/papers.py::local_questions`：
  - 选择题：`select_questions`（失败重试 2 次）；
  - 开放题：`select_open_questions`，只对选中的题调用 `convert_to_choice`。
- `backend/exams.py`：新增 `SELECT_OPEN_PROMPT`、`OpenSelection(s)`、`select_open_questions`。
- 测试：`test_all_candidates_are_sent_to_api`、`test_open_question_rejected_by_api_is_not_converted`。

### 第 3 轮：开放题转换与“未通过初审”

**用户：**

> 为啥一直提示未通过初审，是不是非选择题转化为选择题的方式错误。我认为应该把选出来的非选择题给 api，让 api 把这个非选择题生成选择题，然后对这个进行和之前一样的初筛。你觉得呢

随后确认：

> 生成/初审循环 非常对……把 3 次上限设为 10 次吧

**AI 诊断：**

- 用户描述的流程其实**已经是当前实现**：`convert_to_choice` 把选中的开放题交给 API 生成一道单选题，再跑同一个 `initial_review`；
- 用户看到的“题目未通过初审，请重试。”来自**配套模拟题**的 `build_quiz`，不是开放题转换；
- 真实复现：反比例函数练习的 `build_quiz` 第 1 次 `quiz_review_failed`，第 2 次成功——模型输出有随机性；
- 转换失败的消息是“改写后的题目未通过复核。”，会被 `local_questions` 静默跳过，所以最终看到的是模拟题报错。

**AI 修改：**

- 新增 `initial_review_detail`，同时返回 `issues` 和初审模型的独立答案；
- `build_quiz` / `convert_to_choice` 都改成“生成 → 初审 → 把 issues + 初审答案作为 feedback → 再生成”，**上限 10 次**；
- 题库题已存在时，不再强制模拟题补齐另一种题型；
- 按用户意见，**不**保留“模拟题失败只显示题库题”的降级；10 次仍失败按原逻辑进入 `exam_choice`/`failed`。

**验证：**

- `tests/test_learning_quiz.py`：初审反馈包含“初审独立求解为 …”；
- `tests/test_papers.py`：转换重试、题库 + 单选题不再强制多选、10 次失败仍失败；
- 真实 DeepSeek：反比例函数 `build_quiz` 在 10 次循环内返回 `DRAFT_OK`。

### 第 4 轮：题目知识点可编辑

**用户：**

> 对于每个导入的题目，用户可以编辑题目类型，可以添加或者删除该题所属的类型

**AI 修改：**

- `backend/papers.py`：`QuestionTags` + `PATCH /api/exam-library/{paper_id}/questions/{question_id}/tags`；
- 规则：1–8 个标签、每个 ≤60 字；只改标签不改变 `confirmed/ready/status`；内容编辑仍会回退为草稿；
- 前端「编辑知识点」chips，支持添加、删除、datalist 建议。

**Bug（后续）：**

- 用户反馈“添加知识点不生效、删除生效”；
- 根因：`TagForm` 只有按回车才把输入加入 chips，点「保存」提交的是旧 chips；
- 修复：保存时合并待输入值、新增「添加」按钮、删空时仍可按待输入值保存；浏览器用例覆盖“输入后直接点保存”。

## 关键 Bug 修复记录

| 现象 | 根因 | 修复 |
| --- | --- | --- |
| 选到反比例函数而不是二次函数 | 选题 prompt 以 lesson.title 为主 | 以 `lesson.question` 为准，候选不相关返回空 |
| 开放题没有选项 | 开放题不能直接判分 | 先 `select_open_questions`，再 `convert_to_choice` + 初审 |
| 一直“未通过初审” | 配套模拟题初审失败，不是转换失败 | 10 次反馈重试；初审答案写入 feedback |
| 同号跨卷 section 被压成 a卷 | `draft_questions` 对 section 做了小写压缩 | 输出原始 `section`；测试用 A卷/B卷 |
| 开放题测试 FTS 主题不匹配 | 题目“因式分解”与课程“二次函数”不一致 | 用二次函数开放题/标签 |
| `invalid_model_response` 偶发 | 模型一次返回非 JSON | `local_questions` 对选择题重试，转换循环捕获 |

## 落地清单

- 文件：`backend/exams.py`、`backend/papers.py`、`backend/paper_store.py`、`backend/quiz_models.py`、`backend/paper_files.py`、`tests/test_papers.py`、`tests/test_learning_quiz.py`、`docs/ai-iterations/06-photo-import-drafts.md`
- 提交：`5db9bcf feat: draft-first paper import with AI selection and editable tags`
- 测试：`pytest -q` **71 passed**
- 真实链路：反比例函数 → 第 11 题；概率 → 第 7 题；因式分解 → 第 9 题；二次函数 → 第 8 题
