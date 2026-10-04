---
type: Technical Reference
title: Open Knowledge Format v0.2 (upstream pointer)
description: Links to the canonical OKF v0.2 specification; local adoption rules live in OKF_ADOPTION.md.
resource: reference/OKF_SPEC_v0.2.md
tags: [docs, okf, reference, governance]
timestamp: 2026-10-04T00:00:00Z
okf_version: 0.2
---

# Open Knowledge Format v0.2 — upstream pointer

This page does **not** duplicate the full spec (it changes upstream). Use it when you need the authoritative OKF v0.2 text or a quick reminder of what v0.2 adds.

## Canonical sources

| Source | URL |
|---|---|
| **Primary repo** | [GoogleCloudPlatform/open-knowledge-format — SPEC.md](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md) |
| **HTML mirror** | [openknowledge.sh/wiki/SPEC.html](https://openknowledge.sh/wiki/SPEC.html) |
| **knowledge-catalog mirror** | [knowledge-catalog/okf/SPEC.md](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) |
| **Overview (trust signals)** | [OKF v0.2 adds trust signals (Google Cloud Blog)](https://cloud.google.com/blog/products/data-analytics/okf-v0-2-adds-trust-signals) |

## v0.2 at a glance (non-normative)

- **Backward compatible** with v0.1 bundles; `type` remains the only required field.
- **Optional trust/lifecycle frontmatter:** `sources`, `generated`, `verified`, `status`, `stale_after`, plus attested-computation concept types for executable, attestable figures.
- **Renames with fallback:** `timestamp` → prefer `generated.at`; body `# Citations` → prefer structured `sources`.
- **Bundle version:** bundle-root `index.md` may declare `okf_version: "0.2"`; this repo also sets `okf_version: 0.2` on concept pages per [OKF_ADOPTION.md](../OKF_ADOPTION.md).

## Local adoption

Repository-specific frontmatter, lint profiles, and folder conventions: [OKF_ADOPTION.md](../OKF_ADOPTION.md) and [WIKI_SCHEMA.md](../WIKI_SCHEMA.md).
