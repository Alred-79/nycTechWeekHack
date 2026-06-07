# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

Fresh `uv`-managed Python scaffold — `main.py` is a hello-world placeholder and `README.md` is empty. There is no real architecture yet; it is the starting point for the **M-AGENTS hackathon** (NYC Tech Week / a16z, June 7 2026). The hackathon rules below are the binding constraints on whatever gets built here.

## Toolchain

- Python **3.14** (pinned in `.python-version`), dependency + venv management via **`uv`** (v0.9+).
- `uv run main.py` — run the entrypoint.
- `uv add <pkg>` — add a dependency (writes to `pyproject.toml`); `uv sync` — install from lockfile.
- `uv run python -m pytest` / `uv run pytest <file>::<test>` — run tests / a single test (no test framework added yet; add `pytest` via `uv add --dev pytest` before relying on this).
- No lint/format tooling configured yet; `ruff` is the conventional choice for a `uv` project (`uv add --dev ruff`, then `uv run ruff check` / `ruff format`).

## Hackathon constraints (these dictate architecture)

The deliverable is a **multi-agent pipeline turned end-user product** for one of two tracks (Data Rescue: clean corrupted manufacturer data; or Fraud Watch: detect coordinated fraud). The non-negotiable rules:

- **≥4 agents with genuine handoffs** — not a single LLM in a loop. The canonical pipeline is Find → Rank → Act → Explain (Agents 1–4).
- **Cognee is the mandatory memory layer** — every agent reads from and writes to it; Agent N+1 must demonstrably use Agent N's findings via Cognee.
- **Every agent decision must surface its reasoning** — "the model said so" is a failing answer. Log/expose the rationale per decision.
- **Agent 4 produces a human-readable narrative that is downloadable from the product UI.**
- A one-page **Product Brief (Step 0)** is written before coding and is judged against; build to its stated success metrics.
- **Bring-your-own API key** (OpenAI, Anthropic, or Groq) — none provided. Keep keys out of the repo.
- Other required-but-non-code deliverables: Trupeer demo video, Geodo web research, Devpost submission by **5:00 PM (hard deadline)**.

When proposing structure, organize around the four agents and the Cognee handoff between them, and make the per-decision reasoning a first-class output (not an afterthought).
