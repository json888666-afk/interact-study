# 十条核心功能的完整 Prompt 链

打开链接可逐条阅读原文。各链的摘要、提交与复测依据为编制参赛材料时补录。

## 1. 单题质疑与答案隐藏

- [最初需求、仅在学生质疑时复核的设计及首轮实现](04-codex-transcript.md#msg-074)（消息 074–085）。
- [用户要求质疑期间隐藏答案、解释疑点并在换题后致谢](04-codex-transcript.md#msg-123)（消息 123–126）。后续 AI 消息保留了修改方案、实施进度和验收反馈。
- 初版提交 e93c46a，本次修订提交 983fe08。自动化模拟验证打开质疑时隐藏已答题的答案和解析、审核解释不泄露参考答案、确认有误时仅替换单题并弹出一次感谢提示。见 [API 测试](../../tests/test_learning_quiz.py) 与 [浏览器测试](../../tests/browser/learning-loop.spec.ts)。早期设计见[选择题与双模型审核](03-quiz-review.md)。

## 2. 按学习目标实时查找真题

- [最初的备考搜索需求、DeepSeek 方案及初版结果](04-codex-transcript.md#msg-157)（消息 157–168）。
- [用户报告找不到真题、提供截图并要求实时搜索与审核](04-codex-transcript.md#msg-169)（消息 169–181）。原文保留 AI 的分析、用户的修订指令、实施和复测回应。
- 实现提交 7b22d6c。模拟上游验证按目标考试过滤、原文及答案核验、选项错序、超时和回退。真实接口验证搜索与读取公开试卷，成都样例显示公开原文入口；该次未核实站内使用依据。见[真题测试](../../tests/test_exams.py)。

## 3. 多题照片漏识别与重传

- [最初的试卷导入需求、技术建议与初版实现](04-codex-transcript.md#msg-182)（消息 182–187）。
- [用户报告一张照片只导入一道题，并确认分块识别、保留疑题和按考点练习](04-codex-transcript.md#msg-188)（消息 188–198）。原文保留计划、执行和验收回应。
- 实现提交 4217630。模拟上游验证重识别合并去重、单题重传、索引更新及跨考试筛选。真实 DeepSeek 用合成双栏照片识别出两道可判分题和一道待确认题，用户原照片仍待验证。见[试卷测试](../../tests/test_papers.py)与[题库浏览器测试](../../tests/browser/accounts.spec.ts)。

## 4. 学习中心、欢迎与继续学习

- [完整 Prompt 链](10-learning-hub-quiz-badge-paper-library.md#迭代一学习中心顶部导航与继续学习)：欢迎 gate/两步引导、头像菜单、继续学习从首页卡到导航浮层、首页标题与输入区尺寸。
- 对应提交：`ea33272`、`1d9c5c1`、`0f2b9b1`、`03e7a0b`、`4166140`、`c50fd03`、`788110b`、`7d35c15`、`f786005`。
- 证据：`docs/ai-iterations/assets/2026-11-14/welcome-*.png`、`hub-continue-menu.png`；22 项浏览器测试。

## 5. 练习通过 90% 的「知识徽章」

- [完整 Prompt 链](10-learning-hub-quiz-badge-paper-library.md#迭代二练习通过-90-的知识徽章)：从复用三题巩固动画，到不要星星，再到奖章 + 绶带 + 书本。
- 对应提交：`f3b0bc8`、`bd3079e`。
- 证据：`pass-badge.png`；通过弹窗、去重、报告聚焦的浏览器断言。

## 6. 导入试卷逐题分页、详情去重与宽屏

- [完整 Prompt 链](10-learning-hub-quiz-badge-paper-library.md#迭代三导入试卷逐题分页详情去重与宽屏)：逐题分页、只留底部分页、详情嵌入试卷项、知识点胶囊、1200 双栏、上下文返回文案。
- 对应提交：`e45eb8c`、`06f60f0`、`1b8f07a`、`d6f9d7f`。
- 证据：`paper-wide.png`、`back-from-leaderboard.png`；22 项浏览器测试。

## 7. 主练习 10 题与 2:8 真题/模拟

- [完整 Prompt 链](11-practice-ten-question-mix.md)：10 题、2 真题 + 8 模拟、真题不足自动补齐、个人题库优先。
- 对应提交：`43f17e5`、`8df71d9`。
- 证据：`pytest -q` 77 项、`npm run test:browser` 23 项；真实 API 访客练习返回 10 题。

## 8. 按反馈重新生成一批题

- [完整 Prompt 链](12-feedback-regeneration.md)：整批反馈、保留知识点、排除旧题、报告前可换、不限制次数。
- 对应提交：`27e6152`。
- 证据：`tests/test_learning_quiz.py` 的反馈链路；`tests/browser/learning-loop.spec.ts` 的表单与重新渲染。

## 9. 候选题随机抽样后再核验

- [完整 Prompt 链](13-random-candidate-selection.md)：题库/联网候选先随机抽样最多 16 道，再交给模型核验。
- 对应提交：`072fd76`。
- 证据：`backend/selection.py`、`tests/test_selection.py`、`test_exam_selection_samples_candidates`。

## 10. 排行榜与欢迎页视觉层级

- [完整 Prompt 链](14-leaderboard-and-welcome-hierarchy.md)：金银铜奖牌、相对榜首进度条、固定名字列、用户名 2–16、欢迎页 eyebrow 与交互演示标签字号。
- 对应提交：`d77f8c0`、`bff9371`、`d11c2ba`、`006cb2a`、`b7c277d`、`58a08d2`、`d67dc81`、`6f34ade`。
- 证据：`assets/2026-11-14/leaderboard-progress.png`、`welcome-eyebrow.png`、`preview-labels.png`；23 项浏览器测试。

## 对话原文

- [2026-11-14 练习改造 Prompt 历史快照](exports/dsh-session-2026-11-14-practice-redesign.md)
- [2026-11-14 学习中心/徽章/试卷导出](exports/deepseek-session-2026-11-14.md)
