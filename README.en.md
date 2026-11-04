# Research Claim Literature Verification Agent

English | [简体中文](README.md)

Checks whether verifiable claims in research text are supported by literature. It extracts claims, plans searches, organizes evidence, and produces qualified judgments with citations.

## Capabilities

- Extracts individually verifiable claims from text or uploaded material.
- Retrieves literature per claim and distinguishes supporting, conflicting, contextual, and uncertain evidence.
- Produces judgments, limitations, revision suggestions, and citation mappings, with task progress and history.

## Code and setup

The verification flow is in `源码/backend/app/pipeline/`, configuration in `源码/backend/app/core/`, the main UI in `源码/frontend/web/`, and a static demo in `源码/frontend/web_demo/`. The backend entry is `源码/backend/app/main.py`. See `源码/backend/app/core/config.py` and `源码/backend/app/pipeline/workflow_config.py` for configuration.

Install the backend requirements and frontend dependencies from `源码/frontend/web/package.json`. You need Python, Node.js, MongoDB, and your own model and literature search services.

## Configuration

Supply search, model, and database settings through environment variables using `.env.example` under `源码/` as a guide. Certificate helper scripts use `NSTL_PFX_PASSWORD`. Loopback addresses and `example.invalid` are placeholders.

## Verification and limits

The two frontend report-data files contain synthetic demo records, not real literature or scientific judgments. Historical QA scenarios that relied on real replay fixtures need their own data. Real literature services, models, deployment, and full UI interaction were not tested in the 2026-11-04 public-code review.

See the [publication notes](仓库发布说明.md) for included files. Local archives are excluded.
