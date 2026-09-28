/**
 * Answers to clarifying questions are appended to the brief as one labelled block:
 *
 *   We sell ...
 *
 *   Answers to your questions:
 *   - What do you sell? Soy candles
 *   - Who typically buys it? Mostly women
 *
 * Keeping them in the brief text means everything downstream (quotes, claim grounding)
 * treats them as things the advertiser said. The understand prompt knows this block.
 * Answering again merges into the block, and a new answer to the same question replaces
 * the old one.
 */
export const ANSWERS_HEADING = "Answers to your questions:"

export type QA = { question: string; answer: string }

export function splitBrief(brief: string): { base: string; answers: QA[] } {
  const i = brief.indexOf(ANSWERS_HEADING)
  if (i < 0) return { base: brief.trim(), answers: [] }
  const answers = brief
    .slice(i + ANSWERS_HEADING.length)
    .split("\n")
    .map((l) => l.replace(/^\s*-\s*/, "").trim())
    .filter(Boolean)
    .map((l) => {
      const q = l.indexOf("? ")
      return q < 0 ? { question: "", answer: l } : { question: l.slice(0, q + 1), answer: l.slice(q + 2) }
    })
  return { base: brief.slice(0, i).trim(), answers }
}

export function withAnswers(brief: string, added: QA[]): string {
  const { base, answers } = splitBrief(brief)
  const merged = [...answers.filter((a) => !added.some((n) => n.question === a.question)), ...added]
  if (!merged.length) return base
  const lines = merged.map((a) => `- ${a.question ? `${a.question} ` : ""}${a.answer}`)
  return `${base}\n\n${ANSWERS_HEADING}\n${lines.join("\n")}`
}
