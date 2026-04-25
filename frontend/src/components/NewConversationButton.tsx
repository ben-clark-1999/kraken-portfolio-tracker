interface Props {
  onClick: () => void
}

export default function NewConversationButton({ onClick }: Props) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-xs text-txt-muted hover:text-txt-secondary transition-colors"
    >
      New conversation
    </button>
  )
}
