# 下一位 Agent 交接日志

> 项目：可视化理论中心（interact-study）  
> 赛场：2026 第九届传智杯 · AI 创新应用挑战赛  
> 仓库：<https://github.com/json888666-afk/interact-study>（Public）  
> 项目目录：`E:\传智杯`  
> 交接时间：2026-11-14  
> 本段起点：`006cb2a`（排行榜初版完成）  
> 本段功能终点：`b32c2d3`（2.1 文档归档）  
> 当前测试：`pytest -q` 77 项、`npm run test:browser` 23 项、`npm run build` 通过

## 0. 先读什么

如果只给下一位 Agent 5 分钟，按这个顺序：

1. 本文第 2 节「本段做了什么」；
2. 第 3 节「当前实现」；
3. 第 6 节「Git 与提交」；
4. `docs/ai-iterations/05-prompt-chain-index.md` 的 11–14 条；
5. 第 8 节「环境与坑」再动手。

注意：当前会话运行时的 workspace 曾显示 `E:\competition`，但本项目实际在 **`E:\传智杯`**。所有命令请先 `Set-Location "E:\传智杯"`，不要依赖默认 cwd。

---

## 1. 项目与基线

### 1.1 技术栈

- 前端：React 19 + TypeScript + Vite 7。
- 后端：FastAPI + SQLite/FTS5。
- AI：DeepSeek Chat Completions（`deepseek-flash`）；应用内走真实 API，测试用 mock。
- 认证：Cookie session；学习者 profile、目标审核、练习、报告、积分、排行榜。
- 测试：pytest + Playwright。
- 部署/预览：Vite `5173`，FastAPI `8000`。

### 1.2 上一个 Agent 已经完成

在上一个 Agent 结束时，项目已经具备：

- 问题生成教学页、对话修改、版本管理；
- 选择题生成、初审、单题质疑、三题巩固；
- 真题检索、个人试卷导入、题库匹配；
- 登录/注册/两步引导/个人设置/学习中心；
- 排行榜、练习通过徽章、个人题库分页/宽屏；
- 10 篇 AI 迭代/对话归档文档；
- 基线状态：HEAD `006cb2a`，后端 72 项、浏览器 22 项通过。

### 1.3 本段开始时的排行榜状态

- 前三名已经有金银铜奖牌与绶带；
- 第四名之后仍是 960px 宽的三列表格（名次 / 学习者 / 积分）；
- 用户觉得表格「歪来歪去」，尤其是名字长度不同导致头像和积分不齐；
- 还没有进度条、固定名字列、10 题规则、反馈重出题、随机候选。

---

## 2. 本段做了什么（按讨论顺序）

### 2.1 排行榜：奖牌、当前积分、对齐

用户原话：

> 前三名应该用金银铜牌的徽章，在会续航里面分别标注123。且应该有金银铜的显示区分，金牌最耀眼，银牌次之，铜牌次于银牌后

> 查看名次前的分数应该写成：当前积分：0分

> 名次 学习者 积分。这三个表头字样太小，而且应该居中在下方的信息的位置是最合适的。当前太靠左了。

> 我想实现类似奖牌的那种徽章，不是这样的。你参考下市面上的呢。我们讨论下

> 目前这个表格里的具体学习者排列上，歪来歪去的，尤其是第二章截图里的json1的信息。需要把这部分弄得整齐一点，我认为靠左更合适一点

> 看着更奇怪了，讨论下，看看市场上已有的案例

处理结果：

- 奖牌数字 1/2/3 按**领奖台位置**显示，表格名次仍用后端真实并列名次；
- 金/银/铜材质 + 深绿短绶带；金牌最大、最亮，银次之，铜再次；
- 我的排名文案为 `当前积分：N分`；
- 做了 A/B/C 三版实际截图：
  - A：紧凑行卡片；
  - B：窄表格；
  - C：两行卡片；
- 用户选 A，但指出「中间右边留空太大」；又出 A2（窄行）和 A3（行卡片 + 进度条）；
- 最终选 **A3**：720 宽行卡片 + 相对榜首进度条；
- 进度条规则讨论：
  - 用户问「分差很大怎么办、上限多少」；
  - 确定：**当前榜首 = 100%**，非零最低 2%，0 分空轨道；
  - 后端新增 `top_points`，跨页也用全局榜首；
