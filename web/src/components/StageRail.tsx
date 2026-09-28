import { STAGES, type PlanState } from "@/state/plan"
import { seconds } from "@/lib/format"
import { cn } from "@/lib/utils"

function Dot({ status }: { status: string }) {
  if (status === "done")
    return (
      <svg viewBox="0 0 16 16" className="size-4 text-emerald" aria-hidden>
        <circle cx="8" cy="8" r="7.25" fill="currentColor" />
        <path d="M5 8.2l2 2 4-4.4" stroke="#fffdf9" strokeWidth="1.6" fill="none" strokeLinecap="round" />
      </svg>
    )
  if (status === "started")
    return (
      <svg viewBox="0 0 16 16" className="size-4 animate-spin text-emerald" aria-hidden>
        <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeOpacity=".2" strokeWidth="1.5" fill="none" />
        <path d="M8 1.5a6.5 6.5 0 0 1 6.5 6.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />
      </svg>
    )
  if (status === "failed")
    return <span className="grid size-4 place-items-center rounded-full bg-rust text-[10px] font-bold text-paper">!</span>
  return <span className={`block size-4 rounded-full border ${status === "skipped" ? "border-dashed border-soft/50" : "border-line bg-paper"}`} />
}

/** Sticky progress rail. Numbered because these really are sequential stages. */
export function StageRail({ plan }: { plan: PlanState }) {
  return (
    <nav aria-label="Plan sections" className="sticky top-6 hidden lg:block">
      <ol className="space-y-1">
        {STAGES.map((s, i) => {
          const st = plan.stages[s.key]
          return (
            <li key={s.key}>
              <a
                href={`#${s.key}`}
                className="group flex items-center gap-3 rounded-md px-2 py-2 text-sm hover:bg-track/60"
              >
                <Dot status={st.status} />
                <span className="w-4 text-soft">{i + 1}</span>
                <span className={cn("whitespace-nowrap", st.status === "skipped" ? "text-soft line-through decoration-soft/40" : "text-ink")}>
                  {s.label}
                </span>
                {st.ms != null && st.status === "done" && (
                  <span className="ml-auto text-2xs text-soft opacity-0 group-hover:opacity-100">{seconds(st.ms)}</span>
                )}
              </a>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

/** On narrow screens the rail collapses into a row of dots. */
export function StageDots({ plan }: { plan: PlanState }) {
  return (
    <div className="sticky top-0 z-10 -mx-4 mb-4 flex items-center gap-4 border-b border-line bg-bg/95 px-4 py-2 backdrop-blur lg:hidden">
      {STAGES.map((s) => (
        <a key={s.key} href={`#${s.key}`} className="flex items-center gap-1.5 text-2xs text-soft">
          <Dot status={plan.stages[s.key].status} />
          <span className="hidden sm:inline">{s.label}</span>
        </a>
      ))}
    </div>
  )
}
