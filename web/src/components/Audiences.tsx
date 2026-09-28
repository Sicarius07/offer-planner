import { useState } from "react"

import type { CatalogPersona, CatalogPublisher, Creative, PersonaPick, PersonaPlan } from "@/api/types"
import { humanize } from "@/lib/format"
import { cn } from "@/lib/utils"

/**
 * A believable mock of where the ad runs: an offer tile on someone else's
 * order-confirmation page. Deliberately plain; it imitates a real page, not our UI.
 */
function OfferCard({ c, brand, host }: { c: Creative; brand: string | null; host: string | null }) {
  return (
    <div className="overflow-hidden rounded-lg border border-[#e3e3e3] bg-white font-sans text-[#111] shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
      <div className="flex items-center justify-between border-b border-[#efefef] px-4 py-2 text-[11px] text-[#777]">
        <span>{host ? `${host}: order confirmed` : "Order confirmed"}</span>
        <span>Thanks for shopping</span>
      </div>
      <div className="px-4 pt-3.5 pb-4">
        <p className="mb-1 text-[11px] text-[#777]">An offer from {brand ?? "a brand you might like"}</p>
        <p className="text-[17px] leading-snug font-semibold">{c.headline}</p>
        <p className="mt-1.5 text-[13.5px] leading-relaxed text-[#333]">{c.body}</p>
        <span className="mt-3.5 block rounded-md bg-[#111] py-2 text-center text-[13px] font-medium text-white">
          {c.cta}
        </span>
      </div>
    </div>
  )
}

function ReviewLine({ c, settled }: { c: Creative; settled: boolean }) {
  const [open, setOpen] = useState(false)
  if (c.status === "draft" && !c.critique)
    return settled
      ? <p className="text-xs text-rust">Not reviewed, so not launched</p>
      : <p className="text-xs text-soft">Reviewing against the brief…</p>
  const checks = c.critique?.checks ?? []
  const passed = checks.filter((x) => x.passed).length
  const label =
    c.status === "passed" ? `Passed review, ${passed} of ${checks.length} checks`
      : c.status === "revised" ? "Rewritten after review"
        : c.status === "flagged" ? "Failed review twice; paused in the campaign"
          : "Unreviewed"
  return (
    <div className="text-xs">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className={cn(
          "underline decoration-dotted underline-offset-4",
          c.status === "flagged" ? "text-rust" : c.status === "revised" ? "text-amber" : "text-emerald",
        )}
      >
        {label}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {c.revision_of && (
            <div className="rounded-md bg-track/50 px-3 py-2 text-ink/80">
              <p className="mb-1 text-soft">First draft, rejected:</p>
              <p className="line-through decoration-rust/60">{c.revision_of.headline}. {c.revision_of.body}</p>
              {c.critique?.fix && <p className="mt-1.5 text-ink">Fix requested: {c.critique.fix}</p>}
            </div>
          )}
          <ul className="space-y-1">
            {checks.map((x) => (
              <li key={x.name} className="grid grid-cols-[1rem_7rem_1fr] gap-1">
                <span className={x.passed ? "text-emerald" : "text-rust"}>{x.passed ? "✓" : "✕"}</span>
                <span className="text-soft">{humanize(x.name)}</span>
                <span className="text-ink/80">{x.reason}</span>
              </li>
            ))}
            {c.critique?.code_issues.map((i) => (
              <li key={i} className="grid grid-cols-[1rem_7rem_1fr] gap-1">
                <span className="text-rust">✕</span><span className="text-soft">format</span><span>{i}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function PersonaBlock({ pick, c, persona, pubs, brand, index, settled, of }: {
  pick: PersonaPick
  c?: Creative
  persona?: CatalogPersona
  pubs: Map<string, CatalogPublisher>
  brand: string | null
  index: number
  settled: boolean
  /** How many personas were scored, for "ranked 8th of 10". */
  of: number
}) {
  const via = pick.reached_via.map((id) => pubs.get(id)?.publisher.name).filter(Boolean) as string[]
  return (
    <article className={cn("grid gap-6 px-5 py-6 sm:px-6 md:grid-cols-[1fr_minmax(0,21rem)]", index > 0 && "border-t border-line")}>
      <div>
        <div className="flex items-baseline gap-3">
          <h3 className="text-lg text-ink">{pick.name}</h3>
          <span className="text-xs text-soft">
            {pick.confidence} confidence{persona ? `, ${persona.persona.age_range}` : ""}
          </span>
          {pick.rank > 5 && (
            <span className="text-xs text-amber" title="The computed score ranked this persona low; the reasoning below says what it missed.">
              picked over the computed ranking (#{pick.rank} of {of})
            </span>
          )}
        </div>
        <p className="mt-2 max-w-prose text-sm leading-relaxed text-ink">{pick.why_plausible}</p>
        <dl className="mt-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-soft">Lean into</dt>
            <dd className="text-ink">{pick.lean_into.join(", ") || "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-soft">Avoid</dt>
            <dd className="text-ink">{pick.avoid.join(", ") || "—"}</dd>
          </div>
          {via.length > 0 && (
            <div>
              <dt className="text-xs text-soft">Reached through</dt>
              <dd className="text-ink">{via.join(", ")}</dd>
            </div>
          )}
          {pick.conflicts.length > 0 && (
            <div>
              <dt className="text-xs text-soft">Watch out</dt>
              <dd className="text-amber">dislikes {pick.conflicts.map(humanize).join(", ")}</dd>
            </div>
          )}
        </dl>
        {c && (
          <div className="mt-5 space-y-1.5 border-t border-line pt-4 text-sm">
            <p><span className="text-soft">Angle: </span>{c.angle}</p>
            {c.claims_used.length > 0 && (
              <p className="flex flex-wrap items-center gap-1.5">
                <span className="text-soft">Claims used:</span>
                {c.claims_used.map((x, i) => (
                  <span key={i} title={`From the brief: “${x.source_quote}”`} className="rounded-full bg-emerald-wash px-2 py-px text-xs text-emerald">
                    {x.claim}
                  </span>
                ))}
              </p>
            )}
            {c.offer_suggestion && (
              <p><span className="text-soft">Incentive to consider: </span>{c.offer_suggestion} <span className="text-xs text-soft">(your call; not in the copy)</span></p>
            )}
          </div>
        )}
      </div>
      <div className="space-y-2.5">
        {c ? (
          <>
            <OfferCard c={c} brand={brand} host={via[0] ?? null} />
            <ReviewLine c={c} settled={settled} />
          </>
        ) : settled ? (
          <p className="text-sm text-rust">Couldn’t write this ad.</p>
        ) : (
          <div className="h-44 animate-pulse rounded-lg border border-line bg-track/40" />
        )}
      </div>
    </article>
  )
}

export function Audiences({ plan, creatives, personas, pubs, brand, settled }: {
  plan: PersonaPlan
  creatives: Record<string, Creative>
  personas: Map<string, CatalogPersona>
  pubs: Map<string, CatalogPublisher>
  brand: string | null
  /** The creative stage has finished, so a missing or unreviewed ad won't arrive. */
  settled: boolean
}) {
  return (
    <div className="rounded-xl border border-line bg-paper">
      {plan.skipped_note && <p className="border-b border-line px-6 py-3 text-sm text-amber">{plan.skipped_note}</p>}
      {plan.picks.map((p, i) => (
        <PersonaBlock key={p.persona_id} index={i} pick={p} c={creatives[p.persona_id]} persona={personas.get(p.persona_id)} pubs={pubs} brand={brand} settled={settled} of={plan.candidates.length} />
      ))}
    </div>
  )
}
