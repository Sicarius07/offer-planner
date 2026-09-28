import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react"

import { getCatalog, getCredits, getExampleRun, getExamples, getMeta, streamPlan } from "@/api/client"
import type { Catalog, Credits, Example, Meta, PlanEvent } from "@/api/types"
import { Audiences } from "@/components/Audiences"
import { BriefForm, type RunOptions } from "@/components/BriefForm"
import { CampaignView } from "@/components/CampaignView"
import { FitMatrix } from "@/components/FitMatrix"
import { RunDrawer } from "@/components/RunDrawer"
import { Panel, Section, SkeletonRows } from "@/components/Section"
import { StageDots, StageRail } from "@/components/StageRail"
import { NeedsInput, Understanding, type AnswerHandlers } from "@/components/Understanding"
import { withAnswers } from "@/lib/brief"
import { seconds } from "@/lib/format"
import { initialPlan, reducer } from "@/state/plan"

const REPLAY_DELAY: Partial<Record<PlanEvent["type"], number>> = {
  profile: 450, publishers: 500, personas: 350, creative: 220, config: 300,
}

export default function App() {
  const [plan, dispatch] = useReducer(reducer, initialPlan)
  const [meta, setMeta] = useState<Meta | null>(null)
  const [credits, setCredits] = useState<Credits | null>(null)
  const [examples, setExamples] = useState<Example[]>([])
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [brief, setBrief] = useState("")
  const [options, setOptions] = useState<Omit<RunOptions, "brief">>({
    monthlyBudget: 10000, flightDays: 30, model: "anthropic:claude-opus-5", allowCompetitors: false,
  })
  const [drawer, setDrawer] = useState(false)
  const abort = useRef<AbortController | null>(null)
  const replayRef = useRef<((ex: Example) => void) | null>(null)

  const refreshCredits = useCallback(() => { getCredits().then(setCredits).catch(() => {}) }, [])

  useEffect(() => {
    getMeta().then((m) => {
      setMeta(m)
      setOptions((o) => ({ ...o, monthlyBudget: m.default_monthly_budget_usd, flightDays: m.default_flight_days, model: m.default_model }))
    }).catch(() => {})
    getExamples().then((exs) => {
      setExamples(exs)
      // Deep link: ?example=ex01 opens a sample straight away (handy for sharing a result).
      const id = new URLSearchParams(window.location.search).get("example")
      const ex = exs.find((e) => e.id === id)
      if (ex) {
        setBrief(ex.brief)
        if (ex.cached) replayRef.current?.(ex)
      }
    }).catch(() => {})
    getCatalog().then(setCatalog).catch(() => {})
    refreshCredits()
  }, [refreshCredits])

  const pubs = useMemo(() => new Map(catalog?.publishers.map((p) => [p.publisher.id, p]) ?? []), [catalog])
  const personas = useMemo(() => new Map(catalog?.personas.map((p) => [p.persona.id, p]) ?? []), [catalog])

  const run = useCallback(async (text: string, extra: { force?: boolean } = {}) => {
    abort.current?.abort()
    const ctrl = new AbortController()
    abort.current = ctrl
    dispatch({ type: "start", brief: text, source: "live" })
    document.getElementById("results")?.scrollIntoView({ behavior: "smooth", block: "start" })
    try {
      await streamPlan(
        {
          brief: text,
          monthly_budget_usd: options.monthlyBudget,
          flight_days: options.flightDays,
          model: options.model,
          allow_competitors: options.allowCompetitors,
          force: extra.force ?? false,
        },
        (event) => dispatch({ type: "event", event }),
        ctrl.signal,
      )
    } catch (e) {
      if (!ctrl.signal.aborted) dispatch({ type: "fail", message: e instanceof Error ? e.message : String(e) })
    }
    refreshCredits()
  }, [options, refreshCredits])

  const replay = useCallback(async (ex: Example) => {
    abort.current?.abort()
    const ctrl = new AbortController()
    abort.current = ctrl
    const data = await getExampleRun(ex.id)
    dispatch({ type: "start", brief: data.brief, source: "cached" })
    for (const event of data.events) {
      if (ctrl.signal.aborted) return
      const wait = REPLAY_DELAY[event.type]
      if (wait) await new Promise((r) => setTimeout(r, wait))
      dispatch({ type: "event", event })
    }
  }, [])

  replayRef.current = replay

  const onExample = (ex: Example) => {
    setBrief(ex.brief)
    if (ex.cached) replay(ex)
    else run(ex.brief)
  }

  // Answers to clarifying questions: previewed in the brief box as they're picked, sent together.
  const answers: AnswerHandlers = {
    onChange: (qa) => setBrief(withAnswers(plan.brief, qa)),
    onSubmit: (qa) => {
      const next = withAnswers(plan.brief, qa)
      setBrief(next)
      run(next)
    },
  }

  const running = plan.status === "running"
  const started = plan.status !== "idle"
  const creativeCount = Object.keys(plan.creatives).length
  const skipped = (s: keyof typeof plan.stages) => plan.stages[s].status === "skipped"
  const failed = (s: keyof typeof plan.stages) => plan.stages[s].status === "failed"

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-paper">
        <div className="mx-auto flex max-w-[1180px] items-center justify-between gap-4 px-4 py-3.5 sm:px-6">
          <div className="flex items-baseline gap-3">
            <span className="font-serif text-lg font-medium text-ink">Offer Planner</span>
            <span className="hidden text-sm text-soft sm:inline">From one line about your business to a post-purchase campaign</span>
          </div>
          {plan.run && (
            <button
              type="button"
              onClick={() => setDrawer(true)}
              className="text-sm text-ink underline decoration-line underline-offset-4 hover:decoration-ink"
            >
              Run details, {seconds(plan.run.totalMs)}
            </button>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-[1180px] px-4 pt-6 pb-24 sm:px-6 sm:pt-8">
        <BriefForm
          meta={meta}
          credits={credits}
          examples={examples}
          running={running}
          value={brief}
          onChange={setBrief}
          onSubmit={() => run(brief)}
          onExample={onExample}
          options={options}
          setOptions={setOptions}
        />

        {!started && (
          <p className="mt-6 max-w-prose text-sm text-soft">
            We’ll read your description back to you, show which publishers fit and which don’t (and why), pick the shoppers
            worth talking to, write an offer for each, and hand you a campaign config you can launch or edit.
          </p>
        )}

        {started && (
          <div id="results" className="mt-10 grid scroll-mt-4 gap-10 lg:grid-cols-[200px_1fr]">
            <aside>
              <StageRail plan={plan} />
            </aside>
            <div className="min-w-0 space-y-12">
              <StageDots plan={plan} />
              {plan.errors.filter((e) => e.stage === "run" || e.stage === "understand").map((e, i) => (
                <p key={i} className="rounded-lg border border-rust/30 bg-rust-wash/50 px-4 py-3 text-sm text-rust">{e.message}</p>
              ))}

              <Section
                id="understand"
                title="What we understood"
                aside={plan.source === "cached" && "Saved run of this sample. Edit the text and draft again for a live run."}
              >
                {plan.profile ? (
                  <Understanding profile={plan.profile} animate answers={answers} key={plan.brief} />
                ) : plan.stages.understand.status === "failed" ? null : (
                  <Panel className="px-8 py-8">
                    <div className="h-6 w-4/5 animate-pulse rounded-sm bg-track" />
                    <div className="mt-3 h-6 w-3/5 animate-pulse rounded-sm bg-track/70" />
                  </Panel>
                )}
                {plan.needsInput && (
                  <div className="mt-4">
                    <NeedsInput
                      reason={plan.needsInput.reason}
                      questions={plan.needsInput.questions}
                      handlers={answers}
                      key={plan.brief}
                      onForce={() => run(plan.brief, { force: true })}
                    />
                  </div>
                )}
              </Section>

              {!skipped("publishers") && plan.stages.understand.status !== "failed" && (
                <Section
                  id="publishers"
                  title="Where to run"
                  aside={plan.publishers && `${plan.publishers.recommended.length} recommended, ${plan.publishers.test.length} to test, ${plan.publishers.excluded.length} excluded`}
                >
                  <StageErrors plan={plan} stage="publishers" />
                  {plan.publishers ? (
                    <FitMatrix plan={plan.publishers} catalog={pubs} />
                  ) : (
                    <Panel><SkeletonRows rows={6} /></Panel>
                  )}
                </Section>
              )}

              {!skipped("personas") && !failed("personas") && plan.stages.understand.status !== "failed" && (
                <Section
                  id="personas"
                  title="Who to reach, and what to say"
                  aside={plan.personas && `${plan.personas.picks.length} personas, ${creativeCount} ads`}
                >
                  <span id="creative" className="block -translate-y-6 scroll-mt-10 lg:scroll-mt-0" />
                  <StageErrors plan={plan} stage="personas" />
                  <StageErrors plan={plan} stage="creative" />
                  {plan.personas ? (
                    <Audiences plan={plan.personas} creatives={plan.creatives} personas={personas} pubs={pubs} brand={plan.profile?.brand_name ?? null}
                      settled={failed("creative") || plan.stages.creative.status === "done"} />
                  ) : (
                    <Panel><SkeletonRows rows={3} height={120} /></Panel>
                  )}
                </Section>
              )}
              {skipped("personas") && !plan.needsInput && plan.publishers && (
                <p className="text-sm text-soft">No personas or ads: with no publisher worth running on, there’s no one to write for yet.</p>
              )}

              {!skipped("campaign") && plan.stages.understand.status !== "failed" && (
                <Section id="campaign" title="Campaign">
                  {plan.config ? (
                    <CampaignView
                      cfg={plan.config}
                      personaName={(id) => personas.get(id)?.persona.name ?? id}
                      summaryPending={plan.stages.campaign.status === "started"}
                    />
                  ) : <Panel><SkeletonRows rows={4} /></Panel>}
                </Section>
              )}
            </div>
          </div>
        )}
      </main>
      <RunDrawer plan={plan} open={drawer} onOpenChange={setDrawer} />
    </div>
  )
}

function StageErrors({ plan, stage }: { plan: ReturnType<typeof reducer>; stage: string }) {
  const errs = plan.errors.filter((e) => e.stage === stage)
  if (!errs.length) return null
  return (
    <div className="mb-3 space-y-1">
      {errs.map((e, i) => (
        <p key={i} className="rounded-md border border-amber/40 bg-amber-wash/50 px-3 py-2 text-sm text-ink">{e.message}</p>
      ))}
    </div>
  )
}
