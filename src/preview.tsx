import { useEffect, useMemo, useRef, useState } from 'react'
import type { Lesson } from './lessons'

const MESSAGE_CHANNEL = 'interact-study-preview'
const READY_TIMEOUT_MS = 8000

function createDocument(lesson: Lesson, previewId: string, hostOrigin: string) {
  // The data literal cannot close the bootstrap script or add outer markup.
  const data = JSON.stringify({
    html: lesson.html,
    css: lesson.css,
    javascript: lesson.javascript,
    previewId,
    hostOrigin,
    channel: MESSAGE_CHANNEL,
  }).replace(/</g, '\\u003c')
  const policy = [
    "default-src 'none'",
    "script-src 'nonce-" + previewId + "'",
    "style-src 'unsafe-inline'",
    'img-src data:',
    "base-uri 'none'",
    "form-action 'none'",
  ].join('; ')

  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="${policy}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root { font-family: system-ui, "Microsoft YaHei", sans-serif; color: #17362e; }
body { margin: 0; background: #fff; }
</style>
</head>
<body>
<div id="lesson"></div>
<script nonce="${previewId}">
(() => {
  const data = ${data};
  let failed = false;
  function notify(type, message) {
    window.parent.postMessage({
      channel: data.channel, previewId: data.previewId, type, message
    }, data.hostOrigin);
  }
  function report(message) {
    failed = true;
    notify('error', String(message).slice(0, 400));
  }
  window.addEventListener('error', (event) => report(event.message || '脚本执行失败'));
  window.addEventListener('unhandledrejection', (event) => report(event.reason));
  window.addEventListener('load', () => {
    if (!failed) notify('ready');
  }, { once: true });
  const style = document.createElement('style');
  style.textContent = data.css;
  document.head.append(style);
  document.querySelector('#lesson').innerHTML = data.html;
  const script = document.createElement('script');
  script.nonce = data.previewId;
  script.textContent = data.javascript;
  document.body.append(script);
})();
</script>
</body>
</html>`
}

type PreviewStatus = { kind: 'loading' | 'ready' } | { kind: 'error'; message: string }

function PreviewFrame({ lesson }: { lesson: Lesson }) {
  const iframe = useRef<HTMLIFrameElement>(null)
  const [previewId] = useState(() => crypto.randomUUID().replace(/-/g, ''))
  const [status, setStatus] = useState<PreviewStatus>({ kind: 'loading' })
  const [listening, setListening] = useState(false)
  const srcDoc = useMemo(() => createDocument(lesson, previewId, window.location.origin), [lesson, previewId])

  useEffect(() => {
    const timeout = window.setTimeout(() => setStatus((current) => current.kind === 'loading'
      ? { kind: 'error', message: '等待预览响应超时。' } : current), READY_TIMEOUT_MS)

    function onMessage(event: MessageEvent) {
      if (event.source !== iframe.current?.contentWindow || event.origin !== 'null') return
      const message = event.data
      if (!message || typeof message !== 'object' || message.channel !== MESSAGE_CHANNEL || message.previewId !== previewId) return
      if (message.type === 'ready' && message.message === undefined) {
        setStatus((current) => current.kind === 'loading' ? { kind: 'ready' } : current)
      } else if (message.type === 'error' && typeof message.message === 'string' && message.message.length <= 400) {
        setStatus({ kind: 'error', message: message.message })
      }
    }

    window.addEventListener('message', onMessage)
    setListening(true)
    return () => {
      window.removeEventListener('message', onMessage)
      window.clearTimeout(timeout)
    }
  }, [previewId])

  return (
    <>
      {status.kind === 'loading' && <p className="preview-loading" role="status">正在加载预览…</p>}
      {status.kind === 'error'
        ? <div className="preview-error" role="alert"><strong>预览运行失败</strong><p>{status.message}</p></div>
        : listening && <iframe ref={iframe} srcDoc={srcDoc} sandbox="allow-scripts" title="交互教学预览" />}
    </>
  )
}

export function Preview({ lesson, onRegenerate }: { lesson: Lesson; onRegenerate: () => void }) {
  const [attempt, setAttempt] = useState(0)
  return (
    <section className="preview-shell" aria-label="教学预览">
      <div className="preview-toolbar">
        <span><span className="status-dot" />交互预览</span>
        <div>
          <button type="button" className="quiet-button" onClick={() => setAttempt((value) => value + 1)}>重新运行</button>
          <button type="button" className="quiet-button" onClick={onRegenerate}>重新加载内容</button>
        </div>
      </div>
      <PreviewFrame key={attempt} lesson={lesson} />
    </section>
  )
}
