import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react'
import type { LearningContext } from './learning-api'
import { LoadingProgress } from './loading-progress'
import { quizRequest, startQuiz, type Drill, type Question, type Quiz, type QuizIdentity } from './quiz-api'
import { CelebrationNotice, ReplacementNotice, useNotice } from './quiz-notices'
import { leaderboardLink } from './account-pages'
import { InlineMarkdown, Markdown } from './markdown'

const awaitingReview = (question: Question) => question.review?.status === 'pending'
const paused = (question: Question) => awaitingReview(question) || question.review?.status === 'replacement_failed'

const letters = (options: number[]) => options.map((item) => String.fromCharCode(65 + item)).join('、')

function QuestionCard({ question, busy, act, drillMode = false, drillContent }: {
  question: Question
  busy: boolean
  act: (action: 'answer' | 'challenge' | 'explanation' | 'drill/start', body: object) => void
  drillMode?: boolean
  drillContent?: ReactNode
}) {
  const [selected, setSelected] = useState<number[]>([])
  const [unsure, setUnsure] = useState(false)
  const [challenging, setChallenging] = useState(() => paused(question))
  const [objection, setObjection] = useState(question.review?.objection ?? '')
  const inputId = useId()
  const { answer, review, source } = question
  const hideAnswer = challenging || paused(question)

  function submit(event: FormEvent) {
    event.preventDefault()
    act('answer', unsure ? { unsure: true } : { selected })
  }

  function requestReview(event: FormEvent) {
    event.preventDefault()
    if (objection.trim()) act('challenge', { objection: objection.trim() })
  }

  return (
    <>
      <p className="subject">{question.topic} · {question.kind === 'single' ? '单选' : '多选'}
        {question.origin && <> · <strong>{question.origin === 'past' ? '真题' : '模拟题'}</strong>
          {source?.imported && ' · 用户导入'}</>}
      </p>
      {source && <p className="quiz-source">
        {source.exam} · {source.subject}{source.year && <> · {source.year} 年</>}
        {source.paper && <> · {source.paper}</>} · 第 {source.number} 题 · {source.publisher}
        {source.filename && <> · {source.filename}{source.page && <> 第 {source.page} 页</>}</>}
        {source.attribution && <> · {source.attribution}</>}
        {!hideAnswer && source.url && <> · <a href={source.url} target="_blank" rel="noreferrer">查看原始试卷</a></>}
        {!hideAnswer && source.license_url && <> · <a href={source.license_url} target="_blank" rel="noreferrer">使用条款</a></>}
      </p>}
      <form onSubmit={submit}>
        <fieldset className="quiz-options" disabled={busy || !!answer || hideAnswer}>
          <legend className="sr-only">{question.stem}</legend>
          <Markdown className="question-stem">{question.stem}</Markdown>
          {question.options.map((option, index) => <label key={index}>
            <input type={question.kind === 'single' ? 'radio' : 'checkbox'} name={inputId}
              checked={!hideAnswer && (answer?.selected ?? selected).includes(index)}
              onChange={(event) => {
                setUnsure(false)
                setSelected(question.kind === 'single' ? [index]
                  : event.target.checked ? [...selected, index] : selected.filter((item) => item !== index))
              }} />
            <span>{String.fromCharCode(65 + index)}. <InlineMarkdown>{option}</InlineMarkdown></span>
          </label>)}
          {!drillMode && <label>
            <input type={question.kind === 'single' ? 'radio' : 'checkbox'} name={inputId}
              checked={!hideAnswer && (answer?.unsure ?? unsure)}
              onChange={(event) => {
                setUnsure(event.target.checked)
                setSelected([])
              }} />
            <span>我不清楚</span>
          </label>}
        </fieldset>
        {!answer && !hideAnswer && <button className="primary-button" type="submit"
          disabled={busy || (!unsure && !selected.length)}>{drillMode ? '提交巩固答案' : '提交答案'}</button>}
      </form>
      {answer && !hideAnswer && <div className="quiz-feedback">
        <strong>{drillMode ? '本题已提交' : answer.is_correct ? '回答正确' : '回答错误'}</strong>
        {!drillMode && (answer.correct ? <>
          <p>参考答案 {letters(answer.correct)}</p>
          <div className="markdown explanation">{answer.explanation}</div>
          {!question.drill && <button className="quiet-button" type="button" disabled={busy}
            onClick={() => act('drill/start', {})}>开始巩固</button>}
        </> : <button className="quiet-button" type="button" disabled={busy}
          onClick={() => act('explanation', {})}>查看解析</button>)}
      </div>}
      {awaitingReview(question)
        ? <LoadingProgress label="正在核查此题…" />
        : review && <p className="explanation" role="status">{review.message}</p>}
      {review?.can_replace_simulated && <button className="quiet-button" type="button" disabled={busy}
        onClick={() => act('challenge', { objection: review.objection, allow_simulated: true })}>换成模拟题</button>}
      {!awaitingReview(question) && <button className="quiet-button" type="button"
        disabled={busy} onClick={() => setChallenging(!challenging)}>
        {challenging ? '收起质疑' : '质疑此题'}
      </button>}
      {challenging && !awaitingReview(question) && <form className="objection-form" onSubmit={requestReview}>
        <label htmlFor={inputId + '-objection'}>你对这道题有什么疑问？</label>
        <textarea id={inputId + '-objection'} value={objection} maxLength={2000} disabled={busy}
          onChange={(event) => setObjection(event.target.value)} required />
        <button className="primary-button" type="submit" disabled={busy || !objection.trim()}>提交质疑</button>
      </form>}
      {!hideAnswer && drillContent}
    </>
  )
}

