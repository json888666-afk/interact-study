# 09 年级/目标个性化、目标审核与个人设置返回

> 迭代日期：2026-11-12
> 对话工具：DeepSeek Harness
> 模型：`deepseek-flash`（真实 API 验证）
> 对应提交：`e80eddc`（后端个性化/目标审核）、`0f7ac48`（前端 profile/设置返回）
> 相关测试：`pytest -q` 71 项、`npm run test:browser` 19 项

本文记录“让可视化教学结合年级和目标”、放宽目标审核、以及个人设置保存后返回来源页的三轮迭代。

## Prompt 链

### 第 1 轮：教学要结合年级和目标

**用户：**

> 我认为在可视化教学板块 需要结合用户的年级和目标，生成更符合用户想要的信息的能力，并对这些信息完成可视化教学

**AI 诊断：**

- 链路已经通了：`LearnerProfile` → `Profile` 依赖 → `teaching_material` 把 `learner_profile` 放进生成/修改/问答/出题的模型请求；
- 但 `PROFILE_GUIDANCE` 只说“仅作为教学参考资料”，没有把不同年级/目标落到例子、难度、符号密度、交互形式上；
- 页面也看不到“本次按什么年级和目标生成”。

**AI 修改：**

- `backend/model.py` 新增 `STAGE_GUIDANCE`（幼儿园/小学/初中/高中/本科/硕士/博士），规定抽象程度、例子、符号密度、交互形式；
- 重写 `PROFILE_GUIDANCE`：`education_stage` 决定内容与交互，`goal` 决定情境/难度/备考取向；title/summary 要体现“面向 X · Y”；
- 明确“始终以用户当前问题为主”，profile 不改变问题本身和安全/格式约束；
- `src/main.tsx` 学习页 badge：`按 高中 · 用图像理解二次函数 生成`；访客显示“通用模式”；
- 首页显示“当前个人设置”并链接到修改。

**真实 API 对比（同一问题：为什么二次函数图像的开口方向由 a 决定）：**

| 小学 · 用游戏和图形理解二次函数 | 本科 · 学习二次函数与导数的联系 |
| --- | --- |
| 标题「小学也能懂：为什么 a 决定抛物线的开口方向」 | 标题「面向本科 · 学习二次函数与导数：开口方向为何由 a 决定」 |
| “小碗”、拖动滑块、a=1/−1/0 的具体数值 | 配方 f(x)=a(x−h)²+k、一阶导数 2ax+b、二阶导数、趋于 ±∞ |

结论：同一问题在真实 DeepSeek 下已明显按年级/目标改变内容与交互。

### 第 2 轮：目标审核太严格

**用户：**

> 目前对学习目标的审核太严格了，只要不写考试都不给通过。只要内容是学习相关的内容即可，不需要严格 XX 考试。只不过如目标是 XX 考试，在生成测试题目时候可以联网搜索相关的真题资料……否则不会特意去搜索真题。

**AI 诊断：**

- `GOAL_PROMPT` 把“备考考试不明确”列为 `clarify`，所以「准备期末数学考试」被要求补充具体考试；
- `practice_questions` 在 `target is None` 时仍会调用 `find_exam_questions`，普通学习目标也会触发联网真题搜索。

**AI 修改：**

- `backend/goals.py`：
  - 学习相关目标一律 `approved`，不要求写清具体考试/科目；
  - `clarify` 只用于“无法判断是否学习”（如「不明确」）；`rejected` 只用于违法/作弊/泄漏试题；
  - `exam` 仅在明确写出具体考试名称 + 科目时返回对象；「准备期末数学考试」这类 `exam: null`，不要求补充。
- `backend/quizzes.py::practice_questions`：
  - `target is None` 时直接返回本地题库结果，**不调用** `find_exam_questions`；
  - 有具体考试时才“本地优先、不足联网”。

**真实 API 验证：**

| 目标 | 结果 |
| --- | --- |
| 准备期末数学考试 | approved，`exam: null` |
| 备考成都中考数学 | approved，`exam: {"exam":"成都中考","subject":"数学"}` |
| 不明确 | 422，提示补充具体学习内容 |

**Bug：**

- 第一次真实验证「备考成都中考数学」返回 503：模型把 `exam` 输出成字符串 `"成都中考数学"`，`ExamTarget` 校验失败；
- 修复：在 `GOAL_PROMPT` 里补上对象格式 `{"exam":"考试名称","subject":"科目"}`；复测通过。

### 第 3 轮：个人设置保存后返回来源页

**用户：**

> 这一页应该写成保存个人设置，点击保存按钮后应该返回上一页，不是回到首页

**AI 诊断/修改：**

- `LearningSettings` 原来固定 `finishAuth()` → 首页；
- 顶部「个人设置」和首页「修改」链接现在带 `?from=<当前页>`；
- `LearningSettings` 读取 `from`，用 `safeReturnPath` 只允许同站 `/`、`/study`、`/leaderboard`、`/exam-library`，保存后返回来源页；
- 直接打开 `/profile` 无来源时回首页；资料未完善被拦截在 `/leaderboard` 时返回排行榜；
- 按钮文案改为「保存个人设置」；
- 个人设置页顶部提供「← 返回上一页」与「返回首页」；返回上一页复用保存用的 `returnTo`。

**验证：**

- 浏览器用例：学习页 → 个人设置 → 保存 → 回到学习页（递归调用栈）；
- 个人设置 → 返回上一页 → 学习页；个人设置 → 返回首页 → 首页；
- legacy 账号在排行榜完善资料 → 保存 → 回排行榜；
- 首页 → 个人设置 → 保存 → 回首页。

## 关键 Bug 修复记录

| 现象 | 根因 | 修复 |
| --- | --- | --- |
| 真实目标审核 503 | 模型把 exam 输出成字符串 | prompt 明确对象格式 `{"exam","subject"}` |
| 普通目标也搜真题 | `practice_questions` 对 `target=None` 仍联网 | `target is None` 直接返回本地结果 |
| 设置保存总回首页 | `finishAuth()` 默认 `/` | `?from=` + `safeReturnPath` + `finishAuth(returnTo)` |
| 设置按钮名不明确 | 旧文案「保存学习资料」 | 改为「保存个人设置」 |
| 排行榜/试卷返回总回首页 | `safeReturnLocation` 不含 `/exam-library`，且依赖 referrer | 支持 `/exam-library`、直接用 `from`；试卷页加返回按钮 |
| 个人设置无返回入口 | 页面只有表单 | 顶部增加「返回上一页」「返回首页」 |

## 落地清单

- 文件：`backend/goals.py`、`backend/model.py`、`backend/quizzes.py`、`src/main.tsx`、`src/account-pages.tsx`、`src/exam-library.tsx`、`tests/test_accounts.py`、`tests/test_exams.py`、`tests/browser/accounts.spec.ts`、`tests/browser/study.spec.ts`
- 提交：`e80eddc`、`0f7ac48`、`4463bd4`、`ada3e01`
- 验证：`pytest -q` **71 passed**；`npm run build` 通过；`npm run test:browser` **21 passed**
