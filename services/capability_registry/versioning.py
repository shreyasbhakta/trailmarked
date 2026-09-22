"""Compatibility classification between a newly compiled capability and the
latest version already in the registry — the schema-registry-style rule
that decides whether a new compile auto-bumps or requires explicit
promotion.
"""
from __future__ import annotations

from shared.schemas import Checkpoint, Compatibility, InputParam, OutputSpec


def _param_shape(params: list[InputParam]) -> set[tuple[str, str]]:
    return {(p.name, p.type) for p in params}


def _output_shape(outputs: list[OutputSpec]) -> set[tuple[str, str]]:
    return {(o.name, o.type) for o in outputs}


def _checkpoint_shape(checkpoints: list[Checkpoint]) -> set[tuple[str, str]]:
    return {(c.step_id, c.assertion) for c in checkpoints}


def classify_compatibility(
    previous_input_params: list[InputParam],
    previous_outputs: list[OutputSpec],
    previous_checkpoints: list[Checkpoint],
    new_input_params: list[InputParam],
    new_outputs: list[OutputSpec],
    new_checkpoints: list[Checkpoint],
) -> Compatibility:
    old_inputs, new_inputs = _param_shape(previous_input_params), _param_shape(new_input_params)
    old_outputs, new_outputs_shape = _output_shape(previous_outputs), _output_shape(new_outputs)
    old_checkpoints, new_checkpoints_shape = _checkpoint_shape(previous_checkpoints), _checkpoint_shape(new_checkpoints)

    if old_inputs == new_inputs and old_outputs == new_outputs_shape and old_checkpoints == new_checkpoints_shape:
        return Compatibility.BACKWARD

    # Nothing that previously existed was removed or retyped: every prior
    # input/output/checkpoint is still present under the same name and type,
    # and only additions were made. Old callers and old checkpoint
    # assertions keep working.
    inputs_preserved = old_inputs.issubset(new_inputs)
    outputs_preserved = old_outputs.issubset(new_outputs_shape)
    checkpoints_preserved = old_checkpoints.issubset(new_checkpoints_shape)
    if inputs_preserved and outputs_preserved and checkpoints_preserved:
        return Compatibility.FORWARD

    return Compatibility.BREAKING
