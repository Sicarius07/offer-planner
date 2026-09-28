import { useState } from "react"

import type { Example, Meta } from "@/api/types"
import { cn } from "@/lib/utils"

/** Short names for the sample briefs. Vague ones are shown verbatim because the vagueness is the point. */
const LABELS: Record<string, string> = {
  ex01: "Senior dog food",
  ex02: "Ocean-plastic activewear",
  ex03: "Adaptogen sparkling drink",
  ex04: "Hand-poured candles",
  ex05: "We help people feel better",
  ex06: "Backcountry ski shells",
  ex07: "Dental practice software",
  ex08: "A new kind of thing for moms",
  ex09: "Refillable cleaning products",
  ex10: "$1,200 Italian handbags",
  ex11: "Protein bars",
  ex12: "New-cat subscription box",
  ex13: "Budget supplements",
  ex14: "Portuguese linen bedding",
  ex15: "idk just try it",
}

export type RunOptions = {
  brief: string
  monthlyBudget: number
  flightDays: number
  model: string
  allowCompetitors: boolean
}

export function BriefForm({
  meta, examples, running, value, onChange, onSubmit, onExample, options, setOptions,
}: {
  meta: Meta | null
  examples: Example[]
  running: boolean
  value: string
  onChange: (v: string) => void
  onSubmit: () => void
  onExample: (e: Example) => void
  options: Omit<RunOptions, "brief">
  setOptions: (o: Omit<RunOptions, "brief">) => void
}) {
  const [showSettings, setShowSettings] = useState(false)
  const max = meta?.max_brief_chars ?? 1000
  const tooLong = value.length > max

  return (
    <div className="rounded-xl border border-line bg-paper p-5 sm:p-6">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (!running && value.trim() && !tooLong) onSubmit()
        }}
      >
        <label htmlFor="brief" className="mb-2 block font-serif text-lg text-ink">
          Describe what you sell
        </label>
        <textarea
          id="brief"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault()
              if (!running && value.trim() && !tooLong) onSubmit()
            }
          }}
          rows={3}
          placeholder="A sentence or two is enough. For example: small-batch hot sauce, mostly bought as gifts, $18 a bottle."
          className="w-full resize-y rounded-md border border-input bg-paper px-3.5 py-3 text-base leading-relaxed text-ink outline-none placeholder:text-soft/80 focus-visible:border-emerald focus-visible:ring-3 focus-visible:ring-emerald/15"
        />
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-3">
          <button
            type="submit"
            disabled={running || !value.trim() || tooLong}
            className="h-9 rounded-md bg-emerald px-4 text-sm font-medium text-paper transition-colors hover:bg-[#0c6646] focus-visible:ring-3 focus-visible:ring-emerald/30 focus-visible:outline-none disabled:opacity-45"
          >
            {running ? "Drafting…" : "Draft campaign"}
          </button>
          <span className="text-sm text-soft">
            {options.monthlyBudget.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 })} a month
            for {options.flightDays} days
            {options.allowCompetitors ? ", competing publishers allowed" : ""}
          </span>
          <button
            type="button"
            onClick={() => setShowSettings((s) => !s)}
            aria-expanded={showSettings}
            className="text-sm text-ink underline decoration-line underline-offset-4 hover:decoration-ink"
          >
            {showSettings ? "Hide settings" : "Change settings"}
          </button>
          {value.length > max * 0.8 && (
            <span className={cn("ml-auto text-2xs", tooLong ? "text-rust" : "text-soft")}>
              {value.length} / {max}
            </span>
          )}
        </div>

        {showSettings && (
          <div className="mt-4 grid gap-4 border-t border-line pt-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Monthly budget (USD)">
              <input
                type="number" min={500} step={500} value={options.monthlyBudget}
                onChange={(e) => setOptions({ ...options, monthlyBudget: Number(e.target.value) || 0 })}
                className="h-9 w-full rounded-md border border-input bg-paper px-3 text-sm outline-none focus-visible:border-emerald"
              />
            </Field>
            <Field label="Flight (days)">
              <input
                type="number" min={7} max={90} value={options.flightDays}
                onChange={(e) => setOptions({ ...options, flightDays: Number(e.target.value) || 30 })}
                className="h-9 w-full rounded-md border border-input bg-paper px-3 text-sm outline-none focus-visible:border-emerald"
              />
            </Field>
            <Field label="Model">
              <select
                value={options.model}
                onChange={(e) => setOptions({ ...options, model: e.target.value })}
                className="h-9 w-full rounded-md border border-input bg-paper px-2.5 text-sm outline-none focus-visible:border-emerald"
              >
                {meta?.models.map((m) => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))}
              </select>
            </Field>
            <label className="flex items-start gap-2.5 pt-6 text-sm text-ink">
              <input
                type="checkbox" checked={options.allowCompetitors}
                onChange={(e) => setOptions({ ...options, allowCompetitors: e.target.checked })}
                className="mt-0.5 size-4 accent-emerald"
              />
              <span>
                Allow competing publishers
                <span className="block text-2xs text-soft">Flag publishers that sell what you sell instead of excluding them.</span>
              </span>
            </label>
          </div>
        )}
      </form>

      {examples.length > 0 && (
        <div className="mt-5 border-t border-line pt-4">
          <p className="mb-2.5 text-sm text-soft">Or try one of the sample briefs:</p>
          <div className="flex flex-wrap gap-1.5">
            {examples.map((ex) => (
              <button
                key={ex.id}
                type="button"
                disabled={running}
                onClick={() => onExample(ex)}
                title={ex.brief}
                className="rounded-full border border-line bg-bg px-3 py-1 text-xs text-ink transition-colors hover:border-soft/50 hover:bg-track disabled:opacity-50"
              >
                {LABELS[ex.id] ?? ex.brief.slice(0, 32)}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-2xs text-soft">{label}</span>
      {children}
    </label>
  )
}
