// Marca provisional de AssetControl (lienzo aprobado; logo definitivo en T9 de
// docs/05): barras de código con un punto cobalto.
export function Logo({ className = 'size-7' }: { className?: string }) {
  return (
    <span className={`flex shrink-0 items-center justify-center rounded-md bg-ink text-ink-foreground ${className}`} aria-hidden="true">
      <svg viewBox="0 0 24 24" className="size-[60%]">
        <rect x="5" y="6" width="2" height="12" rx="1" fill="currentColor" />
        <rect x="9" y="6" width="1.5" height="12" rx="0.75" fill="currentColor" />
        <rect x="12.5" y="6" width="2.5" height="12" rx="1" fill="currentColor" />
        <rect x="17" y="6" width="1.5" height="7" rx="0.75" fill="currentColor" />
        <circle cx="17.75" cy="16.5" r="1.75" className="fill-brand-border" />
      </svg>
    </span>
  )
}
