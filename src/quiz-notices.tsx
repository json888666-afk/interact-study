import { useEffect, useId, useRef, useState, type ReactNode } from 'react'

const NOTICE_PREFIXES = {
  replacement: 'quiz-replacement:',
  celebration: 'quiz-celebration:',
  pass: 'quiz-pass:',
} as const

export function useNotice(kind: keyof typeof NOTICE_PREFIXES = 'replacement') {
  const [dismissed, setDismissed] = useState<string[]>([])
  const prefix = NOTICE_PREFIXES[kind]
  const storage = kind === 'replacement' ? sessionStorage : localStorage
  const [initialSeen] = useState(() => new Set(Object.keys(storage).filter((key) => key.startsWith(prefix))))
  const remember = (id: string) => storage.setItem(prefix + id, 'seen')
  return [
    (id: string) => dismissed.includes(id) || initialSeen.has(prefix + id),
    (id: string) => {
      remember(id)
      setDismissed((previous) => [...previous, id])
    },
    remember,
  ] as const
}

function QuizDialog({ title, message, action, celebrating = false, showStay = true, children, onOpen, onClose }: {
  title: string
  message: string
  action: string
  celebrating?: boolean
  showStay?: boolean
  children?: ReactNode
  onOpen?: () => void
  onClose: (continueQuiz: boolean) => void
}) {
  const id = useId()
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    dialog.current?.showModal()
    onOpen?.()
  }, [])
  return (
    <dialog ref={dialog} className={`quiz-replacement-dialog${celebrating ? ' quiz-celebration-dialog' : ''}`}
      aria-labelledby={id + '-title'} aria-describedby={id + '-message'}
      onClose={(event) => onClose(event.currentTarget.returnValue === 'continue')}>
      {children}
      <h3 id={id + '-title'}>{title}</h3>
      <p id={id + '-message'}>{message}</p>
      <form method="dialog">
        {celebrating && showStay && <button className="quiet-button" value="stay">留在本题</button>}
        <button className="primary-button" value="continue" autoFocus>{action}</button>
      </form>
    </dialog>
  )
}

export function ReplacementNotice({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return <QuizDialog title="题目已更新" message={message} action="继续作答" onClose={onDismiss} />
}

export function CelebrationNotice({ action, variant = 'stars', title = '知识点攻克！',
  message = '恭喜你，成功攻克了一个新知识点！继续努力，把下一关也拿下。',
  showStay = true, onOpen, onClose }: {
  action: string
  variant?: 'stars' | 'badge'
  title?: string
  message?: string
  showStay?: boolean
  onOpen: () => void
  onClose: (continueQuiz: boolean) => void
}) {
  return (
    <QuizDialog title={title} message={message} action={action} celebrating showStay={showStay}
      onOpen={onOpen} onClose={onClose}>
      {variant === 'badge' ? <>
        <div className="quiz-badge-scene" aria-hidden="true">
          <span className="quiz-badge-halo" />
          <span className="quiz-badge-ribbons">
            <i className="quiz-badge-ribbon" />
            <i className="quiz-badge-ribbon" />
          </span>
          <span className="quiz-badge">
            <svg viewBox="0 0 32 32" width="34" height="34" fill="none" stroke="currentColor"
              strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 8.2c4-1.5 7.4-.4 11 2.2 3.6-2.6 7-3.7 11-2.2v15.6c-4-1.5-7.4-.4-11 2.2-3.6-2.6-7-3.7-11-2.2z" />
              <path d="M16 10.4v15.6" />
            </svg>
          </span>
        </div>
        <p className="quiz-pass-badge">知识 +1</p>
      </> : <>
        <div className="quiz-confetti" aria-hidden="true">
          {Array.from({ length: 9 }, (_, index) => <i key={index} />)}
        </div>
        <div className="quiz-stars" aria-hidden="true"><span>★</span><span>★</span><span>★</span></div>
      </>}
    </QuizDialog>
  )
}
