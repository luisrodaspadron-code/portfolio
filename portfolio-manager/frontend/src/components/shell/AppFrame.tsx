import * as Popover from "@radix-ui/react-popover";
import { Activity, BriefcaseBusiness, KeyRound, ListChecks, Search, ShieldAlert, Sparkles } from "lucide-react";
import { CommandButton, IconSlot, StatusDot, type UiIcon } from "../ui/Primitives";
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
    <aside className="command-rail" aria-label="Signal PM navigation">
      <div className="signal-brand">
        <div className="signal-mark">
          <Sparkles size={20} />
        </div>
        <div>
          <strong>Signal PM</strong>
          <span>Private command</span>
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
        <span>Local-only</span>
        <strong>No broker trading</strong>
      </div>
    </aside>
  );
}

export function TopTelemetry({
  items,
  onOpenPalette,
  onPrimaryAction,
  primaryLabel,
  busy
}: {
  items: TelemetryItem[];
  onOpenPalette: () => void;
  onPrimaryAction: () => void;
  primaryLabel: string;
  busy: boolean;
}) {
  return (
    <header className="top-telemetry" data-testid="top-telemetry">
      <button className="telemetry-search" data-testid="command-palette-open" onClick={onOpenPalette}>
        <Search size={16} />
        <span>Command</span>
        <kbd>⌘K</kbd>
      </button>
      <div className="telemetry-items" aria-label="Live system telemetry">
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
                <Popover.Arrow className="telemetry-popover-arrow" />
              </Popover.Content>
            </Popover.Portal>
          </Popover.Root>
        ))}
      </div>
      <CommandButton icon={Sparkles} variant="primary" disabled={busy} data-testid="primary-telemetry-action" onClick={onPrimaryAction}>
        {primaryLabel}
      </CommandButton>
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
