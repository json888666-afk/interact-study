# 06 · 照片试卷改为单次切题与逐题确认入库

## 背景

导入一张含多道题的照片后，页面显示「0 道可判分 · 0 道仅供复习 · 3 道待确认」，每道题的原因都是「不同识别结果的题干、公式或选项不一致」。

根因是旧流程对一张照片读了很多次：整页做 `IMPORT_PROMPT` + `IMPORT_VERIFY_PROMPT` 双读，再对本地切出的多条带/双栏区域分别做 `REGION_PROMPT` + `REGION_VERIFY_PROMPT` 双读，最后要求多次结果逐字一致，否则判为待确认。照片没有原生文本可锚定，任何一次读法的字符差异都会触发「不一致」。

## 用户决定的方向

> 不需要对一张照片读很多次，传给相应的api读一次即可，如果用户发现题目和选项识别有误，可以自行修改。

> 识别的题目都显示为未确认版本，需要用户手动点击确认后才可以入库，保证入库的题目正确无误。

> 直接让api切分好丢到客户端，客户端一个一个放进去就好了。

## 实现

- **单次读取，模型切题。** `paper_files.photo_page` 不再本地切分，只返回整页图；`papers.read_batch` 对每批只调用一次 `IMPORT_PROMPT`；纯图片页每页一批，带原生文本的页每 4 页一批。删除 `reading_pair`、`read_region` 以及 `IMPORT_VERIFY_PROMPT`、`REGION_PROMPT`、`REGION_VERIFY_PROMPT`、`RETRY_VERIFY_PROMPT`。
- **草稿状态。** `draft_questions` 把模型一次返回的 `questions`/`answers` 直接映射为草稿，`confirmed=0`、`status="draft"`，不再做多读一致性比对。
- **空白确认入库。** 新增 `PATCH /api/exam-library/{paper_id}/questions/{question_id}` 编辑题干/选项/答案，新增 `POST .../confirm` 确认入库；未确认题被 `matching_questions` 排除，不参与出题与判分。编辑已确认题会退回草稿。
- **数据迁移。** `imported_questions` 增加 `confirmed INTEGER NOT NULL DEFAULT 0`，启动时用 `PRAGMA table_info` 检测后 `ALTER TABLE`。已有 5 道题迁移后按草稿处理，需手动确认。
- **前端。** 导入后逐题渲染卡片（`未确认`），支持「编辑」「确认入库」「重新提交这道题」；已入库卡片显示「可判分/仅供复习」。

## 验证

- `pytest -q`：59 项通过（含新增的单读、草稿不可用、编辑退回草稿、确认校验与越权 404）。
- `npm run build`：通过。
- `npm run test:browser`：18 项通过（含导入→未确认→逐题确认→回到学习）。
- 使用真实数据库副本验证迁移：`imported_questions` 已出现 `confirmed` 列，现有 2 份试卷、5 道题，`confirmed=1` 为 0。

## 待验证

- 用用户原照片做一次真实 DeepSeek 复测（本次未拿到原图，未执行）。
- 本次改动尚未提交 Git；提交时建议单独作为「照片识别单次切题 + 草稿确认入库」一次提交。
