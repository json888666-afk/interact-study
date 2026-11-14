import { useEffect, useRef, useState, type FormEvent } from 'react'
import { learningRequest } from './learning-api'
import { LoadingProgress } from './loading-progress'

export const educationStages = ['幼儿园', '小学', '初中', '高中', '本科', '硕士', '博士'] as const
export type Profile = { education_stage: (typeof educationStages)[number]; goal: string }
type Credentials = { username: string; password: string }
export type User = { id: string; username: string; profile: Profile | null; needs_goal_review?: boolean }
export const AUTH_CHANGE_KEY = 'interact-study.auth-change'

export function authRequest(action: 'me' | 'register' | 'login' | 'logout' | 'profile',
  options?: Credentials | (Credentials & { profile: Profile }) | Profile, signal?: AbortSignal) {
  return learningRequest<{ user: User | null }>('/api/auth/' + action, {
    method: action === 'me' ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: options ? JSON.stringify(options) : undefined,
    signal,
  })
}

export function finishAuth(destination: string = '/') {
  try {
    localStorage.setItem(AUTH_CHANGE_KEY, crypto.randomUUID())
  } catch {
    // The cookie remains the source of truth when browser storage is unavailable.
  }
  window.location.replace(destination)
}

function safeReturnPath(value: string): string {
  const [path] = value.split('?')
  if (path === '/' || path === '/study' || path === '/leaderboard' || path === '/exam-library') return value
  return '/'
}

function readProfile(values: FormData): Profile {
  const stage = educationStages.find((item) => item === values.get('education_stage'))
  const goal = String(values.get('goal') ?? '').trim()
  if (!stage || !goal || goal.length > 300) throw new Error('请选择学习阶段，并填写 1–300 字的近期学习目标。')
  return { education_stage: stage, goal }
}

export function GoalReviewDialog() {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { dialog.current?.showModal() }, [])
  return <dialog ref={dialog} className="account-dialog" aria-label="正在审核目标"
    onCancel={(event) => event.preventDefault()}>
    <LoadingProgress label="正在审核目标…" duration={1500} />
  </dialog>
}

function ProfileFields({ profile, disabled }: { profile?: Profile | null; disabled: boolean }) {
  return <>
    <label htmlFor="education-stage">学习阶段</label>
    <select id="education-stage" name="education_stage" defaultValue={profile?.education_stage ?? ''} disabled={disabled} required>
      <option value="" disabled>请选择学习阶段</option>
      {educationStages.map((stage) => <option key={stage}>{stage}</option>)}
    </select>
    <label htmlFor="learning-goal">近期学习目标</label>
    <textarea id="learning-goal" name="goal" rows={3} maxLength={300} disabled={disabled} required
      defaultValue={profile?.goal ?? ''} placeholder="例如，本周学会用图像判断二次函数的开口和顶点。"
      aria-describedby="learning-goal-help" />
    <p className="subject" id="learning-goal-help">用于调整讲解和练习难度；只有写明具体考试时才会检索该考试真题，之后可在个人设置修改。</p>
  </>
}

export function authLink(mode: 'login' | 'register', fromLeaderboard: boolean) {
  return '/' + mode + (fromLeaderboard ? '?next=%2Fleaderboard' : '')
}

export function AuthForm({ mode }: { mode: 'login' | 'register' }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const registering = mode === 'register'
  const title = registering ? '注册' : '登录'
  const fromLeaderboard = new URLSearchParams(window.location.search).get('next') === '/leaderboard'

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const values = new FormData(event.currentTarget)
    setBusy(true)
    setError('')
    try {
      const credentials = { username: String(values.get('username')), password: String(values.get('password')) }
      await authRequest(mode, credentials)
      finishAuth(fromLeaderboard ? '/leaderboard' : '/')
    } catch (error) {
      setError(error instanceof Error ? error.message : '请求失败，请重试。')
      setBusy(false)
    }
  }

  return (
    <main className="page account-page">
      <form className="account-card" onSubmit={submit}>
        <h1>{title}</h1>
        <label htmlFor="username">用户名</label>
        <input id="username" name="username" autoComplete="username" minLength={3} maxLength={24} required />
        {registering && <p className="subject">3–24 个字母、汉字、数字、下划线或连字符。</p>}
        <label htmlFor="password">密码</label>
        <input id="password" name="password" type="password" autoComplete={registering ? 'new-password' : 'current-password'}
          pattern={registering ? '(?=.*[A-Za-z])(?=.*[0-9]).*' : undefined}
          title={registering ? '至少 8 个字符，包含英文字母和数字。' : undefined}
          aria-describedby={registering ? 'password-rules' : undefined}
          minLength={8} maxLength={128} required />
        {registering && <p className="subject" id="password-rules">至少 8 个字符，包含英文字母和数字；注册后再设置学习阶段和目标。</p>}
        {error && <p role="alert">{error}</p>}
        <button className="primary-button" type="submit" disabled={busy}>{busy ? '正在提交…' : title}</button>
        <a href={authLink(registering ? 'login' : 'register', fromLeaderboard)}>
          {registering ? '已有账户，去登录' : '创建账户'}
        </a>
      </form>
    </main>
  )
}

