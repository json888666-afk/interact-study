import { useEffect, useState, type FormEvent } from 'react'
import { returnLabel, safeReturnLocation } from './account-pages'
import { learningRequest } from './learning-api'
import { LoadingProgress } from './loading-progress'
import { InlineMarkdown, Markdown } from './markdown'

type Paper = {
  id: string
  exam: string
  subject: string
  year: number | null
  paper: string | null
  filenames: string[]
  question_count: number
  draft_count: number
  confirmed_count: number
  ready_count: number
  review_count: number
}

type LibraryQuestion = {
  id: number; number: string; section: string | null; stem: string; options: string[]; correct: number[]
  tags: string[]; confirmed: boolean; status: 'draft' | 'ready' | 'review_only'; reason: string
  file: string; page: number
}

type PaperDetail = Paper & {
  questions: LibraryQuestion[]
}

const libraryUrl = '/api/exam-library'

function encodedFile(file: File) {
  return new Promise<{ filename: string; data: string }>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve({ filename: file.name, data: String(reader.result).split(',', 2)[1] })
    reader.onerror = () => reject(new Error('无法读取文件，请重新选择。'))
    reader.readAsDataURL(file)
  })
}

function paperTitle(paper: Paper) {
  return [paper.exam, paper.subject, paper.year && `${paper.year} 年`, paper.paper].filter(Boolean).join(' · ')
}

function paperCounts(paper: Paper) {
  return `${paper.draft_count} 道未确认 · ${paper.confirmed_count} 道已入库（${paper.ready_count} 道可判分）`
}

function questionStatus(question: LibraryQuestion) {
  if (!question.confirmed) return '未确认'
  return question.status === 'ready' ? '已入库 · 可判分' : '已入库 · 仅供复习'
}

function stemSource(question: LibraryQuestion) {
  const label = `${question.section ? question.section + ' · ' : ''}${question.number}.`
  const stem = question.stem.trim() || '识别结果为空'
  return /^\s*\|/.test(stem) ? `**${label}**\n\n${stem}` : `**${label}** ${stem}`
}

function RepairForm({ target, busy, onCancel, onSubmit }: {
  target: 'paper' | number
  busy: boolean
  onCancel: () => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}) {
  const photoTypes = '.jpg,.jpeg,.png,.webp'
  const types = target === 'paper' ? '.pdf,.docx,' + photoTypes : photoTypes
  return <form className="paper-repair" onSubmit={onSubmit}>
    <fieldset disabled={busy}>
      <legend>{target === 'paper' ? '重新识别原卷' : '重新提交这道题'}</legend>
      <label>{target === 'paper' ? '原试卷文件' : '这道题的清晰照片'}
        <input type="file" name="original" accept={types} required />
      </label>
      <label>参考答案（可选）
        <input type="file" name="answers" accept={'.pdf,.docx,' + photoTypes} />
      </label>
      {target === 'paper' && <p className="subject">使用原导入时的文件名。新识别的题将合并到当前试卷。</p>}
      <label className="paper-consent"><input type="checkbox" name="consent" required />
        我有权使用这些资料，并同意发送给 DeepSeek 识别。</label>
      <div className="quiz-actions">
        <button className="primary-button" type="submit">{target === 'paper' ? '开始重新识别' : '提交核对'}</button>
        <button className="quiet-button" type="button" onClick={onCancel}>取消</button>
      </div>
    </fieldset>
  </form>
}

