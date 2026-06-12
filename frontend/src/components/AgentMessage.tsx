import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { AgentMessage as AgentMessageType } from '../types/agent'

interface Props {
  message: AgentMessageType
}

const components = {
  p: (props: any) => (
    <p className="text-[15px] leading-relaxed text-txt-primary my-3 first:mt-0 last:mb-0" {...props} />
  ),
  h1: (props: any) => (
    <h1 className="text-2xl font-semibold text-txt-primary mt-6 mb-2" {...props} />
  ),
  h2: (props: any) => (
    <h2 className="text-xl font-semibold text-txt-primary mt-6 mb-2" {...props} />
  ),
  h3: (props: any) => (
    <h3 className="text-base font-semibold text-txt-primary mt-4 mb-1" {...props} />
  ),
  strong: (props: any) => <strong className="font-semibold text-txt-primary" {...props} />,
  em: (props: any) => <em className="italic text-txt-secondary" {...props} />,
  ul: (props: any) => <ul className="my-3 pl-5 space-y-1 list-disc" {...props} />,
  ol: (props: any) => <ol className="my-3 pl-5 space-y-1 list-decimal" {...props} />,
  li: (props: any) => <li className="text-[15px] leading-relaxed text-txt-primary" {...props} />,
  a: (props: any) => (
    <a className="text-kraken hover:underline" target="_blank" rel="noreferrer" {...props} />
  ),
  blockquote: (props: any) => (
    <blockquote className="border-l-2 border-surface-border pl-3 text-txt-secondary italic my-3" {...props} />
  ),
  hr: () => <hr className="border-surface-border my-4" />,
  code: ({ inline, className, children, ...rest }: any) =>
    inline ? (
      <code
        className="px-1 py-0.5 rounded bg-surface-raised text-[13px] font-mono text-kraken-light"
        {...rest}
      >
        {children}
      </code>
    ) : (
      <code className={`block text-[13px] font-mono text-txt-primary ${className ?? ''}`} {...rest}>
        {children}
      </code>
    ),
  pre: (props: any) => (
    <pre
      className="bg-surface-raised border border-surface-border rounded-md p-3 overflow-x-auto my-3"
      {...props}
    />
  ),
  table: (props: any) => (
    <div className="my-3 rounded-md overflow-hidden border border-surface-border">
      <table className="w-full text-sm font-mono tabular-nums border-collapse" {...props} />
    </div>
  ),
  thead: (props: any) => <thead className="bg-surface-raised" {...props} />,
  th: (props: any) => (
    <th
      className="text-left text-xs uppercase tracking-wider text-txt-muted font-medium px-3 py-2 border-b border-surface-border"
      {...props}
    />
  ),
  tr: (props: any) => <tr className="border-b border-surface-border/60 last:border-b-0" {...props} />,
  td: (props: any) => <td className="text-sm text-txt-primary px-3 py-2 tabular-nums" {...props} />,
}

export default function AgentMessage({ message }: Props) {
  const safe = typeof message.content === 'string' ? message.content : ''

  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl bg-surface-raised border border-surface-border px-4 py-2.5 text-[15px] leading-relaxed text-txt-primary whitespace-pre-wrap break-words">
          {safe}
        </div>
      </div>
    )
  }

  return (
    <div className="text-[15px] leading-relaxed text-txt-primary font-sans">
      <Markdown remarkPlugins={[remarkGfm]} components={components}>
        {safe}
      </Markdown>
      {message.streaming && (
        <span className="inline-block w-1.5 h-4 bg-txt-muted animate-pulse-subtle ml-0.5 align-text-bottom" />
      )}
    </div>
  )
}
