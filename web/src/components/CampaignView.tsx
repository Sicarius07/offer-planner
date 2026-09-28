import { useState } from "react"

import type { CampaignConfig } from "@/api/types"
import { categoryColor } from "@/lib/colors"
import { humanize, money, shortDate } from "@/lib/format"
import { cn } from "@/lib/utils"

function AllocationBar({ cfg }: { cfg: CampaignConfig }) {
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full bg-track">
        {cfg.placements.map((p) => (
          <span
            key={p.publisher_id}
            title={`${p.publisher_name}: ${p.allocation_pct}%`}
            className={cn("h-full border-r-2 border-paper last:border-r-0", p.role === "test" && "opacity-60")}
            style={{ width: `${p.allocation_pct}%`, background: categoryColor(p.category) }}
          />
        ))}
      </div>
    </div>
  )
}

function Summary({ cfg }: { cfg: CampaignConfig }) {
  const b = cfg.bid_strategy
  const est = cfg.placements.reduce((n, p) => n + p.est_conversions, 0)
  if (!cfg.placements.length)
    return (
      <div className="space-y-5">
        <p className="max-w-[68ch] text-base leading-relaxed text-ink">
          Nothing to launch: no publisher in this network reaches your buyers, so the config has no placements. It’s still
          generated so the targeting, bid logic and assumptions can be reviewed.
        </p>
        <ReviewBox cfg={cfg} />
      </div>
    )
  return (
    <div className="space-y-7">
      <p className="max-w-[68ch] text-base leading-relaxed text-ink">
        Spend <strong className="font-medium">{money(cfg.budget.total_usd)}</strong> from {shortDate(cfg.campaign.flight.start)} to{" "}
        {shortDate(cfg.campaign.flight.end)}, about {money(cfg.budget.daily_cap_usd)} a day, bidding for purchases at a target cost of{" "}
        <strong className="font-medium">{money(b.target_cpa_usd, 2)}</strong> each (never above {money(b.max_cpa_usd, 2)}).
        At target, that’s roughly <strong className="font-medium">{Math.round(est).toLocaleString()} new customers</strong>.
      </p>
      <p className="-mt-4 max-w-[68ch] text-sm text-soft">{b.rationale}</p>

      {cfg.placements.length > 0 && (
        <div>
          <AllocationBar cfg={cfg} />
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="text-2xs tracking-[0.06em] text-soft uppercase">
                <th className="py-2 text-left font-medium">Publisher</th>
                <th className="py-2 text-left font-medium">Role</th>
                <th className="py-2 text-right font-medium">Share</th>
                <th className="py-2 text-right font-medium">Budget</th>
                <th className="py-2 text-right font-medium">Est. customers</th>
              </tr>
            </thead>
            <tbody>
              {cfg.placements.map((p) => (
                <tr key={p.publisher_id} className="border-t border-line align-top">
                  <td className="py-2">
                    <span className="flex items-center gap-2">
                      <span className="size-2 rounded-full" style={{ background: categoryColor(p.category) }} />
                      {p.publisher_name}
                    </span>
                    {p.capacity_note && <span className="mt-0.5 block pl-4 text-xs text-amber">{p.capacity_note}</span>}
                  </td>
                  <td className="py-2 text-soft">{p.role === "core" ? "Core" : "Test"}</td>
                  <td className="py-2 text-right">{p.allocation_pct}%</td>
                  <td className="py-2 text-right">{money(p.budget_usd)}</td>
                  <td className="py-2 text-right">{Math.round(p.est_conversions)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <dl className="grid gap-x-10 gap-y-5 text-sm sm:grid-cols-2">
        <Item label="Who">
          {cfg.targeting.personas.length} persona{cfg.targeting.personas.length === 1 ? "" : "s"}
          {cfg.targeting.gender && `, ${cfg.targeting.gender.value}`}
          {cfg.targeting.age_range && `, ages ${cfg.targeting.age_range.value}`}; {cfg.targeting.geo.join(", ")}
        </Item>
        <Item label="Never next to">
          {cfg.targeting.exclusions.length ? cfg.targeting.exclusions.map(humanize).join(", ") : "no exclusions"}
        </Item>
        <Item label="Frequency">
          {cfg.frequency_cap.impressions} per shopper every {cfg.frequency_cap.per_days} days. {cfg.frequency_cap.rationale}
        </Item>
        <Item label="Measurement">
          Purchases within {cfg.measurement.attribution_window_days} days of seeing the offer, with a {cfg.measurement.holdout_pct}% holdout to
          measure true lift.
        </Item>
        <Item label="Testing">
          {cfg.experiment.graduate_rule} {cfg.experiment.notes}
        </Item>
        <Item label="Ads">
          {cfg.creatives.filter((c) => c.weight > 0).length} in even rotation
          {cfg.creatives.some((c) => c.weight === 0) && `, ${cfg.creatives.filter((c) => c.weight === 0).length} paused`}
        </Item>
      </dl>

      <ReviewBox cfg={cfg} />
    </div>
  )
}

function ReviewBox({ cfg }: { cfg: CampaignConfig }) {
  return (
      <div
        className={cn(
          "rounded-lg border px-4 py-3.5 text-sm",
          cfg.review.needs_human_review ? "border-amber/40 bg-amber-wash/40" : "border-line bg-bg/60",
        )}
      >
        <p className="font-medium text-ink">
          {cfg.review.needs_human_review ? "Review before launch" : "Ready for review"}
          <span className="ml-2 font-normal text-soft">{cfg.review.confidence} confidence</span>
        </p>
        {cfg.review.warnings.length > 0 && (
          <ul className="mt-2 space-y-1 text-amber">
            {cfg.review.warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        )}
        {cfg.review.assumptions.length > 0 && (
          <ul className="mt-2 space-y-1 text-soft">
            {cfg.review.assumptions.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        )}
      </div>
  )
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="mb-0.5 text-xs text-soft">{label}</dt>
      <dd className="leading-relaxed text-ink">{children}</dd>
    </div>
  )
}

/** Minimal JSON highlighting: keys, strings, numbers. */
function highlight(json: string) {
  return json.split("\n").map((line, i) => {
    const parts = line.split(/("(?:[^"\\]|\\.)*"(?:\s*:)?|-?\d+\.?\d*|true|false|null)/g)
    return (
      <div key={i}>
        {parts.map((p, j) => {
          if (/^".*":$/.test(p.replace(/\s/g, ""))) return <span key={j} className="text-[#4a6fa5]">{p}</span>
          if (p.startsWith('"')) return <span key={j} className="text-emerald">{p}</span>
          if (/^-?\d/.test(p) || p === "true" || p === "false" || p === "null") return <span key={j} className="text-[#a4506a]">{p}</span>
          return <span key={j}>{p}</span>
        })}
      </div>
    )
  })
}

export function CampaignView({ cfg }: { cfg: CampaignConfig }) {
  const [tab, setTab] = useState<"summary" | "json">("summary")
  const [copied, setCopied] = useState(false)
  const json = JSON.stringify(cfg, null, 2)

  const download = () => {
    const url = URL.createObjectURL(new Blob([json], { type: "application/json" }))
    const a = document.createElement("a")
    a.href = url
    a.download = "campaign.json"
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="rounded-xl border border-line bg-paper">
      <div className="flex items-center justify-between border-b border-line px-5 sm:px-6">
        <div role="tablist" className="flex gap-5">
          {(["summary", "json"] as const).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={cn(
                "-mb-px border-b-2 py-3 font-serif text-base",
                tab === t ? "border-ink text-ink" : "border-transparent text-soft hover:text-ink",
              )}
            >
              {t === "summary" ? "Summary" : "Config"}
            </button>
          ))}
        </div>
        <div className="flex gap-3 text-sm">
          <button
            type="button"
            onClick={() => navigator.clipboard.writeText(json).then(() => (setCopied(true), setTimeout(() => setCopied(false), 1500)))}
            className="text-ink underline decoration-line underline-offset-4 hover:decoration-ink"
          >
            {copied ? "Copied" : "Copy JSON"}
          </button>
          <button type="button" onClick={download} className="text-ink underline decoration-line underline-offset-4 hover:decoration-ink">
            Download
          </button>
        </div>
      </div>
      <div className="px-5 py-6 sm:px-6">
        {tab === "summary" ? (
          <Summary cfg={cfg} />
        ) : (
          <pre className="max-h-[36rem] overflow-auto rounded-md bg-bg/70 p-4 font-mono text-xs leading-relaxed text-ink">
            {highlight(json)}
          </pre>
        )}
      </div>
    </div>
  )
}
