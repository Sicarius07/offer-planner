import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { ago, money, seconds } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Draft } from "@/state/drafts"

/** Drafts this browser has made, newest first. Opening one replays it from the saved run. */
export function DraftsDrawer({ drafts, currentId, open, onOpenChange, onOpen, onClear }: {
  drafts: Draft[]
  currentId: string | null
  open: boolean
  onOpenChange: (o: boolean) => void
  onOpen: (id: string) => void
  onClear: () => void
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="w-full gap-0 border-line bg-paper sm:max-w-sm">
        <SheetHeader className="border-b border-line px-6 py-5">
          <SheetTitle className="font-serif text-xl font-medium text-ink">Your drafts</SheetTitle>
          <SheetDescription className="text-sm text-soft">
            Kept in this browser for 30 days, the same as the drafts themselves.
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-auto p-3">
          <ul className="space-y-1">
            {drafts.map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  onClick={() => onOpen(d.id)}
                  className={cn(
                    "w-full rounded-md border px-3 py-2.5 text-left transition-colors",
                    d.id === currentId
                      ? "border-emerald/40 bg-emerald-wash"
                      : "border-transparent hover:border-line hover:bg-track",
                  )}
                >
                  <span className="line-clamp-2 text-sm leading-snug text-ink">{d.brief}</span>
                  <span className="mt-1 block text-2xs text-soft">
                    {d.id === currentId ? "Open now" : ago(d.at)}, {seconds(d.totalMs)}, {money(d.costUsd, 2)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="border-t border-line px-6 py-3">
          <button
            type="button"
            onClick={onClear}
            className="text-sm text-soft underline decoration-line underline-offset-4 hover:text-ink"
          >
            Clear this list
          </button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