function EditForm({ question, busy, onCancel, onSubmit }: {
  question: LibraryQuestion
  busy: boolean
  onCancel: () => void
  onSubmit: (data: { stem: string; options: string[]; correct: number[] }) => void
}) {
  const [stem, setStem] = useState(question.stem)
  const [options, setOptions] = useState(() => {
    const values = question.options.slice(0, 6)
    return [...values, ...Array(6 - values.length).fill('')]
  })
  const [correct, setCorrect] = useState(() => new Set(question.correct || []))

  function toggle(index: number) {
    const next = new Set(correct)
    if (next.has(index)) next.delete(index)
    else next.add(index)
    setCorrect(next)
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const pairs = options
      .map((text, index) => ({ text: text.trim(), correct: correct.has(index) }))
      .filter((pair) => pair.text)
    const selected = pairs.map((pair, index) => pair.correct ? index : -1).filter((index) => index >= 0)
    onSubmit({ stem: stem.trim(), options: pairs.map((pair) => pair.text), correct: selected })
  }

  return <form className="paper-repair" onSubmit={submit}>
    <fieldset disabled={busy}>
      <legend>编辑题目</legend>
      <label>题干
        <textarea value={stem} onChange={(event) => setStem(event.target.value)} maxLength={1000} required />
      </label>
      <div className="markdown-preview" aria-label="题干预览">
        <Markdown>{stem || '（空）'}</Markdown>
      </div>
      <fieldset>
        <legend>选项（空项忽略，按 A–F 顺序保存）</legend>
        {options.map((text, index) => <label key={index}>
          {String.fromCharCode(65 + index)}
          <input value={text} maxLength={300}
            onChange={(event) => { const next = [...options]; next[index] = event.target.value; setOptions(next) }} />
        </label>)}
      </fieldset>
      <fieldset>
        <legend>正确答案</legend>
        {options.map((text, index) => text.trim() && <label key={index}>
          <input type="checkbox" checked={correct.has(index)} onChange={() => toggle(index)} />
          {String.fromCharCode(65 + index)}
        </label>)}
      </fieldset>
      <div className="quiz-actions">
        <button className="primary-button" type="submit">保存</button>
        <button className="quiet-button" type="button" onClick={onCancel}>取消</button>
      </div>
    </fieldset>
  </form>
}

function TagForm({ question, suggestions, busy, onCancel, onSubmit }: {
  question: LibraryQuestion
  suggestions: string[]
  busy: boolean
  onCancel: () => void
  onSubmit: (tags: string[]) => void
}) {
  const [tags, setTags] = useState(question.tags)
  const [draft, setDraft] = useState('')
  const value = draft.trim()
  const pending = value && !tags.includes(value) && tags.length < 8 ? value : ''
  const nextTags = pending ? [...tags, pending] : tags

  function add() {
    if (!pending) {
      setDraft('')
      return
    }
    setTags(nextTags)
    setDraft('')
  }

  function remove(tag: string) {
    setTags(tags.filter((item) => item !== tag))
  }

  return <form className="paper-repair" onSubmit={(event) => {
    event.preventDefault()
    if (nextTags.length) onSubmit(nextTags)
  }}>
    <fieldset disabled={busy}>
      <legend>编辑知识点</legend>
      <div className="tag-chips">
        {tags.map((tag) => <span key={tag} className="tag-chip">{tag}
          <button type="button" aria-label={`删除${tag}`} onClick={() => remove(tag)}>×</button>
        </span>)}
      </div>
      <label>添加知识点
        <input value={draft} list="tag-suggestions" maxLength={60}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              add()
            }
          }} />
      </label>
      <datalist id="tag-suggestions">{suggestions.map((tag) => <option key={tag} value={tag} />)}</datalist>
      <div className="quiz-actions">
        <button className="quiet-button" type="button" onClick={add} disabled={!pending}>添加</button>
      </div>
      <p className="subject">至少 1 个、最多 8 个；保存后不会改变题目的确认状态。</p>
      <div className="quiz-actions">
        <button className="primary-button" type="submit" disabled={!nextTags.length}>保存</button>
        <button className="quiet-button" type="button" onClick={onCancel}>取消</button>
      </div>
    </fieldset>
  </form>
}

