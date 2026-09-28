/** Heat ramp shared with tuneloop's grid: rust-pink → sand → mint. */
const STOPS: [number, [number, number, number]][] = [
  [0, [0xe9, 0xc9, 0xc1]],
  [50, [0xef, 0xe2, 0xbd]],
  [100, [0xc8, 0xe6, 0xcf]],
]

export function heat(score: number): string {
  const v = Math.max(0, Math.min(100, score))
  const i = v <= 50 ? 0 : 1
  const [a, ca] = STOPS[i]
  const [b, cb] = STOPS[i + 1]
  const t = (v - a) / (b - a)
  const c = ca.map((x, k) => Math.round(x + (cb[k] - x) * t))
  return `rgb(${c[0]} ${c[1]} ${c[2]})`
}

/** Muted categorical hues (borrowed from tuneloop's task-type palette). */
const CATEGORY: Record<string, string> = {
  pet: "#3e7a5a",
  apparel: "#4a6fa5",
  wellness_services: "#c07a3e",
  wellness_dtc: "#c07a3e",
  beauty: "#8a63b0",
  home: "#4f9a8f",
  groceries: "#c4a24a",
  beverages: "#a4506a",
  meal_kits: "#6b7a3a",
  instant_delivery: "#6b7a3a",
}

export const categoryColor = (c: string) => CATEGORY[c] ?? "#9a958b"
