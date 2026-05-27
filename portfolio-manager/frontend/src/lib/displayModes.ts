export type DisplayMode = "command" | "research" | "focus" | "presentation";

export const DISPLAY_MODES: Array<{ id: DisplayMode; label: string; detail: string }> = [
  { id: "command", label: "Command", detail: "Balanced mission-control dashboard." },
  { id: "research", label: "Research", detail: "Show scores, source receipts, and eval evidence." },
  { id: "focus", label: "Focus", detail: "First action, math, blockers, and receipt only." },
  { id: "presentation", label: "Presentation", detail: "Large cards for demo or judging." },
];

export function displayModeClass(mode: DisplayMode) {
  return `display-mode-${mode}`;
}