export function LearningSettings({ user }: { user: User }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const needsSetup = !user.profile || user.needs_goal_review
  const params = new URLSearchParams(window.location.search)
  const current = window.location.pathname + window.location.search
  const returnTo = safeReturnPath(params.get('from') ?? (window.location.pathname === '/profile' ? '/' : current))

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const profile = readProfile(new FormData(event.currentTarget))
      const result = await authRequest('profile', profile)
      if (!result.user) throw new Error('请重新登录后保存个人设置。')
      finishAuth(returnTo)
    } catch (error) {
      setError(error instanceof Error ? error.message : '保存失败，请重试。')
      setBusy(false)
    }
  }

  return (
    <main className="page account-page">
      {busy && <GoalReviewDialog />}
      <form className="account-card" onSubmit={submit}>
        <nav className="rank-return" aria-label="返回导航">
          <button className="rank-back" type="button" onClick={() => window.location.replace(returnTo)}>← {returnLabel(returnTo)}</button>
        </nav>
        <h1>{needsSetup ? '完善个人资料' : '个人设置'}</h1>
        {needsSetup && <p>学习目标通过审核后，即可开始个性化学习。</p>}
        <ProfileFields profile={user.profile} disabled={busy} />
        {error && <p role="alert">{error}</p>}
        <button className="primary-button" type="submit" disabled={busy}>{busy ? '正在保存…' : '保存个人设置'}</button>
      </form>
    </main>
  )
}

export function safeReturnLocation(value: string | null) {
  if (!value) return null
  const [path, query] = value.split('?')
  if (path === '/' || path === '/profile' || path === '/exam-library' || path === '/leaderboard') return path
  if (path !== '/study') return null
  const practice = new URLSearchParams(query).get('practice')
  return practice ? '/study?practice=' + encodeURIComponent(practice) : '/study'
}

export function leaderboardLink() {
  const current = window.location.pathname + window.location.search
  const from = window.location.pathname === '/leaderboard' ? null : safeReturnLocation(current)
  return '/leaderboard' + (from ? '?from=' + encodeURIComponent(from) : '')
}

export function returnLabel(value: string) {
  const path = value.split('?')[0]
  if (path === '/study') return '返回学习'
  if (path === '/leaderboard') return '返回排行榜'
  if (path === '/exam-library') return '返回我的试卷'
  if (path === '/profile') return '返回个人设置'
  return '返回首页'
}

function returnFromLeaderboard() {
  const from = safeReturnLocation(new URLSearchParams(window.location.search).get('from'))
  window.location.replace(from && from !== '/leaderboard' ? from : '/')
}

type Rank = { username: string; points: number; rank: number }
type Rankings = { entries: Rank[]; has_more: boolean; me: (Rank & { listed_page: number | null }) | null }

const AVATAR_COLORS = ['#0c654b', '#7a5a3a', '#506b8c', '#8a4b5d', '#5e7448', '#6b5b8a']

function avatarFor(username: string) {
  const chars = Array.from(username.trim() || '?')
  const label = (chars[0] ?? '?').toUpperCase()
  const sum = chars.reduce((total, char) => total + (char.codePointAt(0) ?? 0), 0)
  return { label, color: AVATAR_COLORS[sum % AVATAR_COLORS.length] }
}

function GuestLeaderboardNotice({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    dialog.current?.showModal()
  }, [])
  return (
    <dialog className="account-dialog" ref={dialog} aria-labelledby="guest-rank-title"
      aria-describedby="guest-rank-description" onClose={onClose}>
      <h2 id="guest-rank-title">加入学习排行榜</h2>
      <p id="guest-rank-description">你还没有登录，暂时无法参与排行。登录或注册，即可开启个性化学习。</p>
      <div className="account-dialog-actions">
        <a className="primary-button" href={authLink('register', true)}>注册</a>
        <a className="quiet-button" href={authLink('login', true)}>登录</a>
        <form method="dialog"><button className="quiet-button" autoFocus>继续浏览</button></form>
      </div>
    </dialog>
  )
}

