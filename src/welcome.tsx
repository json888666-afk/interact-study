import { useEffect, useState } from 'react'
import { GoalReviewDialog, authRequest, finishAuth, type Profile } from './account-pages'

export const GUEST_KEY = 'interact-study.guest-entry'

type Stage = Profile['education_stage']

const STAGES: { name: Stage; mark: string; note: string }[] = [
  { name: '幼儿园', mark: '幼', note: '用游戏和图形建立直觉' },
  { name: '小学', mark: '小', note: '打基础，学会用图想问题' },
  { name: '初中', mark: '初', note: '函数、几何与中考题型' },
  { name: '高中', mark: '高', note: '抽象、推理与高考题型' },
  { name: '本科', mark: '本', note: '定义、推导与算法可视化' },
  { name: '硕士', mark: '硕', note: '证明、反例与研究问题' },
  { name: '博士', mark: '博', note: '形式化与开放问题' },
]

const GOAL_EXAMPLES = ['准备小升初数学', '理解二次函数图像', '学习递归', '准备期末数学考试']

export function WelcomeGate({ onGuest }: { onGuest: () => void }) {
  const [a, setA] = useState(1)
  const progress = ((a + 1.5) / 3) * 100
  const points = Array.from({ length: 49 }, (_, index) => {
    const x = -1.8 + (3.6 * index) / 48
    return [160 + x * 70, 100 - a * x * x * 20]
  })
  const curve = points.map(([x, y], index) => `${index === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`).join(' ')

  return <main className="welcome-page">
    <header className="welcome-top">
      <a className="brand" href="/">
        <span className="brand-mark" aria-hidden="true">∿</span>可视化理论中心
      </a>
      <nav aria-label="欢迎页导航">
        <a href="/leaderboard">排行榜</a>
        <a href="/login">登录</a>
      </nav>
    </header>

    <section className="welcome-hero" aria-labelledby="welcome-title">
      <p className="welcome-eyebrow">AI 交互式学习 · 数学与计算机</p>
      <h1 id="welcome-title">把问题<span>动起来。</span></h1>
      <p className="welcome-copy">输入一个问题，生成可以亲手拖动的教学页；看懂之后再练两道题。</p>
      <div className="welcome-actions">
        <a className="welcome-primary" href="/register">我是新用户，开始学习</a>
        <a className="welcome-secondary" href="/login">我已有账户，登录</a>
      </div>
      <button className="welcome-guest" type="button" onClick={onGuest}>先逛逛 <span aria-hidden="true">→</span></button>
    </section>

    <aside className="welcome-preview" aria-label="示例预览">
      <div className="preview-card">
        <div className="preview-head">
          <span>交互演示</span>
          <span className="preview-chip">可拖动</span>
        </div>
        <div className="preview-graph">
          <svg viewBox="0 0 320 200" role="img" aria-label="抛物线示意图">
            <line x1="24" y1="100" x2="296" y2="100" />
            <line x1="160" y1="16" x2="160" y2="184" />
            <path d={curve} />
            <circle cx="160" cy="100" r="4" />
          </svg>
          <span className="preview-label">a = {a.toFixed(1)}</span>
        </div>
        <input className="preview-range" type="range" min="-1.5" max="1.5" step="0.1" value={a}
          aria-label="参数 a" onChange={(event) => setA(Number(event.target.value))}
          style={{ background: `linear-gradient(to right, var(--green) 0 ${progress}%, #e2e8db ${progress}% 100%)` }} />
        <div className="preview-caption">
          <h2>二次函数开口方向</h2>
          <span className="preview-status">{a > 0 ? '开口向上' : a < 0 ? '开口向下' : '变成直线'}</span>
        </div>
        <p>拖动 a，看抛物线怎么翻转。</p>
      </div>
    </aside>
  </main>
}