- 后又发现进度条起点随名字长度漂移：
  - 用户选择固定名字列；
  - 身份列固定 220px（移动 150px），长名省略并保留 `title`；
  - 用户名注册限制 2–16；登录保留 2–24 兼容旧账号；
- 本地演示积分（只写 `.local/quiz.sqlite3`，未提交）：

| 账号 | 积分 |
| --- | --- |
| json | 18 |
| json1 | 15 |
| Hub_41681738 | 12 |
| json2 | 9 |
| Hub_41711852 | 8 |
| Hub_42384438 | 7 |
| Hub_42610634 | 6 |
| Hub_43094091 | 5 |
| Hub_43668605 | 4 |
| Hub_43860054 | 3 |
| Hub_43933068 | 2 |
| Hub_44254206 | 1 |
| Demo_39865287 | 0 |

对应提交：`d77f8c0`、`bff9371`、`d11c2ba`、`006cb2a` 是基线；本段后续 `b7c277d`（进度条 + `top_points`）、`58a08d2`（固定名字列 + 用户名 2–16）。

踩坑：

- 一开始以为要对齐左右，实际根因是 960 宽 + 三列 + 中缝过大；
- Vite HMR 曾经没刷新 CSS，计算样式仍是旧值；改完 CSS 后**重启 Vite**再验；
- 头像随名字长度漂移，固定身份列后解决。

### 2.2 欢迎页：eyebrow 与交互演示标签

用户原话：

> AI 交互式学习 · 数学与计算机 这一页的这行字有点小，我觉得需要把他设置的比 把问题动起来。 小一些，比 输入一个问题，生成可以亲手拖动的教学页；看懂之后再练两道题。 大一点

> 我指的 交互演示 可拖动 这两个字样，其实当前的板块大小是合适的我感觉，你觉得呢

> 举得只需要在现有的基础上调整字体大小就好了，你觉得呢，我们讨论下

处理结果：

- 欢迎页 eyebrow：12px → 桌面 24px、移动 16px，位于副文案 17/15 与标题 82/40–60 之间；
- 字距 `.12em` → `.06em`；
- 「交互演示」12 → 14px；「可拖动」12 → 13px；
- **不换颜色、不做实心胶囊、不动卡片尺寸**（用户明确要求只调字号）。
- 提交：`d67dc81`、`6f34ade`。

### 2.3 主练习：10 题 + 2:8 真题/模拟

用户原话：

> 现在可以把我们练习题数量设置为10道题，真题和模拟题2：8的比例。如果联网搜索不到以及库里面的真题数量不够，使用模拟题补齐的方法。你觉得怎么样

> 这里我觉得从个人题库找就可以，不一定要目标考试。因为用户导入即是自己肯定是之前为这场考试准备过的考试。你觉得呢

处理结果：

- 新练习固定 10 题，目标 **2 道真题 + 8 道模拟**；
- 真题不足时 1+9、0+10，不阻断；
- 新练习不再进入 `exam_choice` 选择页；旧 `exam_choice` 存档保留兼容；
- 普通学习目标只查个人题库；明确考试目标先查目标考试题库，再用个人题库其他相关题，最后联网目标考试真题；
- 只核验到 1 道真题时保留该题，其余模拟补齐，而不是整组丢弃；
- 90% 通过线：10 题答对 9 题；
- 前端文案同步改为「十道题」；
- 提交：`43f17e5`、`8df71d9`。

关键文件：

- `backend/quiz_models.py`：`MAIN_QUESTION_COUNT=10`、`MAIN_PAST_TARGET=2`、`MAIN_SIMULATED_TARGET=8`；
- `backend/quizzes.py`：`generate_job` 统一 `simulated_count = 10 - len(past)`、`practice_questions(fallback=True)`；
- `backend/exams.py`：`exam_counts()` 固定 `(2,8)`、允许返回部分已核验真题；
- `backend/papers.py`：目标考试优先 + 个人题库其他题补足。

### 2.4 按反馈重新生成一批题

用户原话：

> 可以增加一个功能，如果用户不满意当前生成的题目，可以像系统提交反馈，系统根据用户的反馈和当前的知识点重新生成一批练习题。你觉得怎么样

> 我觉得不需要限制同一练习链生成的次数。

处理结果：

