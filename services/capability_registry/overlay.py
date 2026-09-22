"""Merges a base CapabilityArtifact with a tenant's locator/param overlay at
resolve time. The base is never mutated per tenant — only the resolved copy
handed back to a caller carries the tenant's overrides.
"""
from __future__ import annotations

from shared.schemas import CapabilityArtifact, TenantOverlay


def resolve(base: CapabilityArtifact, overlay: TenantOverlay | None) -> CapabilityArtifact:
    if overlay is None:
        return base.model_copy(deep=True)

    resolved = base.model_copy(deep=True)
    resolved.tenant_scope = overlay.tenant_id

    for step in resolved.steps:
        if step.step_id in overlay.locator_overrides:
            step.strategy_chain = list(overlay.locator_overrides[step.step_id])
        if step.step_id in overlay.param_overrides:
            step.param_bindings = {**step.param_bindings, **overlay.param_overrides[step.step_id]}

    return resolved
