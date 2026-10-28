/** What a chat answer is doing right now, in plain words, from its answer workflow (pure, unit tested). */
type Entity = Record<string, any>;

export function answerPhase(message: Entity | null | undefined): string {
  const running: string = message?.answer_workflow?.steps?.find((step: Entity) => step.status === "running")?.label || "";
  if (!running) return "Thinking";
  if (/Answering or routing|Understanding/i.test(running)) return "Understanding your question";
  if (/Generating|Repairing|Writing/i.test(running)) return "Writing the answer";
  if (/Validating|Saving|Checking citation/i.test(running)) return "Checking the answer against its sources";
  if (/Resolving|Checking accessible/i.test(running)) return "Checking dataset access";
  return "Searching your knowledge";
}

/** Steps finished so far and the total, for "3 of 5 steps". */
export function answerProgress(message: Entity | null | undefined): { done: number; total: number } {
  const steps: Entity[] = message?.answer_workflow?.steps || [];
  return { done: steps.filter(step => step.status === "completed" || step.status === "done").length, total: steps.length };
}
