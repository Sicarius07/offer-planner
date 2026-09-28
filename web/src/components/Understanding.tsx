import { useMemo, useState } from "react"

import type { AdvertiserProfile, ClarifyingQuestion, Source, Span } from "@/api/types"
import { ANSWERS_HEADING, type QA } from "@/lib/brief"
import { humanize, money } from "@/lib/format"
import { cn } from "@/lib/utils"

type Fact = {
  key: string
  label: string
  value: string
  source: Source
  evidence: Span | null
  note: string | null
}

function facts(p: AdvertiserProfile): Fact[] {
  const out: Fact[] = []
  const add = (key: string, label: string, a: { value: unknown; source: Source; evidence?: Span | null; note?: string | null } | null | undefined, fmt?: (v: never) => string) => {
    if (!a) return
    const value = fmt ? fmt(a.value as never) : String(a.value)
    out.push({ key, label, value, source: a.source, evidence: a.evidence ?? null, note: a.note ?? null })
  }
  add("product", "What you sell", p.product)
  add("audience", "Customer", p.audience)
  add("price", "Positioning", p.price_tier)
  add("order", "First order", p.first_order_value_usd, (v: number) => money(v))
  add("model", "Business model", p.business_model, (v: string) => humanize(v))
  add("gender", "Gender", p.gender, (v: string) => (v === "any" ? "not specified" : v))
  add("age", "Age", p.age_range)
  p.claims.forEach((c, i) =>
    out.push({ key: `claim${i}`, label: "Claim", value: c.claim, source: "stated", evidence: c.evidence, note: null }),
  )
  return out
}

const SOURCE_LABEL: Record<Source, string> = {
  stated: "you said this",
  inferred: "we inferred this",
  assumed: "we assumed this",
}

/** The brief, re-set large, with every phrase the system relied on underlined by source. */
function AnnotatedBrief({ brief, items, active, setActive, animate }: {
  brief: string
  items: Fact[]
  active: string | null
  setActive: (k: string | null) => void
  animate: boolean
}) {
  const marked = items.filter((f) => f.evidence)
  // Answers to earlier questions are part of the brief text (so they can be quoted), but read
  // as a list under it rather than as more of the headline.
  const answersAt = brief.indexOf(ANSWERS_HEADING)
  const baseEnd = answersAt < 0 ? brief.length : brief.slice(0, answersAt).trimEnd().length
  const segments = useMemo(() => {
    const cuts = new Set([0, brief.length, baseEnd, answersAt < 0 ? brief.length : answersAt])
    marked.forEach((f) => {
      cuts.add(f.evidence!.start)
      cuts.add(f.evidence!.end)
    })
    const sorted = [...cuts].sort((a, b) => a - b)
    return sorted.slice(0, -1).map((start, i) => {
      const end = sorted[i + 1]
      const covering = marked
        .filter((f) => f.evidence!.start <= start && f.evidence!.end >= end)
        .sort((a, b) => a.evidence!.end - a.evidence!.start - (b.evidence!.end - b.evidence!.start))
      return { start, end, covering }
    })
  }, [brief, marked, baseEnd, answersAt])

  const render = ({ start, end, covering }: (typeof segments)[number]) => {
    const text = brief.slice(start, end)
    if (!covering.length) return <span key={start}>{text}</span>
    const inner = covering[0]
    const isActive = covering.some((c) => c.key === active)
    return (
      <span
        key={start}
        tabIndex={0}
        data-source={inner.source}
        data-active={isActive}
        onMouseEnter={() => setActive(inner.key)}
        onMouseLeave={() => setActive(null)}
        onFocus={() => setActive(inner.key)}
        onBlur={() => setActive(null)}
        className={cn("mark group relative outline-none", animate && "mark-draw")}
        style={{ ["--i" as string]: marked.indexOf(inner) }}
      >
        {text}
        <span
          role="tooltip"
          className="pointer-events-none absolute top-full left-0 z-20 mt-2 hidden w-max max-w-72 rounded-md border border-line bg-paper px-3 py-2 font-sans text-xs leading-snug text-ink shadow-[0_6px_24px_-8px_rgba(27,26,23,0.25)] group-hover:block group-focus:block"
        >
          {covering.map((c) => (
            <span key={c.key} className="block py-0.5">
              <span className="text-soft">{c.label}: </span>
              {c.value}
              <span className="text-soft">, {SOURCE_LABEL[c.source]}</span>
            </span>
          ))}
        </span>
      </span>
    )
  }

  return (
    <>
      <p className="font-serif text-[1.625rem] leading-[1.5] whitespace-pre-line text-ink sm:text-2xl sm:leading-[1.45]" style={{ maxWidth: "34em" }}>
        {segments.filter((g) => g.end <= baseEnd).map(render)}
      </p>
      {answersAt >= 0 && (
        <p className="mt-4 font-serif text-lg leading-relaxed whitespace-pre-line text-ink" style={{ maxWidth: "40em" }}>
          {segments.filter((g) => g.start >= answersAt).map(render)}
        </p>
      )}
    </>
  )
}