- 练习头部新增「换一批题」；
- 表单：1–500 字反馈 + 快捷标签（太难/太简单/知识点不对/太重复/题干不清楚）；
- 新批保留当前知识点、排除旧题干、仍按 2:8；
- 部分作答会清空，提示「本次练习未完成，不会获得积分」；
- 已有报告、pending review、blocked drill 时不可换题；
- **不限制次数**，没有 429；只有请求进行中禁用按钮；
- 后端 `POST /api/quizzes/{id}/regenerate`，新练习写入 `learner_feedback`；
- 旧练习保留，新练习成为当前 latest；
- 提交：`27e6152`。

### 2.5 候选题随机选择

用户原话：

> 我觉得从联网和题库里面找到的候选题目，应该采取随机选择的原则。你觉得呢

处理结果：

- 不采用完全随机直接出题；采用「随机候选池 + 模型核验」；
- 最多随机取 16 道，先洗牌再截断；
- `SystemRandom`，每次请求独立；
- 题库、联网真题、开放题、单题替换都走同一入口；
- 仍必须通过来源、答案、初审；2:8 不变；
- 新增 `backend/selection.py`；`select_questions`/`select_open_questions` 抽样后重新编号；
- 提交：`072fd76`。

### 2.6 竞赛 2.1 材料归档

用户要求：

> 把现在的新的内容提交git，内容如下  
> 2.1 代码仓库与演进记录 ... 至少 3 个核心功能迭代的完整 Prompt 链 ...

处理结果：

- 新增 4 份 Prompt 链文档（11–14）；
- 新增 DSH Prompt 快照；
- 新增 2.1 对照文档；
- 截图归档到 `docs/ai-iterations/assets/2026-11-14/`；
- 更新 `05-prompt-chain-index.md`（六条 → 十条）和 README；
- 提交：`b32c2d3`。

---

## 3. 当前实现

### 3.1 主练习

- 新练习 10 题。
- 目标 2 真题 + 8 模拟；实际：
  - 2 真 → 8 模拟；
  - 1 真 → 9 模拟；
  - 0 真 → 10 模拟。
- 明确考试：
  - 目标考试个人题库优先；
  - 个人题库其他相关题补足；
  - 不足才联网目标考试真题；
  - 再不足模拟。
- 普通学习目标：只查个人题库，不联网。
- 游客：10 模拟。
- 旧练习/旧报告不迁移，仍可读。
- 90% = 9/10 通过。

### 3.2 反馈重出题

- `POST /api/quizzes/{quiz_id}/regenerate`，body `{"feedback": "..."}`。
- 1–500 字，空/超长 422。
- 只有 `status=ready` 且没有 report、pending review、blocked drill 才能换。
- 新练习同 version、同 learning session、同 account。
- 旧题 `store.seen_stems` 排除。
- `learner_feedback` 写入模型 scope；`DRAFT_PROMPT` 要求按反馈调整难度/表述/题型/情境，避免旧题。
- 不设次数上限；无 429。
- 前端：
  - 头部「换一批题」；
  - 内联表单 + 快捷标签 + 部分作答警告；
  - 成功关闭表单、重置到第一题；失败保留反馈。

### 3.3 随机候选

- `backend/selection.py`：
  - `RNG = random.SystemRandom()`
  - `CANDIDATE_LIMIT = 16`
  - `sample_candidates(items, limit=16, rng=RNG)`：先 `shuffle` 再截断。
- `exams.select_questions` / `select_open_questions` 开头抽样。
- 测试用 `tests/conftest.py` 的 autouse 替身固定顺序；随机性由 `tests/test_selection.py` 覆盖。

### 3.4 排行榜

- 前三名：奖牌 1/2/3 + 绶带；金最大最亮，银次之，铜再次；数字按领奖台位置。
- 当前积分文案：`当前积分：N分`；未上榜显示 `暂未上榜 · 当前积分：N分`。
- 第四名起：720 宽行卡片，网格：
  - 名次；
  - 头像 + 名字（固定 220px，移动 150px）；
  - 相对榜首进度条；
  - 积分。
- 进度条：`points / top_points`，非零最低 2%，0 空轨道；`top_points` 后端返回，跨页全局。
- 用户名：注册 2–16；登录 2–24 兼容旧账号；名字超长省略 + `title`。
- 提交：`b7c277d`、`58a08d2`；基线奖牌提交 `d77f8c0`/`bff9371`/`d11c2ba`/`006cb2a`。

### 3.5 欢迎页

