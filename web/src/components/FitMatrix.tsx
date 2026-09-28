import { Fragment, useState } from "react"

import type { CatalogPublisher, PublisherPlan, PublisherResult, Signal } from "@/api/types"
import { categoryColor, heat } from "@/lib/colors"
import { compact, humanize, money } from "@/lib/format"
import { cn } from "@/lib/utils"

const COLS: { key: Signal["name"]; label: string }[] = [
  { key: "category", label: "Category" },
  { key: "audience", label: "Audience" },
  { key: "price", label: "Price" },
  { key: "values", label: "Values" },
  { key: "reach", label: "Reach" },
]

const WEIGHTS: Record<string, number> = { category: 40, audience: 20, price: 15, values: 15, reach: 10 }

const REASON: Record<string, string> = {
  competitor: "Competitor",
  off_category: "Off-category",
  weak_fit: "Weak fit",
  review: "Excluded on review",
}

const RANK: Record<string, number> = { excluded: 0, test: 1, recommended: 2 }

function HeatCell({ s, dim }: { s: Signal; dim?: boolean }) {
  if (s.neutral)
    return (
      <span title={s.detail} className="heat grid h-7 w-full place-items-center rounded-sm bg-track/60 text-xs text-soft">
        —
      </span>
    )
  return (
    <span
      title={s.detail}
      className={cn("heat grid h-7 w-full place-items-center rounded-sm text-xs text-ink", dim && "opacity-55")}
      style={{ background: heat(s.score) }}
    >
      {s.score}
    </span>
  )
}

/** The review moved this publisher out of the tier its computed fit put it in. */
function Moved({ r }: { r: PublisherResult }) {
  if (!r.tier_reason || r.tier === r.computed_tier) return null
  const up = RANK[r.tier] > RANK[r.computed_tier]
  return (
    <span
      title={`Computed fit ${r.base_fit} put this in ${humanize(r.computed_tier).toLowerCase()}. ${r.tier_reason}`}
      className={cn(
        "rounded-full px-1.5 py-px text-2xs",
        up ? "bg-emerald-wash text-emerald" : "bg-rust-wash text-rust",
      )}
    >
      {up ? "Moved up" : "Moved down"}
    </span>
  )
}

function Row({ r, pub, open, onToggle, excluded }: {
  r: PublisherResult
  pub?: CatalogPublisher
  open: boolean
  onToggle: () => void
  excluded?: boolean
}) {
  const by = Object.fromEntries(r.signals.map((s) => [s.name, s]))
  return (
    <Fragment>
      <tr
        onClick={onToggle}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onToggle())}
        tabIndex={0}
        aria-expanded={open}
        className={cn(
          "cursor-pointer border-t border-line outline-none hover:bg-bg/70 focus-visible:bg-bg",
          excluded && "shadow-[inset_3px_0_0_var(--color-rust)]",
          open && "bg-bg/70",
        )}
      >
        <td className="py-2 pr-3 pl-5">
          <div className="flex items-center gap-2.5">
            <span className="size-2 shrink-0 rounded-full" style={{ background: categoryColor(r.category) }} />
            <span className="font-medium text-ink">{r.name}</span>
            {r.exclusion_reason && (
              <span className={cn("text-2xs", r.exclusion_reason === "competitor" ? "text-rust" : "text-soft")}>
                {REASON[r.exclusion_reason]}
              </span>
            )}
            {!r.exclusion_reason && r.adjacent_conflict && <span className="text-2xs text-amber">Overlaps</span>}
            {r.competitor_dispute && <span className="text-2xs text-amber">Disputed</span>}
          </div>
          <div className="pl-4.5 text-2xs text-soft">{humanize(r.category)}</div>
        </td>
        {COLS.map((c) => (
          <td key={c.key} className="hidden px-1 py-2 sm:table-cell">
            <HeatCell s={by[c.key]} dim={excluded} />
          </td>
        ))}
        <td className="py-2 pr-5 pl-3 text-right">
          <span className="inline-flex items-center gap-1.5">
            <Moved r={r} />
            <span className={cn("w-7 text-base font-medium", excluded ? "text-soft" : "text-ink")}>{r.fit}</span>
          </span>
        </td>
      </tr>
      {open && (
        <tr className="bg-bg/70">
          <td colSpan={7} className="px-5 pt-1 pb-5 sm:pl-10">
            <Detail r={r} pub={pub} />
          </td>
        </tr>
      )}
    </Fragment>
  )
}

