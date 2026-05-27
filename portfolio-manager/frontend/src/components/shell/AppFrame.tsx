import * as Popover from "@radix-ui/react-popover";
import { Activity, BriefcaseBusiness, KeyRound, ListChecks, Search, ShieldAlert, Sparkles } from "lucide-react";
import type { SelectedPolicy } from "../../types";
import { IconSlot, StatusDot, type UiIcon } from "../ui/Primitives";
import { PolicySelectorChip } from "../policy/PolicySelectorChip";
import type { AppTab, TelemetryItem } from "../../lib/viewModels";

export type NavItem = {
  id: AppTab;
  label: string;
  icon: UiIcon;
};

export const navItems: NavItem[] = [
  { id: "now", label: "Now", icon: Activity },
  { id: "portfolio", label: "Portfolio", icon: BriefcaseBusiness },
  { id: "risks", label: "Risks", icon: ShieldAlert },
  { id: "actions", label: "Actions", icon: ListChecks },
  { id: "connections", label: "Connections", icon: KeyRound }
];

export function CommandRail({ activeTab, onTab }: { activeTab: AppTab; onTab: (tab: AppTab) => void }) {
  return (
    <aside className="command-rail" aria-label="Signal Prime navigation">
      <div className="signal-brand">
        <div className="signal-mark">
          <Sparkles size={20} />
        </div>
        <div>
          <strong>Signal Prime</strong>
          <span>Private portfolio</span>
        </div>
      </div>
      <nav aria-label="Primary">
        {navItems.map((item) => {
          const IconComponent = item.icon;
          return (
            <button
              key={item.id}
              className={activeTab === item.id ? "active" : ""}
              aria-label={item.label}
              title={item.label}
              data-testid={`nav-${item.id}`}
              onClick={() => onTab(item.id)}
            >
              <IconSlot icon={IconComponent} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
      <div className="rail-footer">
        <span>Review mode</span>
        <strong>Advisory review</strong>
      </div>
    </aside>
  );
}

export function TopTelemetry({
  items,
  onOpenPalette,
  selectedPolicy,
  onPolicyChanged,
  onPolicyError,
}: {
  items: TelemetryItem[];
  onOpenPalette: () => void;
  selectedPolicy: SelectedPolicy | null;
  onPolicyChanged: (message: string) => Promise<void>;
  onPolicyError: (message: string) => void;
}) {
  return (
    <header className="top-telemetry" data-testid="top-telemetry">
      <button className="telemetry-search" data-testid="command-palette-open" onClick={onOpenPalette}>
        <Search size={16} />
        <span>Search</span>
        <kbd>⌘K</kbd>
      </button>
      <PolicySelectorChip current={selectedPolicy} onChanged={onPolicyChanged} onError={onPolicyError} />
      <div className="telemetry-items" aria-label="System health">
        {items.map((item) => (
          <Popover.Root key={item.label}>
            <Popover.Trigger asChild>
              <button className="telemetry-item" type="button" aria-label={`${item.label}: ${item.value}`}>
                <StatusDot tone={item.tone} />
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </button>
            </Popover.Trigger>
            <Popover.Portal>
              <Popover.Content className="telemetry-popover" sideOffset={10}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
                <p>{item.detail}</p>
                {item.actionLabel && item.onAction && (
                  <button type="button" className="telemetry-popover-action" onClick={item.onAction}>
                    {item.actionLabel}
                  </button>
                )}
                <Popover.Arrow className="telemetry-popover-arrow" />
              </Popover.Content>
            </Popover.Portal>
          </Popover.Root>
        ))}
      </div>
    </header>
  );
}

export function MobileDock({ activeTab, onTab }: { activeTab: AppTab; onTab: (tab: AppTab) => void }) {
  return (
    <nav className="mobile-dock" aria-label="Mobile primary navigation" data-testid="mobile-dock">
      {navItems.map((item) => {
        const IconComponent = item.icon;
        const mobileLabel = item.id === "connections" ? "Connect" : item.label;
        return (
          <button
            key={item.id}
            type="button"
            aria-label={item.label}
            title={item.label}
            data-testid={`mobile-nav-${item.id}`}
            className={`dock-button ${activeTab === item.id ? "active" : ""}`.trim()}
            onClick={() => onTab(item.id)}
          >
            <IconSlot icon={IconComponent} />
            <span>{mobileLabel}</span>
          </button>
        );
      })}
    </nav>
  );
}
