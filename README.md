# 演算室

输入数学或计算机问题，生成可交互的教学页面。预览在浏览器沙箱中运行。首页的「二次函数参数」和「递归调用栈」是预置案例，无需模型密钥。

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

打开 [演算室](http://127.0.0.1:5173)。选择「二次函数参数」并将滑块从正数拖到负数，可以观察开口改变。返回首页打开「递归调用栈」，单击「下一步」直到返回 24，再点「重置」。

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

点击「开始练习」生成 10–15 道选择题。出题模型初审、程序校验均通过后即可作答。提交后可看解析，刷新可继续作答。正确率严格大于 90% 才通过。报告可带着薄弱点回到原演示，也可以重新练习。

SQLite 默认保存在项目的 `.local/quiz.sqlite3`。从 E 盘工作区运行时，数据库位于 E 盘。可在 `.env` 中用 `QUIZ_DB_PATH` 指定其他位置。匿名练习关联当前浏览器的学习会话与演示版本。

「质疑此题」使用独立审核服务，在 `.env` 填写 `REVIEW_MODEL_BASE_URL`、`REVIEW_MODEL_API_KEY` 和 `REVIEW_MODEL_NAME` 后重启后端。审核确认有误时，只替换这一题，其余作答继续有效。常规问答、出题和判分使用已有配置即可。

审核也可以使用 DeepSeek 官方 Flash，地址为 `https://api.deepseek.com`，模型名为 `deepseek-flash`。出题与复核使用各自的密钥和提示词。

## 验证

以下命令在未启动开发服务器时运行。浏览器测试会自动启动前后端，需要本机安装 Microsoft Edge。

```powershell
npm.cmd run build
.\.venv\Scripts\python.exe -m pytest -q
$env:Path = (Join-Path (Get-Location) '.venv\Scripts') + ';' + $env:Path
npm.cmd run test:browser
```

API 测试使用模拟上游。浏览器测试覆盖两个预置案例、错误重试、跨预览消息、沙箱隔离，以及新版自动切换、加载失败后保留原画布、刷新后回退。现场模型联调需要有效的服务配置。等待超时只用于界面反馈，浏览器沙箱不会为脚本提供执行时间配额。

## AI 协同开发记录

- [动态生成与隔离预览](docs/ai-iterations/01-lesson-preview.md) · 原始对话与验收
- [对话修改与版本管理](docs/ai-iterations/02-revision-versions.md) · 设计原文与实施验证
- [选择题与按需审核](docs/ai-iterations/03-quiz-review.md) · 设计决策与实施验证
