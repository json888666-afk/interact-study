# 11 主练习 10 题与 2:8 真题/模拟

> 迭代日期：2026-11-14  
> 对话工具：DeepSeek Harness（DSH）  
> 模型：`deepseek-flash`  
> 对应提交：`43f17e5`、`8df71d9`  
> 相关测试：`pytest -q` 77 项、`npm run test:browser` 23 项、`npm run build`  
> 对话快照：[本次练习改造导出](exports/dsh-session-2026-11-14-practice-redesign.md)

## 用户 Prompt（原话）

> 现在可以把我们练习题数量设置为10道题，真题和模拟题2：8的比例。如果联网搜索不到以及库里面的真题数量不够，使用模拟题补齐的方法。  
> 你觉得怎么样

在确认 10 题方案后，用户补充个人题库的范围：

> 这里我觉得从个人题库找就可以，不一定要目标考试。因为用户导入即是自己肯定是之前为这场考试准备过的考试。  
> 你觉得呢

## AI 建议

- 10 题不能只改一个常量：原实现固定 2 道，`MAIN_QUESTION_COUNT=2`，测试、题目题型校验、备考题量和前端文案都绑定了 2。
- 采用「目标 2 道真题 + 8 道模拟」而不是硬保证 2 道真题；真题 0/1/2 道时，分别用 10/9/8 道模拟补齐。
- 个人题库优先于联网和模拟：先查目标考试题库，再用个人题库其他相关题；个人题库不足才联网，最后模拟。用户导入的题默认视为自己为相关考试准备过。
- 新练习不再停在「重试 / 继续做模拟题」选择页；旧 `exam_choice` 存档保留兼容。
- 真题核验只拿到 1 道时，保留这 1 道，而不是整组丢弃。

## 实现

- `backend/quiz_models.py`：
  - `MAIN_QUESTION_COUNT = 10`
  - `MAIN_PAST_TARGET = 2`、`MAIN_SIMULATED_TARGET = 8`
  - 主练习 scope 改为「紧扣当前教学内容的原创选择题」，至少覆盖一道单选和一道多选。
- `backend/quizzes.py`：
  - `generate_job` 统一计算 `simulated_count = 10 - len(past)`；
  - `practice_questions` 新增 `fallback`，联网失败时保留本地真题；
  - 删除主流程的 `exam_choice` 阻断；旧接口保留。
- `backend/exams.py`：
  - `exam_counts()` 固定返回 `(2, 8)`；
  - `find_exam_questions` 允许返回部分已核验真题。
- `backend/papers.py`：
  - 目标考试题库优先，再用个人题库其他相关题补足。
- `src/welcome.tsx`、`src/main.tsx`、`README.md`：文案从「两道题」改为「十道题」。

## Bug 与踩坑

- **测试仍按 2 题写**：`draft()` 只返回 2 道，`build_quiz` 期望 10 道，直接报「题目未通过初审」。先把测试夹具改成 10 道混合题型，再逐个修正报告、积分、挑战和巩固的断言。
- **真题不足时整组丢失**：`find_exam_questions` 在只核验到 1 道时直接抛错。改为 `count > 1` 时返回部分结果，剩余由模拟补齐。
- **跨考试题库与目标考试冲突**：一开始严格只查目标考试，用户反馈后改为「目标考试优先 + 个人题库其他相关题」，并更新题库测试。
- **网页端真实 10 题验证**：用真实 API 跑了一次访客练习，返回 10 题、全部模拟、单选/多选混合，状态 `ready`。

## 证据

- 提交：`43f17e5 feat: make practice ten questions with a 2:8 real-simulated mix`
- 提交：`8df71d9 fix: use the whole personal bank before simulated fill`
- 后端测试：77 项通过
- 浏览器测试：23 项通过
- 构建：`npm run build` 通过
