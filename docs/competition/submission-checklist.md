# 竞赛提交清单（2026 第九届传智杯 · AI 创新应用挑战赛）

> 赛道：Vibe Coding 个人赛，序号 5「AI 驱动的高交互教育与可视化」
> 项目：可视化理论中心（interact-study）
> 仓库：<https://github.com/json888666-afk/interact-study>
> 本文用于对照竞赛材料要求逐项自查；视频、PDF 等由参赛者本人最终提供。

## 一、竞赛要求原文（摘录）

> 2.1 代码仓库与演进记录
> 托管平台：GitHub / Gitee（须设为 Public 或提供评审访问权限）。
> Git 提交日志（关键）：必须保留完整的、细粒度的 Git 提交历史。禁止一次性提交（"initial commit" 即包含全部功能）。每次提交应对应一次与 AI 的核心对话或一个功能模块的落地。
> AI 对话历史导出的 Prompt 历史快照：
> - 使用 AI 工具需要导出和 AI 的对话历史，如果 AI 工具不支持导出，可以截图或者录屏。
> - 须包含至少 3 个核心功能迭代时与 AI 交互的完整 Prompt 链（包含你的 Prompt 提问、AI 的修改建议、以及你如何引导 AI 修复 Bug 的过程）。

## 二、仓库与访问权限

- 仓库地址：<https://github.com/json888666-afk/interact-study>
- 默认分支：`main`
- 版本标签：`v0.5.0`（`6868c2e`）、`v0.5.1`（历史标签）；当前 `main` HEAD：`d6f9d7f` + 本次文档提交
- 访问要求：**Public**，或给评审账号开通只读权限。
- 提交前确认：
  - [x] GitHub 仓库已设为 Public（2026-11-13 验证；如需评审账号可另加 Collaborator）
  - [x] `origin/main` 已推送最新提交
  - [x] 本地 `.env`、`.local/`、数据库、测试截图未进入仓库

## 三、细粒度 Git 提交历史

历史提交（按时间从旧到新）：

| 提交 | 功能模块 / AI 迭代 |
| --- | --- |
| `de624bc` | 学习者账户、profile 与会话排行榜 |
| `983fe08` | 引导式解析与三题巩固 |
| `7b22d6c` | 真题检索与 DeepSeek 核验 |
| `4217630` | 私有试卷导入与照片漏题恢复 |
| `19ea6dd` | Codex 完整 Prompt 链归档 |
| `390884f` | 浏览器验证使用隔离数据库 |
| `e80eddc` | 年级/目标个性化 + 放宽学习目标审核 + 非考试不搜真题 |
| `5db9bcf` | 草稿式试卷导入 + 全量候选交 API + 开放题转换 + 标签 |
| `52def68` | Markdown/KaTeX 题干渲染 + 标签编辑 UI |
| `0f7ac48` | 学习页 profile 展示 + 个人设置返回来源页 |
| `6868c2e` | DeepSeek Prompt 链 07–09 + 本清单 + README 链接 |
| `4463bd4` | 排行榜/我的试卷返回来源页 + 「个人设置」改名 |
| `ada3e01` | 个人设置页增加返回上一页/返回首页 |
| `ea33272` | 欢迎 gate、两步引导、品牌改名 |
| `1d9c5c1` | 欢迎页抛物线预览可拖动 |
| `0f2b9b1` | 学习首页、头像菜单、继续学习入口 |
| `03e7a0b` / `4166140` / `788110b` | 继续学习紧凑条 → 导航胶囊 → 下拉浮层；首页左对齐 |
| `c50fd03` / `7d35c15` / `f786005` | 首页输入区尺寸与首屏大输入 |
| `f3b0bc8` / `bd3079e` | 练习通过徽章 → 奖章 + 书本 + 绶带 |
| `f7f9348` | 上下文返回按钮 |
| `e45eb8c` / `06f60f0` / `1b8f07a` | 导入试卷逐题分页、底部分页、详情去重 |
| `d6f9d7f` | 知识点胶囊、1200 双栏、设置返回文案 |
| 本次文档提交 | 10 文档、11-14 导出、截图、清单更新 |

说明：

- 没有“initial commit 即包含全部功能”的提交；
- 每个提交对应一次核心 AI 对话或一个功能模块；
- 每个提交都有对应的测试/构建验证（见各提交说明与 `docs/ai-iterations/`）。

