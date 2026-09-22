const COLORS: Record<string, string> = {
  BACKWARD: "bg-[#3fb950]/15 text-[#3fb950] border-[#3fb950]/30",
  FORWARD: "bg-[#5b8def]/15 text-[#5b8def] border-[#5b8def]/30",
  BREAKING: "bg-[#f85149]/15 text-[#f85149] border-[#f85149]/30",
  BUSINESS_OUTCOME: "bg-[#3fb950]/15 text-[#3fb950] border-[#3fb950]/30",
  SUCCEEDED: "bg-[#3fb950]/15 text-[#3fb950] border-[#3fb950]/30",
  RECOVERABLE: "bg-[#d29922]/15 text-[#d29922] border-[#d29922]/30",
  HARD_FAILURE: "bg-[#f85149]/15 text-[#f85149] border-[#f85149]/30",
  FAILED: "bg-[#f85149]/15 text-[#f85149] border-[#f85149]/30",
  PENDING: "bg-[#7c828f]/15 text-[#7c828f] border-[#7c828f]/30",
  IN_PROGRESS: "bg-[#5b8def]/15 text-[#5b8def] border-[#5b8def]/30",
  CLOSED: "bg-[#3fb950]/15 text-[#3fb950] border-[#3fb950]/30",
  OPEN: "bg-[#f85149]/15 text-[#f85149] border-[#f85149]/30",
  HALF_OPEN: "bg-[#d29922]/15 text-[#d29922] border-[#d29922]/30",
  AGENT_CONTROLLED: "bg-[#5b8def]/15 text-[#5b8def] border-[#5b8def]/30",
  INTERVENTION_REQUESTED: "bg-[#d29922]/15 text-[#d29922] border-[#d29922]/30",
  HUMAN_CONTROLLED: "bg-[#a371f7]/15 text-[#a371f7] border-[#a371f7]/30",
  CONTROL_RETURNED: "bg-[#7c828f]/15 text-[#7c828f] border-[#7c828f]/30",
  RESUMED: "bg-[#3fb950]/15 text-[#3fb950] border-[#3fb950]/30",
  TERMINATED: "bg-[#7c828f]/15 text-[#7c828f] border-[#7c828f]/30",
  safe: "bg-[#3fb950]/15 text-[#3fb950] border-[#3fb950]/30",
  risky: "bg-[#f85149]/15 text-[#f85149] border-[#f85149]/30",
};

export default function Badge({ label }: { label: string }) {
  const cls = COLORS[label] ?? "bg-[#7c828f]/15 text-[#7c828f] border-[#7c828f]/30";
  return <span className={`mono text-xs px-2 py-0.5 rounded border ${cls}`}>{label}</span>;
}
