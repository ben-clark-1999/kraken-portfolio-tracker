import { MessageSquareText } from 'lucide-react'

interface Props {
  strategyId: string
  personaKey: string
}

// TODO(backend): /api/agent/chat does not yet accept
//   mode=persona_conversational + strategy_id
// query params. Until it does, this tab cannot be wired up — the
// existing chat endpoint loads the unrestricted tool surface, which
// would allow place_paper_order / cancel_paper_order from a chat
// surface that the spec deliberately scopes read-only. See
// docs/superpowers/specs/2026-05-12-paper-trading-sandbox-design.md §7.2.

export default function PersonaChatTab({ personaKey }: Props) {
  return (
    <div className="px-6 py-8">
      <div className="max-w-md">
        <div className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-kraken/12 ring-1 ring-kraken/20 mb-4">
          <MessageSquareText
            aria-hidden="true"
            strokeWidth={1.5}
            className="h-4 w-4 text-kraken-light"
          />
        </div>

        <h3 className="text-base font-medium tracking-tight text-txt-primary">
          Persona chat
        </h3>

        <p className="mt-1 text-xs font-mono uppercase tracking-wider text-txt-muted">
          {personaKey}
        </p>

        <p className="mt-4 text-sm text-txt-secondary leading-relaxed">
          Conversational persona mode needs a backend endpoint that loads the
          persona prompt with a read-only tool surface (no order placement). It
          will land in a follow-up commit so this surface cannot accidentally
          place trades.
        </p>

        <p className="mt-3 text-xs text-txt-muted leading-relaxed">
          Meanwhile, see the Decisions tab for what the persona has done, and
          the main agent chat for general portfolio questions.
        </p>
      </div>
    </div>
  )
}