## 四、AI 对话历史 / Prompt 链

已归档（`docs/ai-iterations/`）：

| 文档 | 内容 |
| --- | --- |
| `01-lesson-preview.md` | 动态生成与隔离预览 |
| `02-revision-versions.md` | 对话修改与版本历史 |
| `03-quiz-review.md` | 选择题与按需审核 |
| `04-codex-transcript.md` | Codex 对话原文导出（完整 transcript） |
| `05-prompt-chain-index.md` | 六条完整 Prompt 链索引 |
| `06-photo-import-drafts.md` | 照片单次读取 + 草稿确认 |
| `07-selection-and-conversion.md` | 题库选题、开放题转换、10 次初审循环、标签编辑 |
| `08-markdown-and-tag-edit.md` | 照片导入、Markdown/KaTeX、标签“保存丢失输入”修复 |
| `09-profile-goals-and-settings.md` | 年级/目标个性化、目标审核放宽、设置返回来源页 |
| `10-learning-hub-quiz-badge-paper-library.md` | 学习中心/继续学习、练习通过徽章、试卷分页/宽屏/知识点胶囊、设置返回文案 |
| `exports/deepseek-session-2026-11-13.md` | DeepSeek Harness 原始会话导出（脱敏，含 07–09 三个迭代） |
| `exports/deepseek-session-2026-11-14.md` | 2026-11-13 10:44 至 11-14 的续接导出（脱敏，含 10 的三个迭代） |

**至少 3 个核心迭代的完整 Prompt 链**：07、08、09、10 均包含：

- 用户原话 Prompt；
- AI 的诊断/修改建议；
- 用户如何指出问题、引导修 Bug；
- 最终落地的文件、提交、测试证据。

**AI 对话导出**：

- 已从 DSH 原生 session v4 导出两份脱敏 transcript：
  - `docs/ai-iterations/exports/deepseek-session-2026-11-13.md`（07–09）；
  - `docs/ai-iterations/exports/deepseek-session-2026-11-14.md`（2026-11-13 10:44 起，续接 10 的三个迭代）。
  - 保留用户/AI 文本消息与完整的 `exit_plan_mode` 方案，省略 reasoning、工具输出和系统运行时消息；`sk-...`、本机路径、邮箱、演示账号已脱敏。
- 关键界面截图已归档到 `docs/ai-iterations/assets/2026-11-14/`：欢迎 gate、欢迎庆祝、继续学习浮层、知识徽章、试卷宽屏、设置返回排行榜。
- 截图/录屏中不要露出 API Key、账号密码、私有试卷原文。

## 五、其他交付物

| 材料 | 要求 | 状态 |
| --- | --- | --- |
| 公开仓库 | Public 或评审访问 | ✅ 已公开（2026-11-13 验证） |
| 细粒度 commit | 每次对应 AI 对话/功能模块 | 已按上表拆分 |
| Prompt 链 | ≥3 个核心迭代 | 07–09、10 已写（六条索引） |
| AI 对话导出/截图 | 导出或截图/录屏 | ✅ 11-13/11-14 导出 + 2026-11-14 截图资产 |
| README | 启动、功能、验证、AI 记录 | 本次更新链接 |
| 演示视频 | 5–8 分钟、1080p、含 ≥2 分钟 AI 协作 | 待录制（用户操作） |
| PDF | ≤30 页 | 待整理（用户操作） |

## 六、安全与隐私

- [x] `.env` 未提交，仓库中无 API Key；
- [x] 测试/截图不包含真实账号、密码、私有试卷原文；
- [ ] 曾在聊天中出现的 API Key 已在 DeepSeek 控制台轮换；
- [x] `.local/`、`*.sqlite3`、`test-results/`、`playwright-report/` 均被 `.gitignore` 覆盖。

## 七、最终验证命令

```powershell
npm.cmd run build
.\.venv\Scripts\python.exe -m pytest -q
$env:BROWSER_QUIZ_DB_PATH = '.local/browser-quiz-' + [Guid]::NewGuid().ToString('N') + '.sqlite3'
npm.cmd run test:browser
```

预期：构建通过、后端 72 项通过、浏览器 22 项通过；`git status` 除本地截图目录外干净。