function Detail({ r, pub }: { r: PublisherResult; pub?: CatalogPublisher }) {
  return (
    <div className="grid gap-6 text-sm md:grid-cols-[1.3fr_1fr]">
      <div className="space-y-3">
        <p className="max-w-prose leading-relaxed text-ink">{r.rationale}</p>
        {r.conflict && <p className="text-rust">Excluded: {r.conflict}. Offers only run on non-competing brands.</p>}
        {r.competitor_dispute && (
          <p className="text-amber">The review doesn’t think this is a competitor: {r.competitor_dispute} It stays excluded until you decide.</p>
        )}
        {r.adjacent_conflict && r.tier === "test" && !r.tier_reason && <p className="text-amber">Held to a test budget: {r.adjacent_conflict}.</p>}
        {r.tier_reason && r.tier !== r.computed_tier && (
          <p className="text-soft">
            <span className="text-ink">
              Moved from {humanize(r.computed_tier).toLowerCase()} to {humanize(r.tier).toLowerCase()} on review
              {r.fit !== r.base_fit ? ` (computed fit ${r.base_fit})` : ""}:
            </span>{" "}
            {r.tier_reason}
          </p>
        )}
        {r.risk && <p className="text-soft"><span className="text-ink">Risk:</span> {r.risk}</p>}
        {r.evidence.length > 0 && (
          <ul className="flex flex-wrap gap-1.5 pt-1">
            {r.evidence.map((e, i) => (
              <li key={i} className="rounded-full border border-line bg-paper px-2.5 py-0.5 text-xs text-ink">
                <span className="text-soft">{e.field === "brief" ? "your brief" : humanize(e.field)}: </span>“{e.quote}”
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <dl className="space-y-1.5 text-xs">
          {r.signals.map((s) => (
            <div key={s.name} className="grid grid-cols-[5.5rem_2rem_1fr] items-baseline gap-2">
              <dt className="text-soft">{humanize(s.name)} <span className="text-soft/70">{WEIGHTS[s.name]}%</span></dt>
              <span className="text-right text-ink">{s.neutral ? "—" : s.score}</span>
              <dd className="text-ink/80">{s.detail}</dd>
            </div>
          ))}
        </dl>
        {pub && (
          <p className="mt-3 border-t border-line pt-3 text-xs text-soft">
            {compact(pub.publisher.monthly_impressions)} impressions a month, {money(pub.publisher.avg_order_value_usd)} typical order,
            ages {pub.publisher.audience.age_skew}, {pub.publisher.audience.income_tier} income. “{pub.publisher.notes}”
          </p>
        )}
      </div>
    </div>
  )
}

function GroupHeader({ label, count, note, open, onToggle }: {
  label: string
  count: number
  note?: string
  open?: boolean
  onToggle?: () => void
}) {
  return (
    <tr className="border-t border-line">
      <td colSpan={7} className="px-5 pt-4 pb-1.5">
        {onToggle ? (
          <button type="button" onClick={onToggle} aria-expanded={open} className="flex items-center gap-2 text-sm text-ink hover:underline">
            <span className={cn("inline-block text-soft transition-transform", open && "rotate-90")}>›</span>
            {label} <span className="text-soft">{count}</span>
          </button>
        ) : (
          <span className="text-sm text-ink">
            {label} <span className="text-soft">{count}</span>
          </span>
        )}
        {note && <span className="ml-3 text-xs text-soft">{note}</span>}
      </td>
    </tr>
  )
}

export function FitMatrix({ plan, catalog }: { plan: PublisherPlan; catalog: Map<string, CatalogPublisher> }) {
  const [open, setOpen] = useState<string | null>(plan.recommended[0]?.publisher_id ?? null)
  const [showExcluded, setShowExcluded] = useState(false)
  const toggle = (id: string) => setOpen((o) => (o === id ? null : id))
  const competitors = plan.excluded.filter((r) => r.exclusion_reason === "competitor")
  const noFit = plan.recommended.length === 0 && plan.test.length === 0

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-paper">
      <p className="px-5 pt-5 pb-4 text-sm leading-relaxed text-ink sm:max-w-[75ch]">{plan.summary}</p>
      {plan.offering_type_doubt && (
        <p className="mx-5 mb-4 rounded-md bg-amber-wash/60 px-3 py-2 text-sm text-amber">
          The review questions whether this is a business or consumer product: {plan.offering_type_doubt}
        </p>
      )}
      {noFit && (
        <p className="mx-5 mb-4 rounded-md bg-rust-wash/60 px-3 py-2 text-sm text-rust">
          None of the {plan.excluded.length} publishers are a real fit. This network is consumer checkout traffic;
          the closest options are listed below for reference.
        </p>
      )}
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="text-2xs tracking-[0.06em] text-soft uppercase">
            <th className="py-2 pl-5 text-left font-medium">Publisher</th>
            {COLS.map((c) => (
              <th key={c.key} className="hidden w-[11%] px-1 py-2 text-center font-medium sm:table-cell">
                {c.label}
              </th>
            ))}
            <th className="py-2 pr-5 text-right font-medium">Fit</th>
          </tr>
        </thead>
        <tbody>
          {plan.recommended.length > 0 && (
            <>
              <GroupHeader label="Recommended" count={plan.recommended.length} />
              {plan.recommended.map((r) => (
                <Row key={r.publisher_id} r={r} pub={catalog.get(r.publisher_id)} open={open === r.publisher_id} onToggle={() => toggle(r.publisher_id)} />
              ))}
            </>
          )}
          {plan.test.length > 0 && (
            <>
              <GroupHeader label="Test budget" count={plan.test.length} note="Worth a small, measured trial" />
              {plan.test.map((r) => (
                <Row key={r.publisher_id} r={r} pub={catalog.get(r.publisher_id)} open={open === r.publisher_id} onToggle={() => toggle(r.publisher_id)} />
              ))}
            </>
          )}
          <GroupHeader
            label="Excluded"
            count={plan.excluded.length}
            note={competitors.length ? `including ${competitors.map((c) => c.name).join(" and ")} as competitors` : undefined}
            open={showExcluded || noFit}
            onToggle={() => setShowExcluded((s) => !s)}
          />
          {(showExcluded || noFit) &&
            plan.excluded.map((r) => (
              <Row key={r.publisher_id} r={r} pub={catalog.get(r.publisher_id)} excluded open={open === r.publisher_id} onToggle={() => toggle(r.publisher_id)} />
            ))}
        </tbody>
      </table>
      <div className="h-3" />
    </div>
  )
}