export function ExamLibrary({ signedIn }: { signedIn: boolean }) {
  const [papers, setPapers] = useState<Paper[]>([])
  const [active, setActive] = useState<PaperDetail | null>(null)
  const [loading, setLoading] = useState(signedIn)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [removeId, setRemoveId] = useState<string | null>(null)
  const [repair, setRepair] = useState<'paper' | number | null>(null)
  const [editing, setEditing] = useState<number | null>(null)
  const [tagging, setTagging] = useState<number | null>(null)
  const [questionIndex, setQuestionIndex] = useState(0)
  const from = safeReturnLocation(new URLSearchParams(window.location.search).get('from'))
  const backTo = from ?? '/'

  function goBack() {
    window.location.replace(from && from !== '/exam-library' ? from : '/')
  }

  useEffect(() => {
    if (!signedIn) return
    const controller = new AbortController()
    learningRequest<{ papers: Paper[] }>(libraryUrl, { signal: controller.signal })
      .then((result) => setPapers(result.papers))
      .catch((cause) => { if (!controller.signal.aborted) setError(cause.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [signedIn])

  useEffect(() => {
    if (!active) { setQuestionIndex(0); return }
    setQuestionIndex((value) => Math.min(value, Math.max(0, active.questions.length - 1)))
  }, [active?.id, active?.questions.length])

  function updatePaper(paper: PaperDetail) {
    setPapers((current) => current.some((item) => item.id === paper.id)
      ? current.map((item) => item.id === paper.id ? paper : item)
      : [paper, ...current])
    setActive(paper)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const form = event.currentTarget
    const values = new FormData(form)
    const files = values.getAll('papers').filter((value): value is File => value instanceof File && value.size > 0)
    if (!files.length || files.length > 16 || files.reduce((total, file) => total + file.size, 0) > 15 * 1024 * 1024) {
      setError('请选择 1–16 个文件，总大小不得超过 15 MiB。')
      return
    }
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = await learningRequest<{ paper: PaperDetail; duplicate: boolean; merged: boolean }>(libraryUrl + '/imports', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          exam: String(values.get('exam')).trim(), subject: values.get('subject'),
          year: Number(values.get('year')) || null, paper: String(values.get('paper')).trim() || null,
          consent: values.get('consent') === 'on', files: await Promise.all(files.map(encodedFile)),
        }),
      })
      updatePaper(result.paper)
      setQuestionIndex(0)
      setRepair(null)
      setEditing(null)
      setMessage(result.duplicate ? '这份试卷已在题库中。'
        : result.merged ? '已合并到已有试卷。'
        : `已识别 ${result.paper.question_count} 道题，请逐题核对后点击「确认入库」。`)
      form.reset()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '导入失败，请重试。')
    } finally {
      setBusy(false)
    }
  }

  async function openPaper(id: string) {
    setError('')
    setRepair(null)
    setEditing(null)
    try {
      const result = await learningRequest<{ paper: PaperDetail }>(libraryUrl + '/' + id, {})
      setActive(result.paper)
      setQuestionIndex(0)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法打开试卷。')
    }
  }

  async function submitRepair(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!active || repair === null || busy) return
    const values = new FormData(event.currentTarget)
    const files = [values.get('original'), values.get('answers')]
      .filter((value): value is File => value instanceof File && value.size > 0)
    if (!files.length || files.reduce((total, file) => total + file.size, 0) > 15 * 1024 * 1024) {
      setError('请选择清晰的文件，总大小不得超过 15 MiB。')
      return
    }
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const path = libraryUrl + '/' + active.id + (repair === 'paper' ? '/reprocess' : `/questions/${repair}/retry`)
      const result = await learningRequest<{ paper: PaperDetail }>(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ consent: values.get('consent') === 'on', files: await Promise.all(files.map(encodedFile)) }),
      })
      updatePaper(result.paper)
      setMessage(repair === 'paper' ? '重新识别完成，已合并到原试卷。' : '已更新这道题。')
      setRepair(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '识别失败，请重试。')
    } finally {
      setBusy(false)
    }
  }

  async function saveEdit(questionId: number, data: { stem: string; options: string[]; correct: number[] }) {
    if (!active || busy) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = await learningRequest<{ paper: PaperDetail }>(`${libraryUrl}/${active.id}/questions/${questionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      updatePaper(result.paper)
      setEditing(null)
      setMessage('已保存，请点击「确认入库」。')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '保存失败，请重试。')
    } finally {
      setBusy(false)
    }
  }

  async function confirmQuestion(questionId: number) {
    if (!active || busy) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = await learningRequest<{ paper: PaperDetail }>(
        `${libraryUrl}/${active.id}/questions/${questionId}/confirm`, { method: 'POST' })
      updatePaper(result.paper)
      setMessage('已确认入库。')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '确认失败，请重试。')
    } finally {
      setBusy(false)
    }
  }

  async function saveTags(questionId: number, tags: string[]) {
    if (!active || busy) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = await learningRequest<{ paper: PaperDetail }>(
        `${libraryUrl}/${active.id}/questions/${questionId}/tags`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tags }),
        })
      updatePaper(result.paper)
      setTagging(null)
      setMessage('知识点已更新。')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '保存失败，请重试。')
    } finally {
      setBusy(false)
    }
  }

  async function removePaper(id: string) {
    setError('')
    try {
      await learningRequest(libraryUrl + '/' + id + '/delete', { method: 'POST' })
      setPapers((current) => current.filter((paper) => paper.id !== id))
      setActive((current) => current?.id === id ? null : current)
      setMessage('已从个人题库移除试卷。')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法移除试卷。')
    } finally {
      setRemoveId(null)
    }
  }

  const questionCount = active?.questions.length ?? 0
  const position = questionCount ? Math.min(questionIndex, questionCount - 1) : 0
  const question = active?.questions[position]
  const pagingLocked = busy || editing !== null || tagging !== null || typeof repair === 'number'

  function showQuestion(next: number) {
    if (!active) return
    const bounded = Math.min(Math.max(next, 0), Math.max(0, active.questions.length - 1))
    setQuestionIndex(bounded)
    setEditing(null)
    setTagging(null)
    if (typeof repair === 'number') setRepair(null)
    window.requestAnimationFrame(() => document.getElementById('paper-question')?.scrollIntoView({ block: 'start' }))
  }

  function questionPager() {
    return <div className="paper-pager" role="group" aria-label="题目分页">
      <span aria-live="polite">第 {position + 1} / {questionCount} 题</span>
      <div className="quiz-actions">
        <button className="quiet-button" type="button" disabled={pagingLocked || position === 0}
          onClick={() => showQuestion(position - 1)}>← 上一题</button>
        <button className="quiet-button" type="button" disabled={pagingLocked || position >= questionCount - 1}
          onClick={() => showQuestion(position + 1)}>下一题 →</button>
      </div>
    </div>
  }

  function paperDetail() {
    if (!active) return null
    return <section className="paper-detail" aria-label="试卷题目">
      <div className="paper-detail-toolbar">
        {repair === 'paper' ? <RepairForm target="paper" busy={busy} onCancel={() => setRepair(null)} onSubmit={submitRepair} />
          : <button className="quiet-button" type="button" disabled={busy} onClick={() => { setRepair('paper'); setEditing(null) }}>重新识别</button>}
      </div>
      {!questionCount ? <p>暂无题目。</p> : <>
        <ol start={position + 1} id="paper-question" className="paper-question-list">
          {question && <li key={question.id}>
            {tagging === question.id
              ? <TagForm question={question} busy={busy}
                  suggestions={[...new Set(active.questions.flatMap((item) => item.tags))]
                    .filter((tag) => !question.tags.includes(tag))}
                  onCancel={() => setTagging(null)}
                  onSubmit={(tags) => void saveTags(question.id, tags)} />
              : editing === question.id
                ? <EditForm question={question} busy={busy} onCancel={() => setEditing(null)}
                    onSubmit={(data) => void saveEdit(question.id, data)} />
                : <>
                  <Markdown className="question-stem">{stemSource(question)}</Markdown>
                  {!!question.options.length && <ol type="A">{question.options.map((option, i) =>
                    <li key={i}><InlineMarkdown>{option}</InlineMarkdown></li>)}</ol>}
                  {!!question.correct.length && <p className="subject">答案：{question.correct.map((i) => String.fromCharCode(65 + i)).join('、')}</p>}
                  <p className="subject">{question.file} · 第 {question.page} 页 · {questionStatus(question)}</p>
                  {!question.confirmed && <p className="subject">{question.reason}</p>}
                  <div className="quiz-actions">
                    <button className="quiet-button" type="button" disabled={busy}
                      onClick={() => { setEditing(question.id); setRepair(null); setTagging(null) }}>编辑</button>
                    <button className="quiet-button" type="button" disabled={busy}
                      onClick={() => { setTagging(question.id); setEditing(null); setRepair(null) }}>编辑知识点</button>
                    {!question.confirmed && <button className="primary-button" type="button" disabled={busy}
                      onClick={() => void confirmQuestion(question.id)}>确认入库</button>}
                    {!question.confirmed && (repair === question.id
                      ? <RepairForm target={question.id} busy={busy} onCancel={() => setRepair(null)} onSubmit={submitRepair} />
                      : <button className="quiet-button" type="button" disabled={busy}
                          onClick={() => { setRepair(question.id); setEditing(null); setTagging(null) }}>重新提交这道题</button>)}
                  </div>
                </>}
            {!!question.tags.length && <div className="tag-links" role="group" aria-label="学习知识点">
              <span className="tag-links-label">学习知识点：</span>
              {question.tags.map((tag) => <a key={tag} className="tag-pill"
                href={'/?question=' + encodeURIComponent(`请讲解${tag}`)}
                aria-label={`学习${tag}`} title={`学习${tag}`}>{tag}</a>)}
            </div>}
          </li>}
        </ol>
        {questionPager()}
      </>}
    </section>
  }

  return <main className="page account-page exam-library">
    <section className="account-card">
      <nav className="rank-return" aria-label="返回导航">
        <button className="rank-back" type="button" onClick={goBack}>← {returnLabel(backTo)}</button>
      </nav>
      <h1>我的试卷</h1>
      {!signedIn ? <p>登录后即可导入自己的试卷。 <a href="/login">登录</a></p> : <form onSubmit={submit}>
        <fieldset disabled={busy}>
          <legend>导入试卷</legend>
          <label htmlFor="paper-exam">考试名称</label>
          <input id="paper-exam" name="exam" maxLength={60} placeholder="例如，成都中考" required />
          <label htmlFor="paper-subject">科目</label>
          <input id="paper-subject" name="subject" list="paper-subjects" defaultValue="数学" maxLength={30} required />
          <datalist id="paper-subjects"><option value="数学" /><option value="计算机" /><option value="软件构造" /></datalist>
          <label htmlFor="paper-year">年份（可选）</label>
          <input id="paper-year" name="year" type="number" min={1900} max={2100} />
          <label htmlFor="paper-edition">卷别（可选）</label>
          <input id="paper-edition" name="paper" maxLength={60} placeholder="例如，A 卷" />
          <label htmlFor="paper-files">试卷和参考答案</label>
          <input id="paper-files" name="papers" type="file" multiple required
            accept=".pdf,.docx,.jpg,.jpeg,.png,.webp" aria-describedby="paper-help" />
          <p className="subject" id="paper-help">支持 PDF、Word（.docx）、JPG、PNG、WebP。可以同时选择试卷和答案，总计不超过 16 页、15 MiB。</p>
          <label className="paper-consent"><input type="checkbox" name="consent" required />
            我有权使用这些资料，并同意将文件中用于识别的内容发送给 DeepSeek。</label>
          <button className="primary-button" type="submit">导入试卷</button>
        </fieldset>
      </form>}
      {busy && <LoadingProgress label="正在识别题目并核对参考答案…" />}
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
    </section>
    {signedIn && <section className="account-card">
      <h2>已导入的试卷</h2>
      {loading ? <p role="status">正在读取试卷…</p> : !papers.length && <p>暂无试卷。</p>}
      <ul className="paper-list">{papers.map((paper) => <li key={paper.id}>
        <button className="quiet-button" type="button" disabled={busy} onClick={() => void openPaper(paper.id)}>{paperTitle(paper)}</button>
        <p className="subject">{paper.question_count} 道题 · {paperCounts(paper)}</p>
        {removeId === paper.id ? <div className="quiz-actions">
          <button className="quiet-button" type="button" onClick={() => setRemoveId(null)}>取消</button>
          <button className="quiet-button" type="button" disabled={busy} onClick={() => void removePaper(paper.id)}>确认移除</button>
        </div> : <button className="quiet-button" type="button" disabled={busy} onClick={() => setRemoveId(paper.id)}>移除</button>}
        {active?.id === paper.id && paperDetail()}
      </li>)}</ul>
    </section>}
  </main>
}