- eyebrow 桌面 24px / 移动 16px；
- 交互演示 14px、可拖动 13px；
- 颜色、背景、卡片尺寸不变。
- 提交：`d67dc81`、`6f34ade`。

---

## 4. 关键文件地图

### 后端

- `backend/quiz_models.py`：10 题常量、`build_quiz`、`DRAFT_PROMPT`、`learner_feedback`。
- `backend/quizzes.py`：`generate_job`、`practice_questions`、`regenerate`、`FeedbackRequest`、`exam_context`、`feedback_scope`。
- `backend/exams.py`：真题检索、`exam_counts`、`select_questions`/`select_open_questions`、候选抽样。
- `backend/papers.py`：个人题库匹配、目标考试优先 + 其他个人题。
- `backend/selection.py`：随机候选。
- `backend/quiz_store.py`：quiz JSON、报告、公开数据。
- `backend/accounts.py`：用户名校验、2–16 注册、2–24 登录。

### 前端

- `src/quiz-panel.tsx`：练习面板、反馈表单、换一批题、轮询。
- `src/quiz-api.ts`：Quiz 类型、`quizRequest`/`startQuiz`。
- `src/account-pages.tsx`：排行榜、奖牌、行卡片、用户名表单。
- `src/welcome.tsx` / `src/main.tsx`：欢迎页文案。
- `src/styles.css`：排行榜、进度条、反馈表单、欢迎页字号。

### 测试

- `tests/test_learning_quiz.py`：10 题、反馈重出题、挑战/巩固。
- `tests/test_exams.py`：2:8、真题、随机抽样入口。
- `tests/test_papers.py`：个人题库、目标考试、开放题。
- `tests/test_selection.py`：随机模块。
- `tests/conftest.py`：测试数据库 + 确定性候选替身。
- `tests/browser/learning-loop.spec.ts`：反馈表单、10 题、挑战。
- `tests/browser/accounts.spec.ts`：排行榜、用户名、试卷。

### 文档

- `docs/ai-iterations/05-prompt-chain-index.md`：十条 Prompt 链索引。
- `docs/ai-iterations/11-...`：10 题/2:8/个人题库。
- `docs/ai-iterations/12-...`：反馈重出题。
- `docs/ai-iterations/13-...`：随机候选。
- `docs/ai-iterations/14-...`：排行榜/欢迎页。
- `docs/ai-iterations/exports/dsh-session-2026-11-14-practice-redesign.md`：本段 Prompt 快照。
- `docs/competition/2.1-repository-and-ai-history.md`：2.1 对照。
- 截图：`docs/ai-iterations/assets/2026-11-14/leaderboard-progress.png`、`welcome-eyebrow.png`、`preview-labels.png`。

---

## 5. API / 数据

### 主练习

- `POST /api/quizzes`：创建/恢复；新练习 10 题。
- `GET /api/quizzes/{id}`：公开练习数据。
- `POST /api/quizzes/{id}/questions/{qid}/answer`：作答。
- `POST /api/quizzes/{id}/questions/{qid}/challenge`：单题质疑（与整批反馈不同）。
- `POST /api/quizzes/{id}/regenerate`：反馈重出题。

### 反馈请求

```http
POST /api/quizzes/{quiz_id}/regenerate
Content-Type: application/json

{"feedback": "太难了，题干太长"}
```

- 202：新练习 `generating`；
- 404：不存在/不属于 owner；
- 409：不是 ready、已有报告、pending review、blocked drill；
- 422：反馈为空或 >500 字；
- 没有 429。

### 排行榜

- `GET /api/leaderboard?page=N`
- 返回新增 `top_points`；条目仍 `username/rank/points`；`me` 含 `listed_page`。
- 积分来自 qualifies 的 learning_session 去重；同一学习会话最多 1 分。

### 无 schema 迁移

- quiz JSON 新增 `learner_feedback`（无 `regenerations`）。
- 排行榜 `top_points` 为响应字段。
- 旧 2 题练习/报告保持可读。

---

## 6. Git 与提交

### 本段提交（从基线 `006cb2a` 后）

