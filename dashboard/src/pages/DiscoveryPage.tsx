import { useEffect, useRef, useState } from "react";
import { streamTopic } from "../api";
import Badge from "../components/Badge";
import Panel from "../components/Panel";

interface TimelineItem {
  eventType: string;
  occurredAtMs: number;
  payload: any;
}

export default function DiscoveryPage() {
  const [events, setEvents] = useState<TimelineItem[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stop = streamTopic("discovery.events", (eventType, data) => {
      setEvents((prev) => [...prev, { eventType, occurredAtMs: data.occurred_at_ms, payload: data.payload }].slice(-500));
    });
    return stop;
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  const latestSnapshot = [...events].reverse().find((e) => e.eventType === "ObservationCaptured");

  return (
    <div className="grid grid-cols-2 gap-4 h-[calc(100vh-8rem)]">
      <Panel title="Live Event Timeline" right={<span className="mono text-xs text-[var(--text-dim)]">{events.length} events</span>}>
        <div className="overflow-y-auto h-[calc(100vh-11rem)] flex flex-col gap-1.5">
          {events.length === 0 && (
            <div className="text-[var(--text-dim)] text-sm">
              Waiting for a discovery run… start one with{" "}
              <code className="mono text-xs">python -m services.discovery_plane.cli</code>
            </div>
          )}
          {events.map((e, i) => (
            <div key={i} className="flex items-start gap-2 text-sm border-b border-[var(--border)] pb-1.5">
              <span className="mono text-xs text-[var(--text-dim)] w-20 shrink-0">{new Date(e.occurredAtMs).toLocaleTimeString()}</span>
              <EventBadge eventType={e.eventType} />
              <span className="mono text-xs text-[var(--text-dim)] truncate">{summarize(e)}</span>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </Panel>

      <Panel title="Current Accessibility Snapshot">
        {latestSnapshot ? (
          <pre className="mono text-xs whitespace-pre-wrap overflow-auto h-[calc(100vh-11rem)] text-[var(--text-dim)]">
            {latestSnapshot.payload.a11y_snapshot}
          </pre>
        ) : (
          <div className="text-[var(--text-dim)] text-sm">No snapshot captured yet.</div>
        )}
      </Panel>
    </div>
  );
}

function EventBadge({ eventType }: { eventType: string }) {
  const kindByEvent: Record<string, string> = {
    RunSucceeded: "SUCCEEDED", RunFailed: "FAILED", ActionBlocked: "HARD_FAILURE",
  };
  const label = kindByEvent[eventType] ?? (eventType.includes("Fail") ? "FAILED" : eventType);
  return <Badge label={label} />;
}

function summarize(e: TimelineItem): string {
  const p = e.payload ?? {};
  switch (e.eventType) {
    case "ActionDecided":
      return `${p.action_type} — ${p.target_description}`;
    case "ActionExecuted":
      return `via ${p.locator_used ?? "(none)"} → ${p.outcome}`;
    case "StepSucceeded":
      return `step ${p.step_index}`;
    case "StepFailed":
      return p.reason ?? "";
    case "RunSucceeded":
      return JSON.stringify(p.outputs ?? {});
    case "RunFailed":
      return p.reason ?? "";
    default:
      return JSON.stringify(p).slice(0, 120);
  }
}