export function Leaderboard({ guest }: { guest: boolean }) {
  const [page, setPage] = useState(1)
  const [attempt, setAttempt] = useState(0)
  const [data, setData] = useState<Rankings | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(guest)
  const heading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    const controller = new AbortController()
    setData(null)
    setError('')
    learningRequest<Rankings>('/api/leaderboard?page=' + page, { signal: controller.signal })
      .then((result) => { if (!controller.signal.aborted) setData(result) })
      .catch(() => { if (!controller.signal.aborted) setError('无法加载排行榜，请重试。') })
    return () => controller.abort()
  }, [page, attempt])

  const myPage = data?.me?.listed_page
  const backTo = safeReturnLocation(new URLSearchParams(window.location.search).get('from')) ?? '/'
  const showPodium = page === 1 && !!data && data.entries.length >= 3
  const listEntries = data ? (showPodium ? data.entries.slice(3) : data.entries) : []

  return (
    <main className="page account-page">
      {guest && notice && <GuestLeaderboardNotice onClose={() => {
        setNotice(false)
        heading.current?.focus()
      }} />}
      <section className="account-card rankings">
        <nav className="rank-return" aria-label="返回导航">
          <button className="rank-back" type="button" onClick={returnFromLeaderboard}>← {returnLabel(backTo)}</button>
        </nav>
        <h1 ref={heading} tabIndex={-1}>排行榜</h1>
        <p className="rank-sub">完成一次练习并达到 90%，就能留下 1 分。</p>
        {error && <p role="alert">{error} <button type="button" className="quiet-button" onClick={() => setAttempt(attempt + 1)}>重试</button></p>}
        {!data && !error && <p role="status">正在加载排行榜…</p>}
        {data && <>
          {data.me && <div className="rank-self">
            <div className="rank-self-main">
              <span className="rank-self-kicker">我的排名</span>
              <strong>第 {data.me.rank} 名</strong>
            </div>
            <div className="rank-self-side">
              <span className={data.me.listed_page === null ? 'rank-self-muted' : undefined}>
                {data.me.listed_page === null ? '暂未上榜 · ' : ''}当前积分：<strong>{data.me.points}</strong>分
              </span>
              {typeof myPage === 'number' && myPage !== page &&
                <button className="quiet-button" type="button" onClick={() => setPage(myPage)}>查看我的名次</button>}
            </div>
          </div>}
          {showPodium && <ol className="rank-podium" aria-label="前三名">
            {data.entries.slice(0, 3).map((entry, index) => {
              const place = index + 1
              const mine = entry.username === data.me?.username
              const avatar = avatarFor(entry.username)
              return <li key={entry.username} className={`rank-podium-item${mine ? ' rank-current-user' : ''}`}>
                <span className="rank-medal-wrap" aria-hidden="true">
                  <i className="rank-ribbon rank-ribbon-left" />
                  <i className="rank-ribbon rank-ribbon-right" />
                  <span className={`rank-medal rank-medal-${place}`}>{place}</span>
                </span>
                <span className="rank-avatar rank-avatar-podium" style={{ background: avatar.color }} aria-hidden="true">{avatar.label}</span>
                <span className="rank-podium-name">{entry.username}{mine && <span className="rank-you">你</span>}</span>
                <span className="rank-podium-points">{entry.points}<small>分</small></span>
              </li>
            })}
          </ol>}
          {!data.entries.length
            ? <p className="rank-empty">还没有人上榜，完成第一次练习就能成为第一名。</p>
            : !!listEntries.length && <table>
              <thead><tr><th scope="col">名次</th><th scope="col">学习者</th><th scope="col">积分</th></tr></thead>
              <tbody>{listEntries.map((entry) => {
                const mine = entry.username === data.me?.username
                const avatar = avatarFor(entry.username)
                return <tr key={entry.username} className={mine ? 'rank-current-user' : undefined}>
                  <td>{entry.rank}</td>
                  <td><span className="rank-user">
                    <span className="rank-avatar" style={{ background: avatar.color }} aria-hidden="true">{avatar.label}</span>
                    <span>{entry.username}</span>
                    {mine && <span className="rank-you">你</span>}
                  </span></td>
                  <td className="rank-points">{entry.points}</td>
                </tr>
              })}</tbody>
            </table>}
          {(page > 1 || data.has_more) && <div className="rank-pages">
            <button className="quiet-button" type="button" disabled={page === 1} onClick={() => setPage(page - 1)}>上一页</button>
            <span>第 {page} 页</span>
            <button className="quiet-button" type="button" disabled={!data.has_more} onClick={() => setPage(page + 1)}>下一页</button>
          </div>}
        </>}
      </section>
    </main>
  )
}
