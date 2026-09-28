export const money = (n: number, digits = 0) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: digits, minimumFractionDigits: digits })

export const compact = (n: number) =>
  n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : `${n}`

export const seconds = (ms: number) => (ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`)

export const humanize = (tag: string) => tag.replaceAll("_", " ")

export const shortDate = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })

export const ago = (ts: number) => {
  const mins = Math.round((Date.now() - ts) / 60_000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  return days === 1 ? "yesterday" : `${days} days ago`
}