function DrillPanel({ drill, busy, showNotice, request }: {
  drill: Drill
  busy: boolean
  showNotice: boolean
  request: (path: string, body: object) => void
}) {
  const [index, setIndex] = useState(() => Math.max(0, drill.questions.findIndex((item) => !item.answer)))
  const [seen, dismiss] = useNotice()
  const question = drill.questions[index]
  const submitted = drill.questions.filter((item) => item.answer).length
  const canSettle = submitted === 3 && !drill.questions.some(paused)
  const replacement = drill.questions.find((item) => item.review?.status === 'replaced' && !seen(item.id))
  if (drill.status === 'awaiting_explanation') {
    return <p role="status">请先查看解析，再做三道巩固题。</p>
  }
  return (
    <section className="quiz-drill" aria-label="三题巩固">
      <h3>三题巩固 · 第 {drill.round} 轮</h3>
      {drill.status === 'passed' && <p role="status">本轮 3 / 3 正确，巩固通过！</p>}
      {drill.feedback.length > 0 && <details open={drill.status !== 'passed'}>
        <summary>上一轮错题解析</summary>
        {drill.feedback.map((item) => <div key={item.id} className="quiz-feedback">
          <Markdown className="question-stem">{item.stem}</Markdown>
          <p>你的选择 {letters(item.selected)}</p>
          <p>参考答案 {item.correct.map((option) => letters([option]) + '. ' + item.options[option]).join('、')}</p>
          <div className="markdown explanation">{item.explanation}</div>
        </div>)}
      </details>}
      {drill.status === 'generating' && <LoadingProgress label="正在分析考点并生成巩固题…" />}
      {drill.status === 'failed' && <div role="alert">
        <p>{drill.message}</p>
        <button className="quiet-button" type="button" disabled={busy}
          onClick={() => request('retry', {})}>重试生成</button>
      </div>}
      {drill.status === 'ready' && question && <>
        {showNotice && replacement?.review && <ReplacementNotice key={replacement.id} message={replacement.review.message}
          onDismiss={() => { dismiss(replacement.id); setIndex(drill.questions.indexOf(replacement)) }} />}
        <p aria-live="polite">本轮已提交 {submitted} / 3</p>
        <nav className="quiz-actions" aria-label="巩固题导航">
          {drill.questions.map((item, position) => <button className="quiet-button quiz-number" type="button"
            key={item.id} aria-current={index === position ? 'step' : undefined}
            aria-label={`巩固第 ${position + 1} 题${item.answer ? '，已提交' : ''}`}
            onClick={() => setIndex(position)}>{position + 1}</button>)}
        </nav>
        <QuestionCard key={question.id} question={question} busy={busy} drillMode
          act={(action, body) => request(`questions/${question.id}/${action}`, body)} />
        {index < 2 && <button className="quiet-button" type="button"
          onClick={() => setIndex(index + 1)}>下一道巩固题</button>}
        {canSettle && <button className="quiet-button" type="button" disabled={busy}
          onClick={() => request(`questions/${question.id}/answer`, { selected: question.answer?.selected })}>结算本轮</button>}
      </>}
    </section>
  )
}

