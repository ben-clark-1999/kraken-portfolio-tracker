interface Props {
  suggestions: string[]
  onPick: (text: string) => void
}

export default function SuggestionPills({ suggestions, onPick }: Props) {
  return (
    <div className="flex flex-wrap justify-center gap-2 mt-8">
      {suggestions.map((s) => (
        <button
          key={s}
          type="button"
          onClick={() => onPick(s)}
          className="px-4 py-2 rounded-full text-sm text-txt-secondary bg-surface-raised border border-surface-border hover:bg-surface-hover hover:text-txt-primary transition-colors duration-200"
        >
          {s}
        </button>
      ))}
    </div>
  )
}