function SourceSwatch({ source }: { source: Source }) {
  return (
    <span
      aria-hidden
      className="mark ml-1 inline-block w-5 align-middle"
      data-source={source}
      style={{ height: 6, paddingBottom: 0 }}
    />
  )
}

export function Understanding({ profile, animate, answers }: {
  profile: AdvertiserProfile
  animate: boolean
  answers: AnswerHandlers
}) {
  const [active, setActive] = useState<string | null>(null)
  const items = useMemo(() => facts(profile), [profile])
  const dropped = profile.dropped_quotes ?? []

  return (
    <div className="rounded-xl border border-line bg-paper">
      <div className="px-5 pt-6 pb-5 sm:px-8 sm:pt-8">
        <AnnotatedBrief brief={profile.brief} items={items} active={active} setActive={setActive} animate={animate} />
        <p className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-soft">
          <span className="flex items-center gap-2"><SourceSwatch source="stated" /> you said it</span>
          <span className="flex items-center gap-2"><SourceSwatch source="inferred" /> we inferred it</span>
          <span className="flex items-center gap-2"><SourceSwatch source="assumed" /> we assumed it</span>
        </p>
      </div>

      <div className="grid gap-8 border-t border-line px-5 py-6 sm:px-8 md:grid-cols-[1.2fr_1fr]">
        <div>
          <p className="mb-3 text-sm text-ink">{profile.business_summary}</p>
          <dl className="divide-y divide-line/70 text-sm">
            {items.filter((f) => !f.key.startsWith("claim")).map((f) => (
              <div
                key={f.key}
                onMouseEnter={() => setActive(f.key)}
                onMouseLeave={() => setActive(null)}
                className={cn("grid grid-cols-[8.5rem_1fr] gap-3 py-2 transition-colors", active === f.key && "bg-track/40")}
              >
                <dt className="text-soft">{f.label}</dt>
                <dd className={cn(f.source === "assumed" ? "text-amber" : "text-ink")}>
                  <span>
                    {f.value} <SourceSwatch source={f.source} />
                  </span>
                  {f.note && <span className="mt-0.5 block text-xs text-soft">{f.note}</span>}
                </dd>
              </div>
            ))}
          </dl>
          <TagLine profile={profile} />
        </div>

        <div className="space-y-6">
          {profile.claims.length > 0 && (
            <div>
              <h3 className="mb-2 font-sans text-sm font-medium text-ink">Claims the ads may use</h3>
              <ul className="flex flex-wrap gap-1.5">
                {profile.claims.map((c, i) => (
                  <li
                    key={i}
                    onMouseEnter={() => setActive(`claim${i}`)}
                    onMouseLeave={() => setActive(null)}
                    className="rounded-full bg-emerald-wash px-2.5 py-0.5 text-xs text-emerald"
                  >
                    {c.claim}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-soft">Anything not on this list is off limits for the copy.</p>
            </div>
          )}
          {profile.assumptions.length > 0 && (
            <div>
              <h3 className="mb-2 font-sans text-sm font-medium text-ink">What we assumed</h3>
              <ul className="space-y-1.5 text-sm text-amber">
                {profile.assumptions.map((a, i) => (
                  <li key={i} className="border-l-2 border-amber/50 pl-3">{a}</li>
                ))}
              </ul>
            </div>
          )}
          {dropped.length > 0 && (
            <p className="text-xs text-soft">
              {dropped.length} quote{dropped.length > 1 ? "s" : ""} the model gave couldn’t be
              found in your brief, so {dropped.length > 1 ? "they were" : "it was"} treated as an assumption.
            </p>
          )}
          {profile.clarity !== "unusable" && profile.clarifying_questions.length > 0 && (
            <Questions questions={profile.clarifying_questions} handlers={answers} title="Answer to sharpen the plan" />
          )}
        </div>
      </div>
    </div>
  )
}

function TagLine({ profile }: { profile: AdvertiserProfile }) {
  const groups: [string, string[]][] = [
    ["Interests", Object.keys(profile.interests)],
    ["Values", Object.keys(profile.values)],
    ["Occasions", Object.keys(profile.occasions)],
  ]
  const shown = groups.filter(([, t]) => t.length)
  if (!shown.length) return null
  return (
    <div className="mt-4 space-y-1.5 text-xs">
      <p className="text-soft">Matched to our vocabulary, which is what the scoring uses:</p>
      {shown.map(([label, tags]) => (
        <p key={label} className="flex flex-wrap items-center gap-1.5">
          <span className="w-18 text-soft">{label}</span>
          {tags.map((t) => (
            <span key={t} className="rounded-full bg-track px-2 py-0.5 text-ink">{humanize(t)}</span>
          ))}
        </p>
      ))}
    </div>
  )
}

export type AnswerHandlers = {
  /** Called on every selection change, so the brief box can show what will be sent. */
  onChange: (answers: QA[]) => void
  onSubmit: (answers: QA[]) => void
}

/** One answer per question: a suggested one, or the advertiser's own words via "Other". */
export function Questions({ questions, title, handlers, disabled }: {
  questions: ClarifyingQuestion[]
  title: string
  handlers: AnswerHandlers
  disabled?: boolean
}) {
  const [picked, setPicked] = useState<Record<number, string>>({})
  const [custom, setCustom] = useState<Record<number, string>>({})
  const [editing, setEditing] = useState<number | null>(null)

  const toQA = (p: Record<number, string>): QA[] =>
    Object.entries(p).map(([i, answer]) => ({ question: questions[Number(i)].question, answer }))
  const update = (next: Record<number, string>) => {
    setPicked(next)
    handlers.onChange(toQA(next))
  }
  const choose = (i: number, answer: string) => {
    const next = { ...picked }
    if (next[i] === answer) delete next[i]
    else next[i] = answer
    update(next)
  }
  const commitCustom = (i: number) => {
    setEditing(null)
    const text = (custom[i] ?? "").trim()
    const next = { ...picked }
    if (text) next[i] = text
    else if (!questions[i].suggested_answers.includes(next[i] ?? "")) delete next[i]
    update(next)
  }
  const count = Object.keys(picked).length

  const chip = (selected: boolean) => cn(
    "rounded-full border px-3 py-1 text-xs transition-colors",
    selected ? "border-emerald bg-emerald-wash text-emerald" : "border-line bg-bg text-ink hover:border-emerald/40 hover:bg-emerald-wash/60",
  )

  return (
    <div>
      <h3 className="mb-2 font-sans text-sm font-medium text-ink">{title}</h3>
      <ul className="space-y-4">
        {questions.map((q, i) => {
          const own = picked[i] !== undefined && !q.suggested_answers.includes(picked[i])
          return (
            <li key={i}>
              <p className="text-sm text-ink">{q.question}</p>
              <p className="mb-2 text-xs text-soft">{q.why}</p>
              <div role="radiogroup" aria-label={q.question} className="flex flex-wrap items-center gap-1.5">
                {q.suggested_answers.map((a) => (
                  <button key={a} type="button" role="radio" aria-checked={picked[i] === a}
                    onClick={() => choose(i, a)} className={chip(picked[i] === a)}>
                    {a}
                  </button>
                ))}
                {editing === i ? (
                  <input
                    autoFocus
                    aria-label={`Your answer: ${q.question}`}
                    value={custom[i] ?? ""}
                    placeholder="Type your answer"
                    maxLength={80}
                    onChange={(e) => setCustom({ ...custom, [i]: e.target.value })}
                    onBlur={() => commitCustom(i)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitCustom(i)
                      if (e.key === "Escape") setEditing(null)
                    }}
                    className="h-[1.625rem] w-48 rounded-full border border-emerald/50 bg-paper px-3 text-xs text-ink outline-none focus-visible:ring-2 focus-visible:ring-emerald/30"
                  />
                ) : (
                  <button type="button" role="radio" aria-checked={own}
                    onClick={() => setEditing(i)} className={chip(own)}>
                    {own ? picked[i] : "Other…"}
                  </button>
                )}
              </div>
            </li>
          )
        })}
      </ul>
      <div className="mt-5 flex items-center gap-3">
        <button
          type="button"
          disabled={!count || disabled}
          onClick={() => handlers.onSubmit(toQA(picked))}
          className="h-8 rounded-md bg-ink px-3 text-sm text-paper hover:bg-ink/85 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {count ? `Redraft with ${count} answer${count > 1 ? "s" : ""}` : "Redraft"}
        </button>
        {!count && <span className="text-xs text-soft">Answer any of these; skip the rest.</span>}
      </div>
    </div>
  )
}

export function NeedsInput({ reason, questions, handlers, onForce }: {
  reason: string
  questions: ClarifyingQuestion[]
  handlers: AnswerHandlers
  onForce: () => void
}) {
  return (
    <div className="rounded-xl border border-amber/40 bg-amber-wash/40 px-5 py-6 sm:px-8">
      <h3 className="font-serif text-lg text-ink">We need a little more before drafting a campaign</h3>
      <p className="mt-1 mb-5 max-w-prose text-sm text-ink/80">{reason}</p>
      <Questions questions={questions} handlers={handlers} title="Answer what you can, then redraft" />
      <div className="mt-6 flex items-center gap-4 border-t border-amber/25 pt-4">
        <button
          type="button"
          onClick={onForce}
          className="h-8 rounded-md border border-ink/20 bg-paper px-3 text-sm text-ink hover:bg-track"
        >
          Draft anyway with broad assumptions
        </button>
        <span className="text-xs text-soft">Expect a generic plan that needs review.</span>
      </div>
    </div>
  )
}
