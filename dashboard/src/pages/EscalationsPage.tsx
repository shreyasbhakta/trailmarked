import { useEffect, useState } from "react";
import { actOnEscalation, claimEscalation, listEscalations, releaseEscalation } from "../api";
import type { SagaState } from "../api";
import Badge from "../components/Badge";
import Panel from "../components/Panel";

const OPERATOR_ID = "teller_console_operator";

export default function EscalationsPage() {
  const [sagas, setSagas] = useState<SagaState[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [actionType, setActionType] = useState("click");
  const [locator, setLocator] = useState("");
  const [value, setValue] = useState("");
  const [log, setLog] = useState<string[]>([]);

  async function refresh() {
    const d = await listEscalations();
    setSagas(d.sagas);
  }

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 2000);
    return () => clearInterval(interval);
  }, []);

  const selectedSaga = sagas.find((s) => s.saga_id === selected);

  async function claim() {
    if (!selected) return;
    await claimEscalation(selected, OPERATOR_ID);
    setLog((l) => [...l, `claimed ${selected} as ${OPERATOR_ID}`]);
    refresh();
  }

  async function act() {
    if (!selected) return;
    await actOnEscalation(selected, OPERATOR_ID, actionType, locator, value);
    setLog((l) => [...l, `acted on ${selected}: ${actionType} ${locator} ${value}`]);
  }

  async function release(resumeAgent: boolean) {
    if (!selected) return;
    await releaseEscalation(selected, OPERATOR_ID, resumeAgent);
    setLog((l) => [...l, `released ${selected} (resume_agent=${resumeAgent})`]);
    refresh();
  }

  return (
    <div className="grid grid-cols-2 gap-4">
      <Panel title="Interventions">
        <div className="flex flex-col gap-1">
          {sagas.length === 0 && (
            <div className="text-[var(--text-dim)] text-sm">
              No escalations. One is created automatically when a replay hits HARD_FAILURE.
            </div>
          )}
          {sagas.map((s) => (
            <button
              key={s.saga_id}
              onClick={() => setSelected(s.saga_id)}
              className={`flex items-center justify-between px-3 py-2 rounded text-left ${
                selected === s.saga_id ? "bg-[var(--bg-panel-2)]" : "hover:bg-[var(--bg-panel-2)]"
              }`}
            >
              <span className="mono text-xs">{s.saga_id}</span>
              <Badge label={s.status} />
            </button>
          ))}
        </div>
      </Panel>

      <Panel title="Saga State Machine">
        {!selectedSaga && <div className="text-[var(--text-dim)] text-sm">Select an intervention.</div>}
        {selectedSaga && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-2 mono text-xs">
              {["AGENT_CONTROLLED", "INTERVENTION_REQUESTED", "HUMAN_CONTROLLED", "CONTROL_RETURNED"].map((stage, i) => (
                <span key={stage} className="flex items-center gap-2">
                  <Badge label={stage === selectedSaga.status ? selectedSaga.status : stage} />
                  {i < 3 && <span className="text-[var(--text-dim)]">→</span>}
                </span>
              ))}
            </div>

            <div className="text-sm mono text-[var(--text-dim)]">
              run_id={selectedSaga.run_id}
              {selectedSaga.claimed_by_operator_id && <> · claimed_by={selectedSaga.claimed_by_operator_id}</>}
            </div>

            <div className="flex gap-2">
              <button onClick={claim} className="bg-[var(--accent)] text-white rounded px-3 py-1.5 text-sm">
                Claim
              </button>
              <button onClick={() => release(false)} className="border border-[var(--border)] rounded px-3 py-1.5 text-sm">
                Release (terminate)
              </button>
              <button onClick={() => release(true)} className="border border-[var(--border)] rounded px-3 py-1.5 text-sm">
                Release (resume)
              </button>
            </div>

            <div className="border border-[var(--border)] rounded p-3 flex flex-col gap-2">
              <div className="text-xs text-[var(--text-dim)]">Act on live session</div>
              <div className="flex gap-2">
                <select
                  value={actionType}
                  onChange={(e) => setActionType(e.target.value)}
                  className="bg-[var(--bg-panel-2)] border border-[var(--border)] rounded px-2 py-1 mono text-xs"
                >
                  <option value="click">click</option>
                  <option value="fill">fill</option>
                  <option value="select">select</option>
                </select>
                <input
                  placeholder="locator, e.g. css=#retry-button"
                  value={locator}
                  onChange={(e) => setLocator(e.target.value)}
                  className="flex-1 bg-[var(--bg-panel-2)] border border-[var(--border)] rounded px-2 py-1 mono text-xs"
                />
                <input
                  placeholder="value (fill/select)"
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  className="w-32 bg-[var(--bg-panel-2)] border border-[var(--border)] rounded px-2 py-1 mono text-xs"
                />
                <button onClick={act} className="bg-[var(--accent)] text-white rounded px-3 py-1 text-xs">
                  Act
                </button>
              </div>
            </div>

            <div className="mono text-xs text-[var(--text-dim)] flex flex-col gap-0.5">
              {log.map((l, i) => (
                <div key={i}>{l}</div>
              ))}
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}
