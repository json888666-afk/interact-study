import type { ReactNode } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import type { PluggableList } from 'unified'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'

const remarkPlugins: PluggableList = [remarkGfm, remarkMath]
const rehypePlugins: PluggableList = [[rehypeKatex, { throwOnError: false, strict: 'ignore' }]]

const components: Components = {
  table: ({ node: _node, ...props }) => <div className="table-scroll"><table {...props} /></div>,
  a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
}

const inlineComponents: Components = {
  p: ({ children }) => <>{children as ReactNode}</>,
}

export function Markdown({ children, className = '' }: { children: string; className?: string }) {
  return (
    <div className={['markdown', className].filter(Boolean).join(' ')}>
      <ReactMarkdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  )
}

export function InlineMarkdown({ children }: { children: string }) {
  return (
    <span className="markdown-inline">
      <ReactMarkdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins} components={inlineComponents}>
        {children}
      </ReactMarkdown>
    </span>
  )
}
