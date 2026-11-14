# 13 候选题随机抽样后再核验

> 迭代日期：2026-11-14  
> 对话工具：DeepSeek Harness（DSH）  
> 模型：`deepseek-flash`  
> 对应提交：`072fd76`  
> 相关测试：`pytest -q` 77 项、`npm run test:browser` 23 项、`npm run build`  
> 对话快照：[本次练习改造导出](exports/dsh-session-2026-11-14-practice-redesign.md)

## 用户 Prompt（原话）

> 我觉得从联网和题库里面找到的候选题目，应该采取随机选择的原则。  
> 你觉得呢

## AI 建议

- 不建议「完全随机直接出题」：候选题可能不贴合当前知识点，或者答案未核验。
- 采用「随机候选池 + 模型核验」：先洗牌并最多取 16 道，再交给现有模型做相关性、答案和题型初审。
- 随机应发生在候选进入模型之前，而不是只随机最终 2 道题；否则模型仍然只看到固定靠前的题。
- 个人题库、联网真题、开放题三条路径统一在 `select_questions` / `select_open_questions` 抽样，避免每个来源各写一套。
- 用 `SystemRandom`，不设固定种子；测试用可控替身，避免用例随机波动。

## 实现

- 新增 `backend/selection.py`：
  - `RNG = random.SystemRandom()`
  - `CANDIDATE_LIMIT = 16`
  - `sample_candidates(items, limit=16, rng=RNG)`：先洗牌再截断。
- `backend/exams.py`：
  - `select_questions` 开头抽样；
  - `select_open_questions` 开头抽样；
  - 抽样后重新编号 `candidate`。
- 测试：
  - `tests/test_selection.py` 用反向 RNG 验证洗牌、上限、去重和空输入；
  - `tests/conftest.py` 提供确定性替身，保持现有集成测试顺序稳定；
  - `test_exam_selection_samples_candidates` 验证联网路径确实调用抽样入口。

## Bug 与踩坑

- **随机样本让旧测试不稳定**：原测试依赖「第一条候选」和固定候选顺序；用 autouse 替身固定测试顺序，随机性由独立单元测试覆盖。
- **上限不能只截断前 16 条**：如果先截断再洗牌，随机仍只在固定前 16 条里发生；实现为「先洗牌，再截断」。
- **替换题也走同一入口**：单题替换的 1 道候选同样经过抽样，避免替换题固定选第一条。
- **目标考试优先与随机的关系**：随机发生在检索之后；目标考试候选题仍在池中，但不再固定排在最前。

## 证据

- 提交：`072fd76 feat: randomize candidates before quiz review`
- 新增 `backend/selection.py`、`tests/test_selection.py`
- 后端 77 项、浏览器 23 项、构建通过
- 随机上限：16；候选不足时全部进入
