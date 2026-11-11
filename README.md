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

重新启动后端，在首页提交「用滑块展示两个二维向量相加，并画出平行四边形」。实时结果标记为「实时生成」。问题不明确时，可按提示返回补充条件。接口错误时，学习页保留输入，可重试。模型需要在 `choices[0].message.content` 中返回约定的 JSON 文本。

密钥仅由后端读取。`.env` 已加入 Git 忽略列表。构建时使用仓库里的 `package-lock.json` 和 `requirements.txt`。

## 验证

以下命令在未启动开发服务器时运行。浏览器测试会自动启动前后端，需要本机安装 Microsoft Edge。

```powershell
npm.cmd run build
.\.venv\Scripts\python.exe -m pytest -q
$env:Path = (Join-Path (Get-Location) '.venv\Scripts') + ';' + $env:Path
npm.cmd run test:browser
```

API 测试使用模拟上游。浏览器测试覆盖两个实际案例、错误重试、跨预览消息和沙箱中的 DOM、存储及外部 `fetch` 探针。正式模型联调需要有效的服务配置。运行错误与等待超时由预览组件报告。等待超时只用于界面反馈，浏览器沙箱不会为脚本提供执行时间配额。生成页面与问题保存在当前页面会话中，刷新后回到首页。

## AI 协同开发记录

- [动态生成与隔离预览](docs/ai-iterations/01-lesson-preview.md) · 原始对话与验收
- [对话修改与版本管理](docs/ai-iterations/02-revision-versions.md) · 设计快照
- [选择题与双模型审核](docs/ai-iterations/03-quiz-review.md) · 设计快照
