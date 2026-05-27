import * as Dialog from "@radix-ui/react-dialog";
import { AnimatePresence, motion } from "motion/react";
import { FormEvent, useEffect, useState } from "react";
import { BrainCircuit, Send, X } from "lucide-react";
import { askCopilot } from "../../api";
import type { Dashboard } from "../../types";
import { number, titleCase } from "../../lib/format";
import { Badge, CommandButton, IconSlot } from "../ui/Primitives";

type Message = {
  role: "user" | "assistant";
  text: string;
  meta?: string;
};

const starterQuestions = [
  "What is the biggest risk in my current portfolio?",
  "Why is META a breach?",
  "What assets did you consider?",
  "How did SEC EDGAR affect this recommendation?",
  "What would change your mind?"
];

export function AskSignalPanel({
  dashboard,
  open,
  initialQuestion,
  screenContext,
  onOpenChange,
  onActivity
}: {
  dashboard: Dashboard;
  open: boolean;
  initialQuestion?: string;
  screenContext: string;
  onOpenChange: (open: boolean) => void;
  onActivity: (running: boolean) => void;
}) {
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "Ask me about the current portfolio, risk breaches, market universe, data sources, or why an action is blocked.",
      meta: dashboard.ai_status.profile_summary
    }
  ]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (initialQuestion && open) setQuestion(initialQuestion);
  }, [initialQuestion, open]);

  async function submit(event?: FormEvent, override?: string) {
    event?.preventDefault();
    const prompt = (override ?? question).trim();
    if (!prompt || busy) return;
    setQuestion("");
    setMessages((current) => [...current, { role: "user", text: prompt }]);
    setBusy(true);
    onActivity(true);
    try {
      const response = await askCopilot({ question: prompt, conversation_id: conversationId, screen_context: screenContext });
      setConversationId(response.conversation_id);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: response.answer,
          meta: `${titleCase(response.status)} · ${number(response.total_tokens)} tokens · ${response.model}`
        }
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: error instanceof Error ? error.message : "Signal could not answer right now.",
          meta: "Fallback active"
        }
      ]);
    } finally {
      setBusy(false);
      onActivity(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild>
              <motion.div className="copilot-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            </Dialog.Overlay>
            <Dialog.Content asChild>
              <motion.aside
                className="ask-signal-panel"
                data-testid="ask-signal-panel"
                initial={{ opacity: 0, x: 36 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 36 }}
                transition={{ duration: 0.22 }}
              >
                <header>
                  <div>
                    <span>AI copilot</span>
                    <Dialog.Title>Ask Signal</Dialog.Title>
                  </div>
                  <Badge tone={dashboard.ai_activity === "reviewed" ? "live" : dashboard.ai_status.configured ? "good" : "watch"}>
                    {busy ? "Running" : titleCase(dashboard.ai_activity)}
                  </Badge>
                  <Dialog.Close asChild>
                    <button className="icon-button" aria-label="Close Ask Signal">
                      <IconSlot icon={X} />
                    </button>
                  </Dialog.Close>
                </header>

                <div className="copilot-messages">
                  {messages.map((message, index) => (
                    <article className={message.role} key={`${message.role}-${index}`}>
                      <p>{message.text}</p>
                      {message.meta && <small>{message.meta}</small>}
                    </article>
                  ))}
                  {busy && (
                    <article className="assistant thinking">
                      <IconSlot icon={BrainCircuit} />
                      <p>Reading the latest advisor packet...</p>
                    </article>
                  )}
                </div>

                <div className="starter-questions">
                  {starterQuestions.map((starter) => (
                    <button key={starter} type="button" onClick={() => submit(undefined, starter)} disabled={busy}>
                      {starter}
                    </button>
                  ))}
                </div>

                <form className="copilot-input" onSubmit={submit}>
                  <input
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    placeholder="Ask about risk, AI, holdings, or market scope..."
                    aria-label="Ask Signal a question"
                  />
                  <CommandButton icon={Send} variant="primary" type="submit" disabled={busy || !question.trim()}>
                    Ask
                  </CommandButton>
                </form>
              </motion.aside>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
