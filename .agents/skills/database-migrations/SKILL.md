---
name: database-migrations
description: "Use when creating or reviewing schema migrations, changing deployed tables, or planning a database schema rollout."
capability: "Use when creating or reviewing schema migrations, changing deployed tables, or planning a database schema rollout."
side_effect_level: local_write
approval_required: false
requires_tools: "Project-documented tools; see body."
output_schema: "Evidence, changes and verification report."
risk_class: medium
---

# database migrations

Identify the actual migration framework, naming/order rules, database version, deployment target, and backup policy from the repository.
Treat applied migrations as immutable; add a forward migration unless the project's tooling explicitly permits a different development workflow. Separate required reference data from optional seeds.
Describe lock duration, backfill, compatibility with old/new app versions, constraints, and recovery. Prefer expand/backfill/contract for rolling deployments. Do not assume every engine supports transactional DDL.
Test on disposable representative data and record the applied revision. Production execution requires task authority and verified target identity; a migration file is not authorization to apply it.
Use database-backups for backup validation. Report test results, operational steps and known recovery limits.


Resolve helper paths from this skill directory. Run project commands from the target workspace.
