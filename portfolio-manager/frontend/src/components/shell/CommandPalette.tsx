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
                  <Dialog.Title>Command Center</Dialog.Title>
                  <Dialog.Close asChild>
                    <button className="icon-button" aria-label="Close command center" title="Close command center">
                      <IconSlot icon={X} />
                    </button>
                  </Dialog.Close>
                </div>
                <Command>
                  <div className="palette-input">
                    <Search size={18} />
                    <Command.Input placeholder="Search actions, setup, risks, or Ask Signal..." autoFocus />
                  </div>
                  <Command.List>
                    <Command.Empty>No matching command.</Command.Empty>
                    <Command.Group heading="Workspace">
                      {actions.map((action) => {
                        const IconComponent = action.icon;
                        return (
                          <Command.Item
                            key={action.id}
                            value={`${action.label} ${action.detail}`}
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
                          </Command.Item>
                        );
                      })}
                    </Command.Group>
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
