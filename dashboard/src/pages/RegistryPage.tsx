import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getCapabilityDetail, listCapabilities } from "../api";
import type { CapabilityDetail, CapabilitySummary } from "../api";
import Badge from "../components/Badge";
import Panel from "../components/Panel";

export default function RegistryPage() {
  const { capabilityId } = useParams();
  if (capabilityId) return <CapabilityDetailView capabilityId={capabilityId} />;
  return <CapabilityListView />;
}

function CapabilityListView() {
  const [capabilities, setCapabilities] = useState<CapabilitySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCapabilities()
      .then((d) => setCapabilities(d.capabilities))
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <Panel title="Capability Registry">
      {error && <div className="text-[var(--danger)] text-sm">{error}</div>}
      {capabilities === null && !error && <div className="text-[var(--text-dim)] text-sm">loading…</div>}
      {capabilities?.length === 0 && (
        <div className="text-[var(--text-dim)] text-sm">
          No capabilities yet. Run a discovery goal to trailmark one (see README).
        </div>
      )}
      <div className="flex flex-col gap-1">
        {capabilities?.map((c) => (
          <Link
            key={c.capabilityId}
            to={`/capabilities/${c.capabilityId}`}
            className="flex items-center justify-between px-3 py-2 rounded hover:bg-[var(--bg-panel-2)] transition-colors"
          >
            <span className="mono text-sm">{c.capabilityId}</span>
            <span className="mono text-xs text-[var(--text-dim)]">v{c.latestVersion}</span>
          </Link>
        ))}
      </div>
    </Panel>
  );
}

function CapabilityDetailView({ capabilityId }: { capabilityId: string }) {
  const [detail, setDetail] = useState<CapabilityDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCapabilityDetail(capabilityId)
      .then((d) => setDetail(d.capability))
      .catch((e) => setError(String(e)));
  }, [capabilityId]);

  if (error) return <div className="text-[var(--danger)] text-sm">{error}</div>;
  if (!detail) return <div className="text-[var(--text-dim)] text-sm">loading…</div>;

  const artifact = JSON.parse(detail.artifactJson || "{}");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <Link to="/" className="text-[var(--text-dim)] text-sm hover:text-white">
          ← Registry
        </Link>
        <h1 className="mono text-lg">{detail.capabilityId}</h1>
        <Badge label={`v${detail.latestVersion}`} />
        {artifact.tenant_scope === "*" ? null : <Badge label={`tenant overlay: ${artifact.tenant_scope}`} />}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Panel title="Version History">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[var(--text-dim)] text-xs">
                <th className="pb-2 pr-4 whitespace-nowrap">Version</th>
                <th className="pb-2 pr-4 whitespace-nowrap">Compatibility</th>
                <th className="pb-2 pr-4 whitespace-nowrap">Discovery Run</th>
                <th className="pb-2 pr-4 whitespace-nowrap">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {detail.versions.map((v) => (
                <tr key={v.version} className="border-t border-[var(--border)]">
                  <td className="py-1.5 pr-4 mono">v{v.version}</td>
                  <td className="py-1.5 pr-4">
                    <Badge label={v.compatibility} />
                  </td>
                  <td className="py-1.5 pr-4 mono text-xs text-[var(--text-dim)]">{v.discoveryRunId}</td>
                  <td className="py-1.5 pr-4">
                    <div className="flex items-center gap-1.5">
                      <Badge label={v.confidence} />
                      <span className="mono text-xs text-[var(--text-dim)]" title={v.lastValidatedAtMs ? new Date(v.lastValidatedAtMs).toISOString() : undefined}>
                        {v.lastValidatedAtMs
                          ? `validated ${new Date(v.lastValidatedAtMs).toLocaleDateString()}`
                          : "never validated"}
                        {v.consecutiveHardFailures > 0 && ` · ${v.consecutiveHardFailures} hard failure${v.consecutiveHardFailures > 1 ? "s" : ""} in a row`}
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="Input / Output Schema">
          <div className="text-xs text-[var(--text-dim)] mb-1">Inputs</div>
          <div className="flex flex-wrap gap-1 mb-3">
            {artifact.input_params?.map((p: any) => (
              <span key={p.name} className="mono text-xs px-2 py-0.5 rounded border border-[var(--border)]">
                {p.name}: {p.type}
              </span>
            ))}
          </div>
          <div className="text-xs text-[var(--text-dim)] mb-1">Outputs</div>
          <div className="flex flex-wrap gap-1 mb-3">
            {artifact.outputs?.map((o: any) => (
              <span key={o.name} className="mono text-xs px-2 py-0.5 rounded border border-[var(--border)]">
                {o.name}: {o.type}
              </span>
            ))}
          </div>
          <div className="text-xs text-[var(--text-dim)] mb-1">Risk Summary</div>
          <Badge label={artifact.risk_summary?.highest_risk_tag ?? "safe"} />
          {artifact.risk_summary?.requires_preapproval && (
            <span className="ml-2 text-xs text-[var(--warning)]">requires pre-approval</span>
          )}
        </Panel>
      </div>

      <Panel title="Steps">
        <ol className="flex flex-col gap-1.5">
          {artifact.steps?.map((s: any, i: number) => (
            <li key={s.step_id} className="flex items-center gap-2 text-sm">
              <span className="mono text-xs text-[var(--text-dim)] w-6">{i}</span>
              <span className="mono text-xs px-1.5 py-0.5 rounded bg-[var(--bg-panel-2)]">{s.action_type}</span>
              <Badge label={s.risk_tag} />
              <span className="mono text-xs text-[var(--text-dim)] truncate">
                {s.strategy_chain?.map((strat: any) => `${strat.kind}=${strat.value}`).join(" → ") || "(no locator)"}
              </span>
            </li>
          ))}
        </ol>
      </Panel>

      <Panel title="Recent Runs">
        <div className="flex flex-col gap-2">
          {detail.recentRuns.map((r) => (
            <details key={r.runId} className="border border-[var(--border)] rounded px-3 py-2">
              <summary className="flex items-center gap-3 cursor-pointer">
                <span className="mono text-xs text-[var(--text-dim)]">{r.kind}</span>
                <span className="mono text-xs">{r.runId}</span>
                <Badge label={r.status} />
                <span className="mono text-xs text-[var(--text-dim)] ml-auto">{r.correlationId}</span>
              </summary>
              <ul className="mt-2 flex flex-col gap-0.5">
                {r.timeline.map((e) => (
                  <li key={`${e.topic}-${e.offset}`} className="mono text-xs text-[var(--text-dim)] flex gap-2">
                    <span className="w-40">{new Date(e.occurredAtMs).toISOString()}</span>
                    <span className="text-white">{e.eventType}</span>
                  </li>
                ))}
              </ul>
            </details>
          ))}
          {detail.recentRuns.length === 0 && <div className="text-[var(--text-dim)] text-sm">No runs yet.</div>}
        </div>
      </Panel>
    </div>
  );
}