| 提交 | 内容 |
| --- | --- |
| `b7c277d` | 行卡片 + 进度条 + `top_points` |
| `58a08d2` | 固定身份列 + 用户名 2–16 |
| `d67dc81` | 欢迎页 eyebrow 24/16 |
| `6f34ade` | 交互演示 14、可拖动 13 |
| `43f17e5` | 10 题 + 2:8 |
| `8df71d9` | 个人题库优先 |
| `27e6152` | 反馈重出题（不限次数） |
| `072fd76` | 候选题随机抽样 |
| `b32c2d3` | 竞赛 2.1 文档与 Prompt 链 |
| 交接文档提交 | 你正在读的日志 + 压缩包 |

### 基线提交（上一个 Agent）

`d77f8c0`、`bff9371`、`d11c2ba`、`006cb2a`（排行榜奖牌/绶带/对齐初版）；更早的账户、真题、试卷、Prompt 文档提交见 `git log --oneline`。

### 仓库

- `main`，GitHub Public。
- 推送代理（本机）：
  ```powershell
  git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin main
  ```
- 不要提交 `.env`、`.local/`、SQLite DB、`截图问题/`。

---

## 7. 验证命令

```powershell
Set-Location "E:\传智杯"

# 后端
.\.venv\Scripts\python.exe -m pytest -q

# 前端构建
npm.cmd run build

# 浏览器（会自己起 webServer；先停 5173/8000 避免端口冲突）
npm.cmd run test:browser
```

当前期望：

- `pytest`：77 passed
- `npm run test:browser`：23 passed
- `npm run build`：成功

最近真实 API 冒烟（访客）：10 题、全部模拟、单选/多选混合、`status=ready`。

---

## 8. 环境与已知坑

1. **项目目录**：`E:\传智杯`；运行时 workspace 曾显示 `E:\competition`，不要用相对 cwd 找项目。
2. **预览**：
   - 前端 `http://127.0.0.1:5173/`
   - 后端 `http://127.0.0.1:8000/`
   - 若 Playwright 报端口占用，先停 5173/8000。
3. **CSS HMR 可能不刷新**：排行榜/欢迎页样式改完如果计算值仍旧，重启 Vite。
4. **本地 DB 已写入演示积分**：`.local/quiz.sqlite3`；`git` 不包含。换机器会回到 0 分。
5. **测试随机性**：`tests/conftest.py` 的 autouse fixture 把 `sample_candidates` 固定为顺序，保证用例稳定；随机性由 `tests/test_selection.py` 覆盖。不要误以为生产不随机。
6. **旧提交清单文档**：`docs/competition/submission-checklist.md` 在仓库中显示为乱码（历史 UTF-8 问题），本次没有重写；以 `docs/competition/2.1-repository-and-ai-history.md` 为准。
7. **测试夹具**：大量用例使用 mock 上游；真实 API 需要 `.env` 的 key。不要让测试请求真实模型。
8. **用户名**：注册 2–16，登录 2–24；测试名 `Settings_...` 曾超长，已改 `Setting_...`。
9. **未跟踪目录**：`截图问题/` 是用户材料，未纳入本项目，不要删/提交。
10. **PowerShell 文档编码**：之前用 PowerShell trim/Out-File 曾破坏 UTF-8 文档；写文档请用文件写入工具，不要用 PowerShell 重新编码。

---

## 9. 尚未完成 / 可继续

- 竞赛视频：5–8 分钟、1080p（未做）。
- 竞赛 PDF：≤30 页（未做）。
- `submission-checklist.md` 旧文件乱码，可另起新清单或重写。
- 本地演示积分没有可重复 seed 脚本进入 git；如果评审环境需要预置榜单，可加一个 demo seed（当前仅本地 DB）。
- 没有已知的代码阻塞项。

---

## 10. 给下一位 Agent 的建议顺序

1. `git log --oneline -15`，确认 HEAD 与工作区干净。
2. 读 `docs/ai-iterations/05-prompt-chain-index.md` 的 11–14 条。
3. 跑 `pytest -q`、`npm run build`，确认基线 77/23。
4. 要做视频/PDF 时，使用 `docs/competition/2.1-repository-and-ai-history.md` 和 Prompt 链文档作为讲解线索。
5. 不要重做已定方案：
   - 10 题、2:8、个人题库优先；
   - 反馈重出题不限次数；
   - 候选随机 16 道后再核验；
   - 排行榜行卡片 + 固定名字列 + 相对榜首进度条；
   - 用户名注册 2–16、登录 2–24；
   - 欢迎页只调字号，不做大改。
6. 若修改代码，继续用细粒度提交，并在提交说明中写明测试结果。

---

