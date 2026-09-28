import { MenuIcon } from "lucide-react"
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react"

import { getCatalog, getCredits, getExampleRun, getExamples, getMeta, getSavedRun, streamPlan } from "@/api/client"
import type { Catalog, Credits, Example, Meta, PlanEvent } from "@/api/types"
import { Audiences } from "@/components/Audiences"
import { BriefForm, type RunOptions } from "@/components/BriefForm"
import { CampaignView } from "@/components/CampaignView"
import { DraftsDrawer } from "@/components/DraftsDrawer"
import { FitMatrix } from "@/components/FitMatrix"
import { RunDrawer } from "@/components/RunDrawer"
import { Panel, Section, SkeletonRows } from "@/components/Section"
import { StageDots, StageRail } from "@/components/StageRail"
import { NeedsInput, Understanding, type AnswerHandlers } from "@/components/Understanding"
import { withAnswers } from "@/lib/brief"
import { seconds } from "@/lib/format"
import { clearDrafts, forgetDraft, loadDrafts, rememberDraft, type Draft } from "@/state/drafts"
import { initialPlan, reducer } from "@/state/plan"

const REPLAY_DELAY: Partial<Record<PlanEvent["type"], number>> = {
  profile: 450, publishers: 500, personas: 350, creative: 220, config: 300,
}

