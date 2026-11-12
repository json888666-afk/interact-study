import { useEffect, useId, useRef, useState, type ReactNode } from 'react'

export function useNotice(kind = 'replacement') {
  const [dismissed, setDismissed] = useState<string[]>([])
  const prefix = kind === 'replacement' ? 'quiz-replacement:' : 'quiz-celebration:'
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

function QuizDialog({ title, message, action, celebrating = false, children, onOpen, onClose }: {
  title: string
  message: string
  action: string
  celebrating?: boolean
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
        {celebrating && <button className="quiet-button" value="stay">留在本题</button>}
        <button className="primary-button" value="continue" autoFocus>{action}</button>
      </form>
    </dialog>
  )
}

export function ReplacementNotice({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return <QuizDialog title="题目已更新" message={message} action="继续作答" onClose={onDismiss} />
}

export function CelebrationNotice({ action, onOpen, onClose }: {
  action: string
  onOpen: () => void
  onClose: (continueQuiz: boolean) => void
}) {
  return (
    <QuizDialog title="知识点攻克！" message="恭喜你，成功攻克了一个新知识点！继续努力，把下一关也拿下。"
      action={action} celebrating onOpen={onOpen} onClose={onClose}>
      <div className="quiz-confetti" aria-hidden="true">
        {Array.from({ length: 9 }, (_, index) => <i key={index} />)}
      </div>
      <div className="quiz-stars" aria-hidden="true"><span>★</span><span>★</span><span>★</span></div>
    </QuizDialog>
  )
}