export function QuizPanel({ owner, version, context, onReturn }: {
  owner: QuizIdentity
  version: string
  context: LearningContext
  onReturn: (suggestion: string) => void
}) {
  const [quiz, setQuiz] = useState<Quiz | null>(null)
  const [index, setIndex] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const active = useRef<AbortController | null>(null)
  const [replacementSeen, dismissReplacement] = useNotice()
  const [celebrationSeen, dismissCelebration, rememberCelebration] = useNotice('celebration')

  async function run(action: (signal: AbortSignal) => Promise<Quiz>, resetIndex = false) {
    if (active.current) return
    const controller = new AbortController()
    active.current = controller
    setBusy(true)
    setError('')
    try {
      const updated = await action(controller.signal)
      if (!controller.signal.aborted) {
        setQuiz(updated)
        if (resetIndex) setIndex(Math.max(0, updated.questions.findIndex((item) =>
          updated.blocked_question_id ? item.id === updated.blocked_question_id : !item.answer)))
      }
    } catch (error) {
      if (!controller.signal.aborted) setError(error instanceof Error ? error.message : '练习请求失败，请重试。')
    } finally {
      if (!controller.signal.aborted) {
        active.current = null
        setBusy(false)
      }
    }
  }

  function load() {
    void run(async (signal) => {
      const saved = await quizRequest<Quiz | null>(owner, '?version_id=' + encodeURIComponent(version), signal)
      return saved ?? startQuiz(owner, version, context, signal)
    }, true)
  }

  useEffect(() => {
    load()
    return () => {
      active.current?.abort()
      active.current = null
    }
  }, [owner.sessionId, owner.accountId, version])

  const waiting = quiz && (quiz.status === 'generating' || quiz.questions.some((item) =>
    awaitingReview(item) || item.drill?.status === 'generating' || item.drill?.questions.some(awaitingReview)))
  useEffect(() => {
    if (!waiting || busy || error || !quiz) return
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      try {
        const updated = await quizRequest<Quiz>(owner, '/' + quiz.id, controller.signal)
        if (!controller.signal.aborted && !active.current) setQuiz(updated)
      } catch {
        if (!controller.signal.aborted && !active.current) setError('无法获取练习进度，请重试。')
      }
    }, 1200)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [quiz, waiting, busy, error, owner.sessionId, owner.accountId])

  function restart() {
    void run((signal) => startQuiz(owner, version, context, signal, quiz?.id), true)
  }

  function retry() {
    if (!quiz) load()
    else void run((signal) => quizRequest<Quiz>(owner, '/' + quiz.id, signal))
  }

  function chooseExam(action: 'retry' | 'simulated') {
    if (quiz) void run((signal) => quizRequest<Quiz>(owner, `/${quiz.id}/exam-choice`, signal, { action }))
  }

  const blockedIndex = quiz?.questions.findIndex((item) => item.id === quiz.blocked_question_id) ?? -1
  const position = blockedIndex >= 0 ? Math.min(index, blockedIndex) : index
  const question = quiz?.questions[position]
  const replacement = quiz?.questions.find((item, i) => (blockedIndex < 0 || i <= blockedIndex)
    && item.review?.status === 'replaced' && !replacementSeen(item.id))
  const celebrationIndex = quiz?.questions.findIndex((item, i) => (blockedIndex < 0 || i <= blockedIndex)
    && !paused(item) && item.drill?.required && item.drill.status === 'passed' && !celebrationSeen(item.id)) ?? -1
  const celebration = quiz?.questions[celebrationIndex]
  const report = quiz?.report
  const lastCelebration = celebrationIndex === (quiz?.questions.length ?? 0) - 1
  const celebrationAction = !lastCelebration ? '挑战下一题' : report ? '查看练习报告' : '继续作答'
  const weak = report?.topics.filter((topic) => topic.correct < topic.total).map((topic) => topic.topic) ?? []
  const suggestion = weak.length ? `我在练习中对${weak.join('、')}掌握不够。能结合当前演示解释这些知识点吗？` : ''
  const answered = quiz?.questions.filter((item) => item.answer && !paused(item)).length ?? 0

  return (
    <section className="quiz-panel" aria-labelledby="quiz-title">
      {replacement?.review && <ReplacementNotice key={replacement.id} message={replacement.review.message}
        onDismiss={() => {
          dismissReplacement(replacement.id)
          setIndex(quiz?.questions.indexOf(replacement) ?? 0)
        }} />}
      {!replacement && celebration && quiz && <CelebrationNotice key={celebration.id}
        action={celebrationAction} onOpen={() => rememberCelebration(celebration.id)} onClose={(continueQuiz) => {
          dismissCelebration(celebration.id)
          if (continueQuiz && (!lastCelebration || !report)) {
            const next = lastCelebration ? quiz.questions.findIndex((item) => !item.answer) : celebrationIndex + 1
            setIndex(next < 0 ? celebrationIndex : next)
            document.getElementById('current-question')?.scrollIntoView()
          } else {
            setIndex(celebrationIndex)
            if (continueQuiz) {
              const reportElement = document.getElementById('quiz-report')
              reportElement?.focus()
              reportElement?.scrollIntoView()
            }
          }
        }} />}
      <div className="quiz-header">
        <div><h2 id="quiz-title">检查理解</h2><p>多选须完全正确。正确率达到 90% 即通过。</p>
          {quiz?.exam && <p className="subject">备考 · {quiz.exam.exam} · {quiz.exam.subject}</p>}</div>
        <button className="quiet-button" type="button" onClick={() => onReturn(suggestion)}>返回学习</button>
      </div>
      {(!quiz || quiz.status === 'generating') && !error &&
        <LoadingProgress label={quiz?.exam ? '正在准备备考题并初审…' : '正在出题并初审…'} />}
      {error && <div role="alert"><p>{error}</p><button className="quiet-button" disabled={busy} onClick={retry}>重试请求</button></div>}
      {quiz?.status === 'exam_choice' && <div className="quiz-feedback" role="status">
        <p>{quiz.message}</p>
        {!!quiz.public_papers?.length && <ul className="public-exam-links">
          {quiz.public_papers.map((paper) => <li key={paper.url}>
            <a href={paper.url} target="_blank" rel="noreferrer">查看公开试卷</a>
            <span>{paper.title} · {paper.publisher}</span>
          </li>)}
        </ul>}
        <div className="quiz-actions">
          <button className="quiet-button" type="button" disabled={busy} onClick={() => chooseExam('retry')}>重试搜索</button>
          <button className="primary-button" type="button" disabled={busy} onClick={() => chooseExam('simulated')}>继续做模拟题</button>
        </div>
      </div>}
      {quiz?.status === 'failed' && <div role="alert"><p>{quiz.message}</p>
        <button className="primary-button" type="button" disabled={busy} onClick={restart}>重新出题</button>
      </div>}
      {report && quiz && <section id="quiz-report" className="quiz-report" aria-label="练习报告" tabIndex={-1}>
        <h3>{report.passed ? '练习通过' : '可以再练习'}</h3>
        <p>答对 {report.correct} / {report.total} 题 · 正确率 {report.percent}%</p>
        <p>{quiz.ranking.enabled
          ? '本次学习会话积分 ' + quiz.ranking.session_point
          : '访客练习 · 登录后新建练习可参与排名。'} <a href={leaderboardLink()}>查看排行榜</a></p>
        <ul>{report.topics.map((item) => <li key={item.topic}>{item.topic} · {item.correct} / {item.total}</li>)}</ul>
        {report.wrong_ids.length > 0 && <div className="quiz-actions">
          <span>查看错题</span>
          {report.wrong_ids.map((id) => {
            const position = quiz.questions.findIndex((item) => item.id === id)
            return <button className="quiet-button" type="button" key={id}
              onClick={() => { setIndex(position); document.getElementById('current-question')?.scrollIntoView() }}>第 {position + 1} 题</button>
          })}
        </div>}
        <button className="primary-button" type="button" disabled={busy} onClick={restart}>重新练习</button>
      </section>}
      {quiz?.status === 'ready' && <p aria-live="polite">已作答 {answered} / {quiz.questions.length} 题</p>}
      {question && quiz && <div id="current-question">
        <nav className="quiz-actions" aria-label="题目导航">
          {quiz.questions.map((item, i) => <button className="quiet-button quiz-number" type="button"
            key={item.id} aria-current={position === i ? 'step' : undefined}
            disabled={blockedIndex >= 0 && i > blockedIndex}
            aria-label={`第 ${i + 1} 题${paused(item) ? '，核查中' : item.answer ? '，已作答' : ''}`}
            onClick={() => setIndex(i)}>{i + 1}</button>)}
        </nav>
        <QuestionCard key={question.id} question={question} busy={busy}
          drillContent={question.drill && <DrillPanel key={`${question.id}:${question.drill.round}:${question.drill.status}`}
            drill={question.drill} busy={busy} showNotice={!replacement && !celebration}
            request={(path, body) => void run((signal) =>
              quizRequest<Quiz>(owner, `/${quiz.id}/questions/${question.id}/drill/${path}`, signal, body))} />}
          act={(action, body) => void run((signal) =>
            quizRequest<Quiz>(owner, `/${quiz.id}/questions/${question.id}/${action}`, signal, body))} />
        {position + 1 < quiz.questions.length && <button className="quiet-button" type="button"
          disabled={position === blockedIndex} onClick={() => setIndex(position + 1)}>下一题</button>}
      </div>}
    </section>
  )
}