export function Onboarding({ returnTo }: { returnTo: string }) {
  const [step, setStep] = useState<1 | 2>(1)
  const [stage, setStage] = useState<Stage | null>(null)
  const [goal, setGoal] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function complete() {
    if (!stage || !goal.trim() || busy) return
    setBusy(true)
    setError('')
    try {
      await authRequest('profile', { education_stage: stage, goal: goal.trim() })
      finishAuth('/?welcome=1&next=' + encodeURIComponent(returnTo))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '保存失败，请重试。')
      setBusy(false)
    }
  }

  return <main className="onboarding-page">
    {busy && <GoalReviewDialog />}
    <section className="onboarding-card" aria-labelledby="onboarding-title">
      <a className="brand onboarding-brand" href="/">
        <span className="brand-mark" aria-hidden="true">∿</span>可视化理论中心
      </a>
      <div className="step-dots" aria-label={`第 ${step} 步，共 2 步`}>
        <span className={step === 1 ? 'active' : ''} />
        <span className={step === 2 ? 'active' : ''} />
      </div>

      {step === 1 ? <>
        <p className="onboarding-kicker">开始之前</p>
        <h1 id="onboarding-title">先认识一下你</h1>
        <p className="onboarding-copy">这些信息只用于调整讲解和练习难度，之后可以在个人设置里修改。</p>
        <div className="stage-grid" role="group" aria-label="学习阶段">
          {STAGES.map((item) => <button key={item.name} type="button" className="stage-card"
            aria-pressed={stage === item.name} onClick={() => setStage(item.name)}>
            <span className="stage-mark" aria-hidden="true">{item.mark}</span>
            <span><strong>{item.name}</strong><small>{item.note}</small></span>
          </button>)}
        </div>
        <div className="onboarding-actions">
          <button className="primary-button" type="button" disabled={!stage} onClick={() => setStep(2)}>下一步</button>
        </div>
      </> : <>
        <p className="onboarding-kicker">第 2 步</p>
        <h1 id="onboarding-title">最近想弄懂什么？</h1>
        <p className="onboarding-copy">写一句就好。比如一门考试、一个知识点，或者一个想做的项目。</p>
        <label className="onboarding-label" htmlFor="onboarding-goal">近期学习目标</label>
        <textarea id="onboarding-goal" className="onboarding-goal" value={goal} maxLength={300} rows={4}
          placeholder="例如：这周学会用图像判断二次函数的开口和顶点。" aria-describedby="onboarding-goal-help"
          onChange={(event) => setGoal(event.target.value)} />
        <p className="subject" id="onboarding-goal-help">只有写明具体考试时，练习才会检索该考试的真题。</p>
        <div className="goal-examples">
          {GOAL_EXAMPLES.map((example) => <button key={example} type="button" className="example-chip"
            onClick={() => setGoal(example)}>{example}</button>)}
        </div>
        {error && <p className="onboarding-error" role="alert">{error}</p>}
        <div className="onboarding-actions">
          <button className="quiet-button" type="button" onClick={() => setStep(1)}>返回</button>
          <button className="primary-button" type="button" disabled={!goal.trim()} onClick={() => void complete()}>
            完成，进入可视化理论中心
          </button>
        </div>
      </>}
    </section>
  </main>
}

export function WelcomeCelebration({ next }: { next: string }) {
  useEffect(() => {
    const timer = window.setTimeout(() => finishAuth(next), 4000)
    return () => window.clearTimeout(timer)
  }, [next])

  return <main className="celebration" role="status" aria-live="polite">
    <span className="celebration-ring ring-one" aria-hidden="true" />
    <span className="celebration-ring ring-two" aria-hidden="true" />
    <span className="celebration-spark spark-one" aria-hidden="true" />
    <span className="celebration-spark spark-two" aria-hidden="true" />
    <span className="celebration-spark spark-three" aria-hidden="true" />
    <div className="celebration-content">
      <span className="brand-mark celebration-mark" aria-hidden="true">∿</span>
      <p className="celebration-kicker">设置完成</p>
      <h1>欢迎来到<br /><span>可视化理论中心</span></h1>
      <p>你的学习空间已准备好。</p>
      <button className="primary-button celebration-button" type="button" onClick={() => finishAuth(next)}>
        开始学习 <span aria-hidden="true">→</span>
      </button>
    </div>
  </main>
}
