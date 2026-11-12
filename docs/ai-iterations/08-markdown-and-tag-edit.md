# 08 照片导入、Markdown 渲染与标签编辑修复

> 迭代日期：2026-11-12
> 对话工具：DeepSeek Harness
> 对应提交：`5db9bcf`（草稿式导入）、`52def68`（Markdown/KaTeX + 标签 UI）、`0f7ac48`（浏览器用例）
> 相关测试：`pytest -q` 71 项、`npm run build`、`npm run test:browser` 19 项

本文记录照片多题识别、题干/选项可读性、以及“编辑知识点添加不生效”的完整修复链。

## Prompt 链

### 第 1 轮：多题照片不要“一整页丢给用户”

**用户：**

> 不是直接输出一整页的内容让用户自己找，系统先进行切分所有的题目……不需要本地切分，直接让 api 切分好丢到客户端，客户端一个一个放进去就好了

**AI 诊断/修改：**

- 之前按区域裁剪 + 本地切分，既慢又容易切错；
- 改为**每张照片只发一次 API**，让模型直接返回 `questions[]`；
- `backend/paper_files.py::photo_page` 只返回整页图片，不再返回区域；
- 识别结果全部先存为草稿（`confirmed=0`），用户在题库中逐题确认后才可用于练习；
- 只有 `confirmed=1 AND ready=1` 的题进入练习。

**验证：**

- 浏览器用例：识别 2 道题 → 逐题「确认入库」→ 再开始学习；
- 文档：[06-photo-import-drafts.md](06-photo-import-drafts.md)。

### 第 2 轮：原始 Markdown/LaTeX 不可读

**用户：**

> 需要增强可读性，不要直接的 markdown 形式，可以内置 markdown 查看器

**AI 修改：**

- 新增 `src/markdown.tsx`：
  - `Markdown`（块级）与 `InlineMarkdown`（选项内联）；
  - `react-markdown` + `remark-gfm` + `remark-math` + `rehype-katex`；
  - 不启用原始 HTML；表格外包 `.table-scroll`，链接新窗口打开；
- `src/exam-library.tsx`、`src/quiz-panel.tsx`、`src/ask-panel.tsx` 统一使用；
- 题干用 `sr-only` legend 保留可访问名称，可见区域用 Markdown 渲染；
- `src/styles.css` 增加 `.markdown`、`.table-scroll`、KaTeX 样式。

**验证：**

- 浏览器用例 mock 一道带 `$xOy$` 和 GFM 表格的二次函数题：
  - 断言页面出现 `<table>`、`.katex`；
  - 断言不再出现 `|---|` 原始表格分隔符。

### 第 3 轮：编辑知识点“添加不生效、删除生效”

**用户：**

> 目前编辑添加知识点后，无法增加用户添加的知识点，但是删除已有知识点的功能是实现了的

**AI 根因：**

- `TagForm` 只有在输入框按 **Enter** 时才把 `draft` 加进 `tags`；
- 点「保存」提交的是 `tags`，没有合并输入框里还没提交的文字；
- 删除会立即改 `tags`，所以删除生效、添加丢失；
- 另一个问题：删空后 `tags.length === 0`，即使输入框里有新标签，「保存」也被禁用。

**AI 修复：**

- 保存时计算 `pending`（去重、最多 8 个），提交 `nextTags = tags + pending`；
- 新增「添加」按钮，不按回车也能先加入；
- 「保存」按钮的禁用条件改为 `!nextTags.length`；
- 浏览器用例：输入「判别式」后**不按回车、直接点保存**，断言请求体 `["二次函数","判别式"]` 且页面出现新标签。

### 第 4 轮：标签保存后的状态

**用户：**

> 保存后不要改变题目的确认状态

**AI 规则：**

- `PATCH .../tags` 只改 `tags`/`searchable`，不动 `confirmed/ready/status`；
- 题干/选项/答案的内容编辑仍回退为草稿，避免“改了答案还标可判分”。

## 关键 Bug 修复记录

| 现象 | 根因 | 修复 |
| --- | --- | --- |
| 多题识别输出整页 | 按区域本地切分 | 每页一次 API，模型返回 `questions[]` |
| 题干显示 `$...$`/`|---|` | 直接输出原始 Markdown | `Markdown`/`InlineMarkdown` 组件 |
| 添加标签丢失 | 保存只提交已有 chips | 合并 `pending`，新增「添加」按钮 |
| 删空后不能保存 | 只看 `tags.length` | 改看 `nextTags.length` |
| 标签保存后变草稿 | 复用了内容编辑逻辑 | 标签接口只更新 tags/searchable |
| 识别结果直接可练 | 未区分草稿/确认 | 全部草稿，确认后才 `confirmed=1` |

## 落地清单

- 新增：`src/markdown.tsx`、`docs/ai-iterations/06-photo-import-drafts.md`
- 修改：`src/exam-library.tsx`、`src/quiz-panel.tsx`、`src/ask-panel.tsx`、`src/styles.css`、`backend/paper_files.py`、`backend/papers.py`、`backend/paper_store.py`
- 提交：`5db9bcf`、`52def68`、`0f7ac48`
- 验证：`npm run build` 通过；`npm run test:browser` **19 passed**；`pytest -q` **71 passed**
