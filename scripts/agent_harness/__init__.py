"""Jev-centric coding-agent harness.

Deterministic policy first, Jev (TypeSafe System One) second: Jev answers the
per-turn questions a coding agent faces — which instruction packs to show,
whether a command may run, which tool fits, whether a subtask can leave the
frontier model, whether a subgoal is a duplicate — as typed answers with
probabilities. See docs/technical/JEV_AGENT_HARNESS.md.

Everything here is fail-safe: without a key, the SDK, or network, the harness
falls back to its deterministic layer and never blocks the agent on Jev.
"""