/** ?run=<id> makes a finished draft reloadable and shareable, like ?example= for the samples. */
function putRunInUrl(id: string | null) {
  const url = new URL(window.location.href)
  if (id) url.searchParams.set("run", id)
  else url.searchParams.delete("run")
  window.history.replaceState(null, "", url)
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
  const [drafts, setDrafts] = useState<Draft[]>(loadDrafts)
  const [draftsOpen, setDraftsOpen] = useState(false)
  // Which stored draft is on screen. Kept apart from plan.run.id: this is the id the link
  // and the list use, so the two can't drift.
  const [openId, setOpenId] = useState<string | null>(null)
  const [linkError, setLinkError] = useState<string | null>(null)
  const abort = useRef<AbortController | null>(null)
  const replayRef = useRef<((ex: Example) => void) | null>(null)
  const openSavedRef = useRef<((id: string) => void) | null>(null)

  const refreshCredits = useCallback(() => { getCredits().then(setCredits).catch(() => {}) }, [])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    getMeta().then((m) => {
      setMeta(m)
      setOptions((o) => ({ ...o, monthlyBudget: m.default_monthly_budget_usd, flightDays: m.default_flight_days, model: m.default_model }))
    }).catch(() => {})
    getExamples().then((exs) => {
      setExamples(exs)
      // Deep link: ?example=ex01 opens a sample straight away. A ?run= link wins over it.
      const ex = exs.find((e) => e.id === params.get("example"))
      if (ex && !params.get("run")) {
        setBrief(ex.brief)
        if (ex.cached) replayRef.current?.(ex)
      }
    }).catch(() => {})
    getCatalog().then(setCatalog).catch(() => {})
    refreshCredits()

    const runId = params.get("run")
    if (runId) openSavedRef.current?.(runId)
  }, [refreshCredits])

  const pubs = useMemo(() => new Map(catalog?.publishers.map((p) => [p.publisher.id, p]) ?? []), [catalog])
  const personas = useMemo(() => new Map(catalog?.personas.map((p) => [p.persona.id, p]) ?? []), [catalog])

  const run = useCallback(async (text: string, extra: { force?: boolean } = {}) => {
    abort.current?.abort()
    const ctrl = new AbortController()
    abort.current = ctrl
    setLinkError(null)
    setOpenId(null)
    putRunInUrl(null)
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
        (event) => {
          dispatch({ type: "event", event })
          // The finished draft becomes a link and joins this browser's list, so a reload or
          // a second visit brings it back instead of losing it.
          if (event.type === "done" && meta?.saved_runs) {
            putRunInUrl(event.run_id)
            setOpenId(event.run_id)
            setDrafts(rememberDraft({
              id: event.run_id, brief: text, at: Date.now(),
              costUsd: event.cost_usd, totalMs: event.total_ms,
            }))
          }
        },
        ctrl.signal,
      )
    } catch (e) {
      if (!ctrl.signal.aborted) dispatch({ type: "fail", message: e instanceof Error ? e.message : String(e) })
    }
    refreshCredits()
  }, [meta?.saved_runs, options, refreshCredits])

  const play = useCallback(async (brief: string, events: PlanEvent[], source: "cached" | "saved") => {
    abort.current?.abort()
    const ctrl = new AbortController()
    abort.current = ctrl
    dispatch({ type: "start", brief, source })
    for (const event of events) {
      if (ctrl.signal.aborted) return
      // Samples unfold stage by stage to show the shape of a run; a saved draft is what
      // someone came back for, so it appears at once.
      const wait = source === "cached" ? REPLAY_DELAY[event.type] : 0
      if (wait) await new Promise((r) => setTimeout(r, wait))
      dispatch({ type: "event", event })
    }
  }, [])

  const replay = useCallback(async (ex: Example) => {
    setLinkError(null)
    setOpenId(null)
    putRunInUrl(null)
    const data = await getExampleRun(ex.id)
    await play(data.brief, data.events, "cached")
  }, [play])

  /** Reopen a finished draft, from its link or from the list. */
  const openSaved = useCallback(async (id: string) => {
    setDraftsOpen(false)
    setLinkError(null)
    try {
      const saved = await getSavedRun(id)
      setBrief(saved.brief)
      putRunInUrl(id)
      setOpenId(id)
      await play(saved.brief, saved.events, "saved")
    } catch {
      putRunInUrl(null)
      setOpenId(null)
      setDrafts(forgetDraft(id))
      setLinkError("That draft has expired. Drafts are kept for 30 days; draft it again below.")
    }
  }, [play])

  replayRef.current = replay
  openSavedRef.current = openSaved

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
  const shareable = plan.status === "done" && (plan.source === "saved" || (plan.source === "live" && !!meta?.saved_runs))

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-paper">
        <div className="mx-auto flex max-w-[1180px] items-center justify-between gap-4 px-4 py-3.5 sm:px-6">
          <div className="flex items-center gap-3">
            {drafts.length > 0 && (
              <button
                type="button"
                onClick={() => setDraftsOpen(true)}
                className="-ml-1.5 flex items-center gap-1.5 rounded-md px-1.5 py-1 text-sm text-ink transition-colors hover:bg-track"
              >
                <MenuIcon className="size-4 text-soft" aria-hidden />
                Drafts
              </button>
            )}
            <div className="flex items-baseline gap-3">
              <span className="font-serif text-lg font-medium text-ink">Offer Planner</span>
              <span className="hidden text-sm text-soft sm:inline">From one line about your business to a post-purchase campaign</span>
            </div>
          </div>
          {plan.run && (
            <div className="flex items-baseline gap-4">
              {shareable && openId && <ShareLink runId={openId} />}
              <button
                type="button"
                onClick={() => setDrawer(true)}
                className="text-sm text-ink underline decoration-line underline-offset-4 hover:decoration-ink"
              >
                Run details, {seconds(plan.run.totalMs)}
              </button>
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-[1180px] px-4 pt-6 pb-24 sm:px-6 sm:pt-8">
        {linkError && (
          <p className="mb-4 rounded-md border border-line bg-paper px-3.5 py-2.5 text-sm text-rust">{linkError}</p>
        )}
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
                aside={(plan.source === "cached" && "Saved run of this sample. Edit the text and draft again for a live run.")
                  || (plan.source === "saved" && "A saved draft, reopened from its link. Edit the text and draft again for a fresh run.")}
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
      <DraftsDrawer
        drafts={drafts}
        currentId={openId}
        open={draftsOpen}
        onOpenChange={setDraftsOpen}
        onOpen={openSaved}
        onClear={() => {
          setDrafts(clearDrafts())
          setDraftsOpen(false)
        }}
      />
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

/** Copies the ?run= link for a finished draft, so it survives a reload and can be sent on. */
function ShareLink({ runId }: { runId: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      onClick={() => {
        const url = `${window.location.origin}${window.location.pathname}?run=${runId}`
        navigator.clipboard.writeText(url).then(() => {
          setCopied(true)
          setTimeout(() => setCopied(false), 2000)
        }).catch(() => {})
      }}
      className="text-sm text-ink underline decoration-line underline-offset-4 hover:decoration-ink"
    >
      {copied ? "Link copied" : "Copy link"}
    </button>
  )
}
