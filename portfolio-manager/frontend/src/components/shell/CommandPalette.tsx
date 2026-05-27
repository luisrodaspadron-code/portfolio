import * as Dialog from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { AnimatePresence, motion } from "motion/react";
import { Search, X } from "lucide-react";
import { useEffect } from "react";
import { IconSlot, type UiIcon } from "../ui/Primitives";

export type PaletteAction = {
  id: string;
  label: string;
  detail: string;
  icon: UiIcon;
  group: "Navigation" | "Actions" | "Holdings" | "Receipts" | "Ask Signal";
  shortcut?: string;
  run: () => void;
};

export function CommandPalette({
  open,
  onOpenChange,
  actions
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  actions: PaletteAction[];
}) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpenChange(!open);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onOpenChange, open]);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild>
              <motion.div className="palette-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            </Dialog.Overlay>
            <Dialog.Content asChild>
              <motion.div
                className="command-palette"
                initial={{ opacity: 0, y: -16, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -16, scale: 0.98 }}
                transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
              >
                <div className="palette-head">
                  <Dialog.Title>Search</Dialog.Title>
                  <Dialog.Close asChild>
                    <button className="icon-button" aria-label="Close search" title="Close search">
                      <IconSlot icon={X} />
                    </button>
                  </Dialog.Close>
                </div>
                <Command>
                  <div className="palette-input">
                    <Search size={18} />
                    <Command.Input placeholder="Search screens, holdings, risks, or Ask Signal..." autoFocus />
                  </div>
                  <Command.List>
                    <Command.Empty>No matching result.</Command.Empty>
                    {(["Navigation", "Actions", "Holdings", "Receipts", "Ask Signal"] as const).map((group) => {
                      const groupActions = actions.filter((action) => action.group === group);
                      if (!groupActions.length) return null;
                      return (
                        <Command.Group heading={group} key={group}>
                          {groupActions.map((action) => {
                            const IconComponent = action.icon;
                            return (
                              <Command.Item
                                key={action.id}
                                value={`${action.label} ${action.detail} ${group}`}
                                onSelect={() => {
                                  action.run();
                                  onOpenChange(false);
                                }}
                              >
                                <IconSlot icon={IconComponent} />
                                <div>
                                  <strong>{action.label}</strong>
                                  <span>{action.detail}</span>
                                </div>
                                {action.shortcut && <kbd>{action.shortcut}</kbd>}
                              </Command.Item>
                            );
                          })}
                        </Command.Group>
                      );
                    })}
                  </Command.List>
                </Command>
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
