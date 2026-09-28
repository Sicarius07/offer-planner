import type { Catalog, Example, Meta, PlanEvent, PlanRequest } from "./types"

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

export const getMeta = () => getJSON<Meta>("/api/meta")
export const getExamples = () => getJSON<Example[]>("/api/examples")
export const getCatalog = () => getJSON<Catalog>("/api/catalog")
export const getExampleRun = (id: string) =>
  getJSON<{ id: string; brief: string; events: PlanEvent[] }>(`/api/examples/${id}`)

/**
 * POST /api/plan and read the server-sent events off the response body.
 * (EventSource only supports GET, so this parses the stream by hand.)
 */
export async function streamPlan(
  req: PlanRequest,
  onEvent: (e: PlanEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/plan", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(req),
    signal,
  })
  if (!res.ok || !res.body) {
    let message = `Request failed (${res.status})`
    try {
      const body = await res.json()
      message = body.detail ?? message
    } catch {
      /* not JSON */
    }
    throw new Error(message)
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ""
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    let cut: number
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, cut)
      buffer = buffer.slice(cut + 2)
      const data = frame
        .split("\n")
        .filter((l) => l.startsWith("data: "))
        .map((l) => l.slice(6))
        .join("\n")
      if (data) onEvent(JSON.parse(data) as PlanEvent)
    }
  }
}
