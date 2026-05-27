import * as Dialog from "@radix-ui/react-dialog";
import * as Tooltip from "@radix-ui/react-tooltip";
import { motion, AnimatePresence } from "motion/react";
import type { ReactNode } from "react";
import type { Activity } from "lucide-react";
import { X } from "lucide-react";

export type UiIcon = typeof Activity;
export type Tone = "neutral" | "live" | "good" | "attention" | "danger" | "pass" | "watch" | "fail" | string;

export function IconSlot({ icon: IconComponent, className = "" }: { icon: UiIcon; className?: string }) {
  return (
    <span className={`ui-icon-slot ${className}`.trim()} aria-hidden="true">
      <IconComponent size={18} />
    </span>
  );
}

export function CommandButton({
  icon,
  children,
  variant = "secondary",
  className = "",
  ...props
}: {
  icon?: UiIcon;
  children: ReactNode;
  variant?: "primary" | "secondary" | "ghost" | "danger" | "quiet";
  className?: string;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={`command-button ${variant} ${className}`.trim()} {...props}>
      {icon && <IconSlot icon={icon} />}
      <span>{children}</span>
    </button>
  );
}

export function IconButton({
  icon,
  label,
  className = "",
  ...props
}: {
  icon: UiIcon;
  label: string;
  className?: string;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <button className={`icon-button ${className}`.trim()} aria-label={label} title={label} {...props}>
          <IconSlot icon={icon} />
        </button>
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content className="signal-tooltip" sideOffset={8}>
          {label}
          <Tooltip.Arrow className="signal-tooltip-arrow" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export function SignalPanel({
  children,
  className = "",
  testId
}: {
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  return (
    <section className={`signal-panel ${className}`.trim()} data-testid={testId}>
      {children}
    </section>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  return <span className={`signal-badge ${tone}`}>{children}</span>;
}

export function StatusDot({ tone = "neutral" }: { tone?: Tone }) {
  return <span className={`status-dot ${tone}`} aria-hidden="true" />;
}

export function SectionHeader({
  icon,
  eyebrow,
  title,
  body,
  action
}: {
  icon?: UiIcon;
  eyebrow?: string;
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <div className="section-header">
      <div className="section-heading">
        {icon && <IconSlot icon={icon} className="section-heading-icon" />}
        <div>
          {eyebrow && <span>{eyebrow}</span>}
          <h2>{title}</h2>
          {body && <p>{body}</p>}
        </div>
      </div>
      {action && <div className="section-header-action">{action}</div>}
    </div>
  );
}

export function DetailDrawer({
  open,
  onOpenChange,
  title,
  eyebrow,
  children
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  eyebrow?: string;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild>
              <motion.div
                className="drawer-overlay"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18 }}
              />
            </Dialog.Overlay>
            <Dialog.Content asChild>
              <motion.aside
                className="detail-drawer"
                initial={{ opacity: 0, x: 42 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 42 }}
                transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
              >
                <div className="drawer-header">
                  <div>
                    {eyebrow && <span>{eyebrow}</span>}
                    <Dialog.Title>{title}</Dialog.Title>
                  </div>
                  <Dialog.Close asChild>
                    <button className="icon-button" aria-label="Close drawer" title="Close drawer">
                      <IconSlot icon={X} />
                    </button>
                  </Dialog.Close>
                </div>
                {children}
              </motion.aside>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}

export function EmptyState({
  title,
  body,
  action
}: {
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{body}</p>
      {action && <div>{action}</div>}
    </div>
  );
}
