import type { PlanState } from "@/state/plan"
import { seconds } from "@/lib/format"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"

/** Per-call timeline: model, prompt version, tokens, cost, latency. How you'd debug a bad run. */
export function RunDrawer({ plan, open, onOpenChange }: {
  plan: PlanState
  open: boolean
  onOpenChange: (o: boolean) => void
}) {
  const run = plan.run
  const max = Math.max(1, ...(run?.trace.map((t) => t.ms) ?? [1]))
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 border-line bg-paper sm:max-w-xl">
        <SheetHeader className="border-b border-line px-6 py-5">
          <SheetTitle className="font-serif text-xl font-medium text-ink">Run details</SheetTitle>
          <SheetDescription className="text-sm text-soft">
            {run
              ? `${plan.source === "cached" ? "Cached run" : "Live run"} ${run.id}: ${seconds(run.totalMs)}, $${run.costUsd.toFixed(3)} in model calls, ${run.trace.filter((t) => t.model).length} model calls.`
              : "Details appear when the run finishes."}
          </SheetDescription>
        </SheetHeader>
        <div className="overflow-auto px-6 py-4">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-2xs tracking-[0.06em] text-soft uppercase">
                <th className="py-2 text-left font-medium">Step</th>
                <th className="py-2 text-left font-medium">Time</th>
                <th className="py-2 text-right font-medium">Tokens</th>
                <th className="py-2 text-right font-medium">Cost</th>
              </tr>
            </thead>
            <tbody>
              {run?.trace.map((t, i) => (
                <tr key={i} className="border-t border-line align-top">
                  <td className="py-2 pr-3">
                    <span className={t.ok ? "text-ink" : "text-rust"}>{t.name}</span>
                    {t.model && (
                      <span className="block font-mono text-[11px] text-soft">
                        {t.model.split(":")[1]}, {t.prompt_version}{t.retries ? `, ${t.retries} retry` : ""}
                      </span>
                    )}
                    {t.error && <span className="block text-rust">{t.error.slice(0, 160)}</span>}
                  </td>
                  <td className="w-32 py-2 pr-3">
                    <span className="mb-1 block h-1.5 rounded-full bg-track">
                      <span className="block h-full rounded-full bg-emerald/70" style={{ width: `${(100 * t.ms) / max}%` }} />
                    </span>
                    <span className="text-soft">{seconds(t.ms)}</span>
                  </td>
                  <td className="py-2 text-right text-soft">
                    {t.input_tokens ? `${t.input_tokens.toLocaleString()} / ${t.output_tokens.toLocaleString()}` : "—"}
                  </td>
                  <td className="py-2 text-right">{t.cost_usd ? `$${t.cost_usd.toFixed(4)}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-4 text-xs text-soft">
            Tokens are input / output. Prompt versions change whenever a file in prompts/ changes, so traces and evals can be
            tied to the exact prompt text.
          </p>
        </div>
      </SheetContent>
    </Sheet>
  )
}
