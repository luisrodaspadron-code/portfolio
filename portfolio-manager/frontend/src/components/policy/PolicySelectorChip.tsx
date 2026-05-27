import * as Popover from "@radix-ui/react-popover";
import { ChevronDown, Shield } from "lucide-react";
import { useState } from "react";
import { updatePolicy } from "../../api";
import type { SelectedPolicy } from "../../types";
import { pct } from "../../lib/format";
import { POLICY_PRESET_PREVIEWS, PRESET_TO_SETTINGS, type PolicyPresetId } from "../../lib/policyPresets";
import { Badge } from "../ui/Primitives";

export function PolicySelectorChip({
  current,
  onChanged,
  onError,
}: {
  current: SelectedPolicy | null;
  onChanged: (message: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const activePreset = (current?.preset ?? "balanced") as PolicyPresetId;

  async function selectPreset(preset: PolicyPresetId) {
    if (preset === activePreset || busy) {
      setOpen(false);
      return;
    }
    setBusy(true);
    try {
      await updatePolicy(PRESET_TO_SETTINGS[preset]);
      await onChanged(`Policy switched to ${preset}. Run the advisor to refresh the receipt.`);
      setOpen(false);
    } catch (error) {
      onError(error instanceof Error ? error.message : "Unable to update policy");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          className="policy-selector-chip"
          data-testid="policy-selector-chip"
          aria-label={`Policy: ${current?.name ?? "Balanced"}`}
        >
          <Shield size={14} />
          <span>Policy</span>
          <strong>{current?.name ?? "Balanced"}</strong>
          <ChevronDown size={14} />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="policy-selector-popover" sideOffset={8} align="start">
          <header>
            <span>Risk policy</span>
            <p>Select a preset. Thresholds apply on the next advisor run.</p>
          </header>
          <div className="policy-selector-options">
            {POLICY_PRESET_PREVIEWS.map((preset) => {
              const active = preset.id === activePreset;
              return (
                <button
                  key={preset.id}
                  type="button"
                  className={`policy-selector-option ${active ? "active" : ""}`}
                  disabled={busy}
                  onClick={() => void selectPreset(preset.id)}
                >
                  <div className="policy-selector-option-head">
                    <strong>{preset.label}</strong>
                    {active && <Badge tone="live">Active</Badge>}
                  </div>
                  <p>{preset.description}</p>
                  <dl>
                    <div>
                      <dt>Warning</dt>
                      <dd>{pct(preset.singleStock.warning)}</dd>
                    </div>
                    <div>
                      <dt>Hard buy-block</dt>
                      <dd>{pct(preset.singleStock.hardBuyBlock)}</dd>
                    </div>
                    <div>
                      <dt>Sector cap</dt>
                      <dd>{pct(preset.sectorCap)}</dd>
                    </div>
                    <div>
                      <dt>Crypto</dt>
                      <dd>{preset.cryptoEnabled ? "Allowed" : "Off by default"}</dd>
                    </div>
                  </dl>
                  {preset.id === "competition" && (
                    <small className="policy-selector-warning">{preset.warning}</small>
                  )}
                </button>
              );
            })}
          </div>
          <Popover.Arrow className="telemetry-popover-arrow" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
