---
name: container-operations
description: "Use for Docker or Compose service diagnostics, local rebuilds, container health checks, and safe volume-aware maintenance."
capability: "Use for Docker or Compose service diagnostics, local rebuilds, container health checks, and safe volume-aware maintenance."
side_effect_level: local_write
approval_required: false
requires_tools: "Project-documented tools; see body."
output_schema: "Evidence, changes and verification report."
risk_class: medium
---

# container operations

Read the actual Compose files, profiles, task runners and environment documentation. Verify the project name and target service before running mutations.
Start with status, health and bounded logs. Redact environment and connection credentials. Distinguish host, Windows, WSL and container paths.
Use the narrowest documented rebuild/restart command. Explain state implications before changes affecting persistent data. Never use down -v, volume prune, system prune or destructive database recreation as a routine fix.
Verify health and the affected application path after restart. Report startup readiness separately from application correctness.


Resolve helper paths from this skill directory. Run project commands from the target workspace.
