const REST_BASE = "/api";

async function restGet<T>(path: string): Promise<T> {
  const res = await fetch(`${REST_BASE}${path}`);
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`);
  return res.json();
}

async function restPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${REST_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function graphql<T>(query: string, variables: Record<string, unknown> = {}): Promise<T> {
  const res = await fetch("/graphql", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, variables }),
  });
  const json = await res.json();
  if (json.errors) throw new Error(json.errors[0].message);
  return json.data;
}

export interface CapabilitySummary {
  capabilityId: string;
  latestVersion: number;
}

export interface CapabilityVersion {
  version: number;
  compatibility: "BACKWARD" | "FORWARD" | "BREAKING";
  discoveryRunId: string;
  compiledAtMs: number;
  lastValidatedAtMs: number | null;
  consecutiveHardFailures: number;
  confidence: "FRESH" | "NEEDS_REVIEW";
}

export interface EventEntry {
  topic: string;
  offset: number;
  eventType: string;
  occurredAtMs: number;
  payloadJson: string;
}

export interface RunSummary {
  runId: string;
  kind: string;
  tenantId: string | null;
  correlationId: string;
  status: string;
  startedAtMs: number;
  timeline: EventEntry[];
}

export interface CapabilityDetail extends CapabilitySummary {
  versions: CapabilityVersion[];
  recentRuns: RunSummary[];
  artifactJson: string;
}

export function listCapabilities() {
  return graphql<{ capabilities: CapabilitySummary[] }>(`{ capabilities { capabilityId latestVersion } }`);
}

export function getCapabilityDetail(capabilityId: string) {
  return graphql<{ capability: CapabilityDetail | null }>(
    `query($id: String!) {
      capability(capabilityId: $id) {
        capabilityId latestVersion artifactJson
        versions { version compatibility discoveryRunId compiledAtMs lastValidatedAtMs consecutiveHardFailures confidence }
        recentRuns(limit: 20) { runId kind tenantId correlationId status startedAtMs timeline { eventType offset occurredAtMs payloadJson } }
      }
    }`,
    { id: capabilityId },
  );
}

export interface InvokeResponse {
  runId: string;
  deduplicated: boolean;
  correlationId: string;
}

export function invokeCapability(capabilityId: string, tenantId: string, inputParams: Record<string, string>, idempotencyKey?: string) {
  return restPost<InvokeResponse>(`/capabilities/${capabilityId}/invoke`, {
    tenant_id: tenantId,
    input_params: inputParams,
    idempotency_key: idempotencyKey,
  });
}

export interface ReplayStatus {
  run_id: string;
  outcome: "PENDING" | "BUSINESS_OUTCOME" | "RECOVERABLE" | "HARD_FAILURE";
  outputs: Record<string, string>;
  retry_count: number;
  failed_step_id: string;
  dead_letter_event_id: string;
}

export function getRunStatus(capabilityId: string, runId: string) {
  return restGet<ReplayStatus>(`/capabilities/${capabilityId}/runs/${runId}`);
}

export interface CircuitBreakerState {
  state: "CLOSED" | "OPEN" | "HALF_OPEN";
  consecutive_failures: number;
  cooldown_until_epoch_ms: number;
}

export function getCircuitBreaker(tenantId: string, capabilityId: string) {
  return restGet<CircuitBreakerState>(`/circuit-breaker/${tenantId}/${capabilityId}`);
}

export interface SagaState {
  saga_id: string;
  run_id: string;
  status: string;
  claimed_by_operator_id: string;
}

export function listEscalations() {
  return restGet<{ sagas: SagaState[] }>(`/escalations`);
}

export function getEscalation(sagaId: string) {
  return restGet<SagaState>(`/escalations/${sagaId}`);
}

export function claimEscalation(sagaId: string, operatorId: string) {
  return restPost(`/escalations/${sagaId}/claim`, { operator_id: operatorId });
}

export function actOnEscalation(sagaId: string, operatorId: string, actionType: string, locator: string, value: string) {
  return restPost(`/escalations/${sagaId}/act`, { operator_id: operatorId, action_type: actionType, locator, value });
}

export function releaseEscalation(sagaId: string, operatorId: string, resumeAgent: boolean) {
  return restPost(`/escalations/${sagaId}/release`, { operator_id: operatorId, resume_agent: resumeAgent });
}

export function streamTopic(topic: string, onEvent: (eventType: string, data: any) => void): () => void {
  const source = new EventSource(`/stream/${topic}`);
  const handler = (e: MessageEvent) => {
    onEvent(e.type, JSON.parse(e.data));
  };
  // sse-starlette sends named events; EventSource dispatches them by name.
  const knownTypes = [
    "ObservationCaptured", "ActionDecided", "ActionExecuted", "ActionBlocked", "StepSucceeded", "StepFailed",
    "RunSucceeded", "RunFailed", "ReplayRequested", "ReplayStepExecuted", "ReplaySucceeded", "ReplayHardFailure",
    "InterventionRequested", "ControlClaimed", "HumanActed", "ControlReturned",
  ];
  for (const t of knownTypes) source.addEventListener(t, handler as EventListener);
  return () => source.close();
}
