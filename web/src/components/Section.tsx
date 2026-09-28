import type { ReactNode } from "react"

export function Section({
  id, title, aside, children,
}: { id: string; title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-16 lg:scroll-mt-6">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="text-xl text-ink">{title}</h2>
        {aside && <div className="text-sm text-soft">{aside}</div>}
      </div>
      {children}
    </section>
  )
}

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-line bg-paper ${className}`}>{children}</div>
}

export function SkeletonRows({ rows = 4, height = 44 }: { rows?: number; height?: number }) {
  return (
    <div className="divide-y divide-line">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-5" style={{ height }}>
          <div className="h-3 w-40 animate-pulse rounded-sm bg-track" />
          <div className="h-3 flex-1 animate-pulse rounded-sm bg-track/70" />
        </div>
      ))}
    </div>
  )
}
