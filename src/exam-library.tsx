import { useEffect, useState, type FormEvent } from 'react'
import { learningRequest } from './learning-api'
import { LoadingProgress } from './loading-progress'

type Paper = {
  id: string
  exam: string
  subject: string
  year: number | null
  paper: string | null
  filenames: string[]
  question_count: number
  ready_count: number
  pending_count: number
  review_count: number
}

type LibraryQuestion = {
  id: number; number: string; section: string | null; stem: string; options: string[]; tags: string[]
  status: 'ready' | 'review_only' | 'pending'; reason: string; file: string; page: number
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
  return `${paper.ready_count} 道可判分 · ${paper.review_count} 道仅供复习 · ${paper.pending_count} 道待确认`
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

export function ExamLibrary({ signedIn }: { signedIn: boolean }) {
  const [papers, setPapers] = useState<Paper[]>([])
  const [active, setActive] = useState<PaperDetail | null>(null)
  const [loading, setLoading] = useState(signedIn)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [removeId, setRemoveId] = useState<string | null>(null)
  const [repair, setRepair] = useState<'paper' | number | null>(null)

  useEffect(() => {
    if (!signedIn) return
    const controller = new AbortController()
    learningRequest<{ papers: Paper[] }>(libraryUrl, { signal: controller.signal })
      .then((result) => setPapers(result.papers))
      .catch((cause) => { if (!controller.signal.aborted) setError(cause.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [signedIn])

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
      const result = await learningRequest<{ paper: PaperDetail; duplicate: boolean }>(libraryUrl + '/imports', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          exam: String(values.get('exam')).trim(), subject: values.get('subject'),
          year: Number(values.get('year')) || null, paper: String(values.get('paper')).trim() || null,
          consent: values.get('consent') === 'on', files: await Promise.all(files.map(encodedFile)),
        }),
      })
      setPapers((current) => [result.paper, ...current.filter((paper) => paper.id !== result.paper.id)])
      setActive(result.paper)
      setRepair(null)
      setMessage(result.duplicate ? '这份试卷已在题库中。' : `已导入 ${result.paper.question_count} 道题，其中 ${result.paper.ready_count} 道可用于自动判分。`)
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
    try {
      const result = await learningRequest<{ paper: PaperDetail }>(libraryUrl + '/' + id, {})
      setActive(result.paper)
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
      setPapers((current) => current.map((paper) => paper.id === result.paper.id ? result.paper : paper))
      setActive(result.paper)
      setMessage(repair === 'paper' ? '重新识别完成，已合并到原试卷。' : '已更新这道题。')
      setRepair(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '识别失败，请重试。')
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

  return <main className="page account-page exam-library">
    <section className="account-card">
      <a href="/">← 返回首页</a>
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
      </li>)}</ul>
      {active && <section className="paper-detail" aria-label="试卷题目">
        <h3>{paperTitle(active)}</h3>
        <p className="subject">{active.filenames.join('、')}</p>
        <p className="subject">{paperCounts(active)}</p>
        {repair === 'paper' ? <RepairForm target="paper" busy={busy} onCancel={() => setRepair(null)} onSubmit={submitRepair} />
          : <button className="quiet-button" type="button" disabled={busy} onClick={() => setRepair('paper')}>重新识别</button>}
        <ol>{active.questions.map((question) => <li key={question.id}>
          <p><strong>{question.section ? question.section + ' · ' : ''}{question.number}.</strong> {question.stem || '正文待核对'}</p>
          {!!question.options.length && <ol type="A">{question.options.map((option, i) => <li key={i}>{option}</li>)}</ol>}
          <p className="subject">{question.file} · 第 {question.page} 页 · {question.status === 'ready' ? '可判分' : question.status === 'pending' ? '待确认' : '仅供复习'}</p>
          {question.status === 'pending' && <><p>{question.reason}</p>
            {repair === question.id ? <RepairForm target={question.id} busy={busy} onCancel={() => setRepair(null)} onSubmit={submitRepair} />
              : <button className="quiet-button" type="button" disabled={busy} onClick={() => setRepair(question.id)}>重新提交这道题</button>}
          </>}
          <div className="quiz-actions">{question.tags.map((tag) =>
            <a key={tag} href={'/?question=' + encodeURIComponent(`请讲解${tag}`)}>学习{tag}</a>)}</div>
        </li>)}</ol>
      </section>}
    </section>}
  </main>
}
