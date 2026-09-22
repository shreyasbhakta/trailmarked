import { useEffect, useState } from "react";
import {
  getCapabilityDetail, getCircuitBreaker,
  invokeCapability, listCapabilities, getRunStatus,
} from "../api";
import type { CapabilitySummary, CircuitBreakerState, ReplayStatus } from "../api";
import Badge from "../components/Badge";
import Panel from "../components/Panel";

export default function ReplayPage() {
  const [capabilities, setCapabilities] = useState<CapabilitySummary[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [tenantId, setTenantId] = useState("default");
  const [inputParams, setInputParams] = useState<{ name: string; type: string }[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<ReplayStatus | null>(null);
  const [breaker, setBreaker] = useState<CircuitBreakerState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCapabilities().then((d) => {
      setCapabilities(d.capabilities);
      if (d.capabilities[0]) setSelected(d.capabilities[0].capabilityId);
    });
  }, []);

  useEffect(() => {
    if (!selected) return;
    getCapabilityDetail(selected).then((d) => {
      const artifact = JSON.parse(d.capability?.artifactJson ?? "{}");
      setInputParams(artifact.input_params ?? []);
      setValues({});
    });
    getCircuitBreaker(tenantId, selected).then(setBreaker).catch(() => setBreaker(null));
  }, [selected, tenantId]);

  useEffect(() => {
    if (!runId || !selected) return;
    setStatus(null);
    const interval = setInterval(async () => {
      try {
        const s = await getRunStatus(selected, runId);
        setStatus(s);
        if (s.outcome !== "PENDING") clearInterval(interval);
      } catch {
        /* not ready yet */
      }
    }, 500);
    return () => clearInterval(interval);
  }, [runId, selected]);

  async function submit() {
    setError(null);
    setStatus(null);
    try {
      const ack = await invokeCapability(selected, tenantId, values);
      setRunId(ack.runId);
    } catch (e) {
      setError(String(e));
    }
    getCircuitBreaker(tenantId, selected).then(setBreaker).catch(() => {});
  }

  return (
    <div className="grid grid-cols-2 gap-4">
      <Panel title="Invoke Capability">
        <div className="flex flex-col gap-3">
          <label className="text-sm">
            <div className="text-xs text-[var(--text-dim)] mb-1">Capability</div>
            <select
              className="w-full bg-[var(--bg-panel-2)] border border-[var(--border)] rounded px-2 py-1.5 mono text-sm"
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              {capabilities.map((c) => (
                <option key={c.capabilityId} value={c.capabilityId}>
                  {c.capabilityId} (v{c.latestVersion})
                </option>
              ))}
            </select>
          </label>

          <label className="text-sm">
            <div className="text-xs text-[var(--text-dim)] mb-1">Tenant</div>
            <select
              className="w-full bg-[var(--bg-panel-2)] border border-[var(--border)] rounded px-2 py-1.5 mono text-sm"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
            >
              <option value="default">default</option>
              <option value="overlay_demo">overlay_demo</option>
            </select>
          </label>

          {inputParams.map((p) => (
            <label key={p.name} className="text-sm">
              <div className="text-xs text-[var(--text-dim)] mb-1">
                {p.name} <span className="opacity-60">({p.type})</span>
              </div>
              <input
                className="w-full bg-[var(--bg-panel-2)] border border-[var(--border)] rounded px-2 py-1.5 mono text-sm"
                value={values[p.name] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [p.name]: e.target.value }))}
              />
            </label>
          ))}

          <button
            onClick={submit}
            disabled={!selected}
            className="mt-1 bg-[var(--accent)] text-white rounded px-3 py-1.5 text-sm font-medium disabled:opacity-40"
          >
            Submit Replay
          </button>
          {error && <div className="text-[var(--danger)] text-sm">{error}</div>}
        </div>
      </Panel>

      <div className="flex flex-col gap-4">
        <Panel title="Circuit Breaker" right={breaker && <Badge label={breaker.state} />}>
          {breaker ? (
            <div className="text-sm mono text-[var(--text-dim)]">
              consecutive_failures={breaker.consecutive_failures}
              {breaker.state === "OPEN" && <> · cooldown until {new Date(breaker.cooldown_until_epoch_ms).toLocaleTimeString()}</>}
            </div>
          ) : (
            <div className="text-[var(--text-dim)] text-sm">—</div>
          )}
        </Panel>

        <Panel title="Outcome">
          {!runId && <div className="text-[var(--text-dim)] text-sm">No run submitted yet.</div>}
          {runId && !status && <div className="text-[var(--text-dim)] text-sm">Running…</div>}
          {status && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <Badge label={status.outcome} />
                <span className="mono text-xs text-[var(--text-dim)]">{status.run_id}</span>
              </div>
              {status.retry_count > 0 && <div className="text-xs text-[var(--warning)]">retries: {status.retry_count}</div>}
              {status.outcome === "HARD_FAILURE" && (
                <div className="text-xs text-[var(--danger)]">
                  failed at step {status.failed_step_id} · dead-lettered as {status.dead_letter_event_id}
                </div>
              )}
              <pre className="mono text-xs bg-[var(--bg-panel-2)] rounded p-2 overflow-auto">{JSON.stringify(status.outputs, null, 2)}</pre>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
