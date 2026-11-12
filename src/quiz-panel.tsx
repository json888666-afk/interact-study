import { leaderboardLink } from './account-pages'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import type { LearningContext } from './learning-api'
import { quizRequest, startQuiz, type Question, type Quiz, type QuizIdentity } from './quiz-api'

const awaitingReview = (question: Question) => question.review?.status === 'pending'
const paused = (question: Question) => awaitingReview(question) || question.review?.status === 'replacement_failed'

function QuestionCard({ question, busy, act }: {
  question: Question
  busy: boolean
  act: (action: 'answer' | 'challenge', body: object) => void
}) {
  const [selected, setSelected] = useState<number[]>([])
  const [challenging, setChallenging] = useState(false)
  const [objection, setObjection] = useState(question.review?.objection ?? '')
  const { answer, review } = question

  function submit(event: FormEvent) {
    event.preventDefault()
    act('answer', { selected })
  }

  function requestReview(event: FormEvent) {
    event.preventDefault()
    if (objection.trim()) act('challenge', { objection: objection.trim() })
  }

  return (
    <>
      <p className="subject">{question.topic} · {question.kind === 'single' ? '单选' : '多选'}</p>
      <form onSubmit={submit}>
        <fieldset className="quiz-options" disabled={busy || !!answer || paused(question)}>
          <legend>{question.stem}</legend>
          {question.options.map((option, index) => <label key={index}>
            <input type={question.kind === 'single' ? 'radio' : 'checkbox'} name="quiz-option"
              checked={(answer?.selected ?? selected).includes(index)}
              onChange={(event) => setSelected(question.kind === 'single' ? [index]
                : event.target.checked ? [...selected, index] : selected.filter((item) => item !== index))} />
            <span>{String.fromCharCode(65 + index)}. {option}</span>
          </label>)}
        </fieldset>
        {!answer && <button className="primary-button" type="submit"
          disabled={busy || paused(question) || !selected.length}>提交答案</button>}
      </form>
      {answer && !paused(question) && <div className="quiz-feedback">
        <strong>{answer.is_correct ? '回答正确' : '回答错误'}</strong>
        <p>参考答案 {answer.correct.map((item) => String.fromCharCode(65 + item)).join('、')}</p>
        <p className="explanation">{answer.explanation}</p>
      </div>}
      {review && <p className="explanation" role="status">
        {awaitingReview(question) ? '正在核查此题，可先回答其他题目。' : review.message}
      </p>}
      {!awaitingReview(question) && <button className="quiet-button" type="button"
        disabled={busy} onClick={() => setChallenging(!challenging)}>
        {challenging ? '收起质疑' : '质疑此题'}
      </button>}
      {challenging && !awaitingReview(question) && <form className="objection-form" onSubmit={requestReview}>
        <label htmlFor="quiz-objection">你对这道题有什么疑问？</label>
        <textarea id="quiz-objection" value={objection} maxLength={2000} disabled={busy}
          onChange={(event) => setObjection(event.target.value)} required />
        <button className="primary-button" type="submit" disabled={busy || !objection.trim()}>提交质疑</button>
      </form>}
    </>
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
        if (resetIndex) setIndex(Math.max(0, updated.questions.findIndex((item) => !item.answer)))
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

  const waiting = quiz && (quiz.status === 'generating' || quiz.questions.some(awaitingReview))
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

  const question = quiz?.questions[index]
  const report = quiz?.report
  const weak = report?.topics.filter((topic) => topic.correct < topic.total).map((topic) => topic.topic) ?? []
  const suggestion = weak.length ? `我在练习中对${weak.join('、')}掌握不够。能结合当前演示解释这些知识点吗？` : ''
  const answered = quiz?.questions.filter((item) => item.answer && !paused(item)).length ?? 0

  return (
    <section className="quiz-panel" aria-labelledby="quiz-title">
      <div className="quiz-header">
        <div><h2 id="quiz-title">检查理解</h2><p>多选须完全正确。正确率大于 90% 通过。</p></div>
        <button className="quiet-button" type="button" onClick={() => onReturn(suggestion)}>返回学习</button>
      </div>
      {(!quiz || quiz.status === 'generating') && !error && <p role="status">正在出题并初审…</p>}
      {error && <div role="alert"><p>{error}</p><button className="quiet-button" disabled={busy} onClick={retry}>重试请求</button></div>}
      {quiz?.status === 'failed' && <div role="alert"><p>{quiz.message}</p>
        <button className="primary-button" type="button" disabled={busy} onClick={restart}>重新出题</button>
      </div>}
      {report && quiz && <section className="quiz-report" aria-label="练习报告">
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
          {quiz.questions.map((item, position) => <button className="quiet-button quiz-number" type="button"
            key={item.id} aria-current={index === position ? 'step' : undefined}
            aria-label={`第 ${position + 1} 题${paused(item) ? '，核查中' : item.answer ? '，已作答' : ''}`}
            onClick={() => setIndex(position)}>{position + 1}</button>)}
        </nav>
        <QuestionCard key={question.id} question={question} busy={busy}
          act={(action, body) => void run((signal) =>
            quizRequest<Quiz>(owner, `/${quiz.id}/questions/${question.id}/${action}`, signal, body))} />
        {index + 1 < quiz.questions.length && <button className="quiet-button" type="button"
          onClick={() => setIndex(index + 1)}>下一题</button>}
      </div>}
    </section>
  )
}
