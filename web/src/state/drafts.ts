/** Drafts made in this browser.
 *
 * There are no accounts, so the list is local: it never shows anyone else's drafts, and
 * clearing browser data clears it. The runs themselves live on the server for 30 days,
 * which is how long an entry is worth keeping here.
 */

export type Draft = { id: string; brief: string; at: number; costUsd: number; totalMs: number }

const KEY = "offer-planner.drafts"
const MAX = 20
const KEEP_MS = 30 * 24 * 60 * 60 * 1000

function read(): Draft[] {
  try {
    const raw: unknown = JSON.parse(window.localStorage.getItem(KEY) ?? "[]")
    if (!Array.isArray(raw)) return []
    return (raw as Draft[])
      .filter((d) => d?.id && typeof d.at === "number" && Date.now() - d.at < KEEP_MS)
      .sort((a, b) => b.at - a.at)
      .slice(0, MAX)
  } catch {
    return [] // private browsing, or something else wrote to the key
  }
}

function write(drafts: Draft[]): Draft[] {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(drafts))
  } catch {
    /* out of quota or storage blocked: the list is a convenience, not the record */
  }
  return drafts
}

export const loadDrafts = read
export const rememberDraft = (d: Draft) => write([d, ...read().filter((x) => x.id !== d.id)].slice(0, MAX))
export const forgetDraft = (id: string) => write(read().filter((d) => d.id !== id))
export const clearDrafts = () => write([])
