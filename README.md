# 可视化理论中心

输入数学或计算机问题，生成可交互的教学页面。预览在浏览器沙箱中运行。

## 10 分钟本地体验

准备 Node.js 24、npm 11、Python 3.11 和浏览器。本项目在 Windows、Node.js 24.18.0、npm 11.16.0、Python 3.11.9 和 Microsoft Edge 上验证。

在仓库根目录打开 PowerShell，安装锁定的依赖。

```powershell
npm.cmd ci
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

在第一个终端启动后端。

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

在第二个终端启动前端。

```powershell
npm.cmd run dev
```

打开 [可视化理论中心](http://127.0.0.1:5173/)。配置下方的模型服务后，输入「用滑块展示二次函数参数变化」，点击「生成演示」。

## 实时生成

复制模板并在本机编辑 `.env`。

```powershell
Copy-Item .env.example .env
```

| 变量 | 填写方式 |
| --- | --- |
| `MODEL_BASE_URL` | 服务商的 Chat Completions 兼容基础地址，例如 `https://api.example.com/v1`。后端自动追加 `/chat/completions`。本机服务允许使用回环 HTTP 地址 |
| `MODEL_API_KEY` | 服务商颁发的密钥 |
| `MODEL_NAME` | 接口接受的模型名称 |

使用 DeepSeek 官方 V4.1-Flash 时，地址填写 `https://api.deepseek.com`，模型名填写 `deepseek-flash`。后端会对官方地址启用 JSON 输出，并使用非思考模式生成交互代码。 [DeepSeek 官方模型列表](https://api-docs.deepseek.com/api/list-models/)

重新启动后端，在首页提交「用滑块展示两个二维向量相加，并画出平行四边形」。实时结果标记为「实时生成」。问题不明确时，可按提示返回补充条件。接口错误时，学习页保留输入，可重试。模型需要在 `choices[0].message.content` 中返回约定的 JSON 文本。

密钥仅由后端读取。`.env` 已加入 Git 忽略列表。构建时使用仓库里的 `package-lock.json` 和 `requirements.txt`。

## 对话修改与版本历史

在学习页输入一条修改意见并发送。后端把原始问题、修改意见和当前版本交给模型。新版在隔离运行区加载，收到就绪信号后自动显示并保存。请求或新版加载失败时，画布继续显示当前版本。

浏览器保存最近一次学习的版本和当前版本指针。刷新学习页后可接续，首页也有「继续上次学习」入口。版本历史可恢复旧版。对话列表保留在当前学习页。生成新版需要模型配置，恢复历史版本可离线操作。

## 学习问答与练习

进入演示后，在「问原理」中输入问题，可附一张不超过 5 MiB 的 PNG、JPEG 或 WebP 截图。问答引用当前演示与近期对话，图片随本次请求发送给模型。

点击「开始练习」生成 2 道选择题，一道单选、一道多选。出题模型初审、程序校验均通过后即可作答。提交后可看解析，刷新可继续作答。答错或提交「我不清楚」后，须在同一轮答对三道巩固题再继续。主练习正确率达到 90% 即通过，两道都答对为 100%。报告可带着薄弱点回到原演示，也可以重新练习。

SQLite 默认保存在项目的 `.local/quiz.sqlite3`。从 E 盘工作区运行时，数据库位于 E 盘。可在 `.env` 中用 `QUIZ_DB_PATH` 指定其他位置。匿名练习关联当前浏览器的学习会话与演示版本。

### 真题练习与个人题库

联网查找真题使用 DeepSeek 官方 Search 和 Fetch API。将检索密钥写入本机 `.env` 的 `EXAM_DEEPSEEK_API_KEY`。明确备考时，默认 `EXAM_QUIZ_MODE=debug` 生成 1 道真题与 1 道模拟题，设为 `standard` 后生成 3 道真题与 7 道模拟题。备考真题不足时，学生可以重试或选择模拟练习。

明确具体考试且题库未找到足量匹配题时才联网搜索；普通学习目标只查个人题库，不足时用模拟题。只有能从发布页核实出处、站内使用依据、原题和答案的题目才进入练习。图片版试卷从发布页提供的原始图片进行两次识别；读数、公式、选项或答案不一致时跳过。备考时若仅核实了公开来源，页面提供原卷链接，用户可重试或继续做模拟题。采用的题目随本次练习保存，以便刷新恢复。 [DeepSeek 检索文档](https://api-docs.deepseek.com/guides/search/) · [DeepSeek 图像识别](https://api-docs.deepseek.com/guides/vision/)

登录后可打开「我的试卷」，填写考试名称与科目，并同时导入试卷和参考答案。支持 PDF、Word（.docx）、JPG、PNG 和 WebP，单次最多 16 页、15 MiB。照片先读取整页题号，再从原图按重叠区域识别和核对，可处理长图和双栏。导入结果区分「可判分」「仅供复习」「待确认」。可为待确认题单独重传清晰照片及带题号的参考答案，也可在原试卷中点击「重新识别」，用相同文件名重传原卷来合并补识别出的题。源文件不会存入题库。

题库按账户隔离，存储和全文索引都在现有 SQLite 数据库内。明确具体考试时，只在目标考试和科目内查找个人题库，再联网补足；普通学习目标只查个人题库，不足时用模拟题。核验到题目时出一道真题和一道模拟题，否则直接出两道模拟题。只有可核对答案、通过相关性检查与初审的题可用于自动判分。导入题会注明「用户导入」、文件名和页码。 [SQLite FTS5 文档](https://sqlite.org/fts5.html)

「质疑此题」使用独立审核服务，在 `.env` 填写 `REVIEW_MODEL_BASE_URL`、`REVIEW_MODEL_API_KEY` 和 `REVIEW_MODEL_NAME` 后重启后端。审核确认有误时，只替换这一题，其余作答继续有效。常规问答、出题和判分使用已有配置即可。

审核也可以使用 DeepSeek 官方 Flash，地址为 `https://api.deepseek.com`，模型名为 `deepseek-flash`。出题与复核使用各自的密钥和提示词。

## 注册、登录与排行榜

注册时填写学习阶段和近期目标，已有账户在首次使用个性化前补审。可在顶部「个人设置」随时修改。目标通过审核后，模型根据资料调整演示、答疑和出题，访客使用基础版。

登录后开始的新练习参与排名。通过时，每个账户在同一学习会话最多获得 1 分。重练或修改演示都计入原会话。排行榜显示前 100 人，每页 10 人，同分并列。登录后可以查看自己的名次，榜单内的本人行会高亮。访客关闭邀请弹窗后可以浏览公开榜单。榜单内置小王和小明两个示例。

后端启动时会在原 SQLite 数据库中增量建立账户和登录会话表。旧匿名练习在访客模式下仍可查看，历史报告按新通过门槛更新。账户的最近学习会话由当前浏览器保存。

## 验证

以下命令在未启动开发服务器时运行。浏览器测试会自动启动前后端，需要本机安装 Microsoft Edge。

```powershell
npm.cmd run build
.\.venv\Scripts\python.exe -m pytest -q
$env:Path = (Join-Path (Get-Location) '.venv\Scripts') + ';' + $env:Path
$env:BROWSER_QUIZ_DB_PATH = '.local/browser-quiz-' + [Guid]::NewGuid().ToString('N') + '.sqlite3'
npm.cmd run test:browser
```

API 测试使用模拟上游。浏览器测试用确定性题材验证二次函数和递归交互、错误重试、跨预览消息、沙箱隔离，以及新版自动切换、加载失败后保留原画布、刷新后回退。现场模型联调需要有效的服务配置。等待超时只用于界面反馈，浏览器沙箱不会为脚本提供执行时间配额。

## AI 协同开发记录

> 项目现已更名为「可视化理论中心」；以下历史记录中的「演算室」为原名。

- [Codex 对话原文导出](docs/ai-iterations/04-codex-transcript.md) · 按时间排列的用户与 AI 可见消息
- [三条完整 Prompt 链](docs/ai-iterations/05-prompt-chain-index.md) · 用户修复指导、实现提交与复测入口
- [动态生成与隔离预览](docs/ai-iterations/01-lesson-preview.md) · 原始对话与验收
- [对话修改与版本管理](docs/ai-iterations/02-revision-versions.md) · 设计原文与实施验证
- [选择题与按需审核](docs/ai-iterations/03-quiz-review.md) · 设计决策与实施验证
- [照片导入与草稿确认](docs/ai-iterations/06-photo-import-drafts.md) · 一次 API 读取与确认入库
- [题库选题与开放题转换](docs/ai-iterations/07-selection-and-conversion.md) · 全量候选、10 次初审循环、标签
- [Markdown 与标签编辑](docs/ai-iterations/08-markdown-and-tag-edit.md) · 可读性修复与「保存丢失输入」
- [年级、目标与设置](docs/ai-iterations/09-profile-goals-and-settings.md) · 个性化、审核放宽、返回来源页
- [DeepSeek 会话导出（脱敏）](docs/ai-iterations/exports/deepseek-session-2026-11-13.md) · 原始用户/AI 对话与完整 exit_plan_mode 方案
- [竞赛提交清单](docs/competition/submission-checklist.md) · 仓库、提交、Prompt 链自查