## 11. 本轮用户消息摘录（按主题）

> 以下保留用户原话/关键口语，便于下一位 Agent 理解真实意图；极少数错别字未改。

### 排行榜

- 「前三名应该用金银铜牌的徽章，在会续航里面分别标注123。且应该有金银铜的显示区分，金牌最耀眼，银牌次之，铜牌次于银牌后」
- 「查看名次前的分数应该写成：当前积分：0分」
- 「名次 学习者 积分。这三个表头字样太小，而且应该居中在下方的信息的位置是最合适的。当前太靠左了。」
- 「我想实现类似奖牌的那种徽章，不是这样的。你参考下市面上的呢。我们讨论下」
- 「目前这个表格里的具体学习者排列上，歪来歪去的，尤其是第二章截图里的json1的信息。需要把这部分弄得整齐一点，我认为靠左更合适一点」
- 「看着更奇怪了，讨论下，看看市场上已有的案例」
- 「我看看实际可能的图片呢，这几个方案的，方便我选」
- 「紧凑行卡片可以，但是现在中间的右边部分留空太大了，看上去很奇怪」
- 「A3. 行卡片 + 轻进度条。这个方案是可以的，但是要是分数差距很大咋办呢，进度条可以正常显示吗。上限又是多少」
- 「1. 相对榜首，线性（推荐）」
- 「给现在这些人的附一定的积分值，方便我看效果。」
- 「我想让这些进度条从同一个起点出发，我们讨论下有没有好用的方案。我的一个想法是不显示全名，仅显示这个头像，点击头像后可以查看用户的个人信息。你觉得怎么样」
- 「但是前三名可以保留现在的设置」
- 「固定名字列的方案更好，然后在注册界面限制用户名满足2-16个字符的限制，这样系统里的用户名都在2-16个字符内。你觉得怎么样」
- 「我看看这些方案效果图」

### 欢迎页

- 「AI 交互式学习 · 数学与计算机 这一页的这行字有点小，我觉得需要把他设置的比 把问题动起来。 小一些，比 输入一个问题，生成可以亲手拖动的教学页；看懂之后再练两道题。 大一点」
- 「我觉得右侧的交互演示 的设计可以醒目一点，并且 可拖动也稍微显眼一点，你觉得呢，我们讨论下」
- 「我指的 交互演示 可拖动 这两个字样，其实当前的板块大小是合适的我感觉，你觉得呢，我们讨论下」
- 「我说的 交互演示的字体」
- 「我举得只需要在现有的基础上调整字体大小就好了，你觉得呢，我们讨论下」

### 练习与真题

- 「现在可以把我们练习题数量设置为10道题，真题和模拟题2：8的比例。如果联网搜索不到以及库里面的真题数量不够，使用模拟题补齐的方法。你觉得怎么样」
- 「这里我觉得从个人题库找就可以，不一定要目标考试。因为用户导入即是自己肯定是之前为这场考试准备过的考试。你觉得呢」

### 反馈重出题

- 「可以增加一个功能，如果用户不满意当前生成的题目，可以像系统提交反馈，系统根据用户的反馈和当前的知识点重新生成一批练习题。你觉得怎么样」
- 「我觉得不需要限制同一练习链生成的次数。」

### 随机候选

- 「我觉得从联网和题库里面找到的候选题目，应该采取随机选择的原则。你觉得呢」
- 「可以执行」

### 竞赛材料

- 「把我们讨论的所有内容，从上一个agent的基础上开始做的工作，打包一份我们的聊天日志，方便我给下一个agent传过去，让他可以快速理解我们聊了什么。」
- 2.1 要求：Public 仓库、细粒度 Git 提交、至少 3 个核心功能迭代的完整 Prompt 链（用户 Prompt、AI 修改建议、如何引导 AI 修复 Bug）。

逐字/更完整的 Prompt 链与截图见：

- `docs/ai-iterations/11-practice-ten-question-mix.md`
- `docs/ai-iterations/12-feedback-regeneration.md`
- `docs/ai-iterations/13-random-candidate-selection.md`
- `docs/ai-iterations/14-leaderboard-and-welcome-hierarchy.md`
- `docs/ai-iterations/exports/dsh-session-2026-11-14-practice-redesign.md`

---

**交接结论**：项目功能完整、测试绿色；下一步优先做竞赛视频与 PDF，不要把已确认的交互方案再重新讨论一遍。