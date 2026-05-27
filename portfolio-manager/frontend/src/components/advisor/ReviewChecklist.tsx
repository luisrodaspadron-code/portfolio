import { useState } from "react";
import { Badge, SignalPanel } from "../ui/Primitives";

const DEFAULT_ITEMS = [
  { id: "price", label: "Price source checked", defaultChecked: true },
  { id: "gate", label: "Risk gate identified", defaultChecked: true },
  { id: "math", label: "Sizing math calculated", defaultChecked: true },
  { id: "tax", label: "Tax impact reviewed", defaultChecked: false },
  { id: "advisory", label: "Advisory-only scope understood", defaultChecked: false },
  { id: "review", label: "Next review scheduled", defaultChecked: false },
];

export function ReviewChecklist({ compact }: { compact?: boolean }) {
  const [checked, setChecked] = useState<Record<string, boolean>>(
    Object.fromEntries(DEFAULT_ITEMS.map((item) => [item.id, item.defaultChecked])),
  );
  const done = DEFAULT_ITEMS.filter((item) => checked[item.id]).length;

  return (
    <SignalPanel className={`review-checklist ${compact ? "compact" : ""}`} testId="review-checklist">
      <div className="panel-label-row">
        <span>Before acting</span>
        <Badge tone={done === DEFAULT_ITEMS.length ? "live" : "watch"}>{done}/{DEFAULT_ITEMS.length}</Badge>
      </div>
      <ul className="review-checklist-list">
        {DEFAULT_ITEMS.map((item) => (
          <li key={item.id}>
            <label>
              <input
                type="checkbox"
                checked={Boolean(checked[item.id])}
                onChange={(event) => setChecked((current) => ({ ...current, [item.id]: event.target.checked }))}
              />
              <span>{item.label}</span>
            </label>
          </li>
        ))}
      </ul>
    </SignalPanel>
  );
}
