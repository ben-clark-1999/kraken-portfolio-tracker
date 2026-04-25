import type { HITLState } from '../types/agent'

interface Props {
  hitl: HITLState
  onRespond: (approved: boolean) => void
}

export default function AgentHITL({ hitl, onRespond }: Props) {
  return (
    <p className="text-[15px] leading-relaxed text-txt-primary font-sans">
      {hitl.reason}{' '}
      <button
        type="button"
        onClick={() => onRespond(true)}
        className="text-txt-primary hover:underline hover:text-kraken transition-colors active:opacity-70"
      >
        Proceed
      </button>
      {' or '}
      <button
        type="button"
        onClick={() => onRespond(false)}
        className="text-txt-primary hover:underline hover:text-kraken transition-colors active:opacity-70"
      >
        cancel
      </button>
      .
    </p>
  )
}
