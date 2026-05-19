# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PyAgent_IA is a Python microservice that performs automated AI-powered code review on Bitbucket pull requests. It receives Bitbucket webhook events, fetches PR diffs and full file contents, sends them to an AI agent (Google Gemini or Anthropic Claude), and posts clean code suggestions as inline PR comments.

The codebase is written in Portuguese (variable names, comments, log messages).

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server (default port 5000)
python -m app.main

# Run with custom port
FLASK_RUN_PORT=8080 python -m app.main
```

No test suite exists. No linter is configured.

## Required Environment Variables

Set these in a `.env` file at the project root:

- `ACTIVE_AI` — which AI backend to use (`gemini`, `claude`, or `mock`; defaults to `mock`)
- `GEMINI_API_KEY` — API key for Google Gemini (required when `ACTIVE_AI=gemini`)
- `CLAUDE_API_KEY` — API key for Anthropic Claude (required when `ACTIVE_AI=claude`)
- `BITBUCKET_EMAIL` — Bitbucket account email for API auth
- `BITBUCKET_API_TOKEN` — Bitbucket app password / API token
- `BITBUCKET_WORKSPACE` — Bitbucket workspace slug
- `BITBUCKET_REPO_SLUG` — target repository slug

## Architecture

**Request flow:** Bitbucket webhook → `app/api/webhook.py` → `app/services/reviewer.py` → AI agent + Bitbucket API → inline PR comments.

**Key layers:**

- **`app/main.py`** — Flask app entry point. Registers the webhook blueprint under `/webhook`.
- **`app/api/webhook.py`** — Single endpoint `POST /webhook/bitbucket`. Extracts PR id, title, source/dest branches from the Bitbucket payload.
- **`app/services/reviewer.py`** — Orchestrator. Fetches the PR diff, downloads full file contents from both branches for context, calls the AI agent, and posts resulting suggestions as inline Bitbucket comments.
- **`app/clients/bitbucket.py`** — `BitbucketClient` wraps Bitbucket REST API 2.0 (diff, file content, comments, commits). Uses email + app-password basic auth.
- **`app/clients/ai/`** — Strategy pattern for AI backends:
  - `base.py` — `BaseAIAgent` ABC defining the `analyze_pr()` contract.
  - `gemini_agent.py` — `GeminiAgent` sends a structured prompt to the Google Generative Language REST API directly (no SDK; uses `requests`). Model: `gemini-3.1-flash-lite`. Parses a JSON response with clean code suggestions (`sugestoes_clean_code` array with `arquivo`, `linha`, `comentario` fields).
  - `claude_agent.py` — `ClaudeAgent` sends a structured prompt to the Anthropic REST API directly (no SDK; uses `requests`). Hardcoded model: `claude-sonnet-4-20250514`. Same response contract as `GeminiAgent`.
  - `mock.py` — `MockAIAgent` returns hardcoded suggestions for local development.

**Adding a new AI backend:** Create a class in `app/clients/ai/` extending `BaseAIAgent`, implement `analyze_pr()`, and add a selection branch in `reviewer.py:obter_agente_ia()`.

**AI response contract:** All AI agents must return a dict with key `sugestoes_clean_code`, a list of `{"arquivo": str, "linha": int, "comentario": str}`.

## Local Development with Ngrok

Bitbucket webhooks require a public URL. Use ngrok to tunnel to the local Flask server, then configure the Bitbucket webhook to point to `https://<ngrok-url>/webhook/bitbucket`.
