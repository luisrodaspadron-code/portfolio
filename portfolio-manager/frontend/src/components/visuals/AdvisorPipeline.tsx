import { motion } from "motion/react";
import { CheckCircle2, CircleDashed, Lock, RadioTower } from "lucide-react";
import type { PipelineStep } from "../../lib/viewModels";
import { IconSlot } from "../ui/Primitives";

function stepIcon(status: PipelineStep["status"]) {
  if (status === "complete") return CheckCircle2;
  if (status === "blocked") return Lock;
  if (status === "active") return RadioTower;
  return CircleDashed;
}

export function AdvisorPipeline({ steps }: { steps: PipelineStep[] }) {
  return (
    <div className="advisor-pipeline" data-testid="advisor-pipeline">
      {steps.map((step, index) => (
        <motion.div
          className={`pipeline-step ${step.status}`}
          key={step.label}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: index * 0.05, duration: 0.25 }}
        >
          <IconSlot icon={stepIcon(step.status)} />
          <div>
            <strong>{step.label}</strong>
            <span>{step.detail}</span>
          </div>
        </motion.div>
      ))}
    </div>
  );
}
