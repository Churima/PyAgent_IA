# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PyAgent_IA is a Python microservice that performs automated AI-powered code review on Bitbucket pull
requests. It receives Bitbucket webhook events, fetches PR diffs and full file contents, sends them
to an AI agent (Google Gemini or Anthropic Claude), and posts clean code suggestions as inline PR
comments. When Git reports a real merge conflict, it delegates resolution to `GitWorker`, which
performs an actual merge commit and pushes it back.

It is distributed as a **single PyInstaller executable** that runs from a folder containing its own
`config.ini` and an editable `ai_context/` directory. The production target is a client codebase
written mostly in **Delphi (Object Pascal)**, not Python — prompts are language-aware and must stay
that way.

The codebase is written in Portuguese (variable names, comments, log messages).

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server (creates config.ini + ai_context/ on first run, then exits with code 2)
python run.py

# Build the distributable executable -> dist/PyAgentIA/
# Use the .bat wrapper: Windows opens .ps1 in Notepad from cmd.exe, and the
# default ExecutionPolicy (Restricted) blocks .ps1 even inside PowerShell.
build.bat
```

Exit codes of `run.py`: `0` normal shutdown · `1` invalid configuration · `2` first run, files just
created.

No test suite is committed. No linter is configured.

## Configuration

Configuration lives in `config.ini` **next to the executable** (repo root in development). The
template is `config.ini.example`.

`app/core/config.py` reads the INI and injects values into `os.environ`, so all the existing
`os.getenv(...)` calls across the codebase keep working unchanged. Resolution order, strongest
first: **system env var → `config.ini` → `.env` → built-in default**. The startup log prints the
origin of every value.

To add a setting: add one entry to `MAPA_CONFIG` in `app/core/config.py` (mapping `(section, option)`
to `(ENV_VAR, default)`), document it in `config.ini.example`, and read it with `os.getenv` where it
is needed.

`validar_configuracao()` returns `(erros, avisos)` and is called by `run.py` before the port opens —
errors abort startup. It also checks that Git is reachable.

## Architecture

**Request flow:** Bitbucket webhook → `app/api/webhook.py` → `app/services/reviewer.py` → AI agent →
validation → inline PR comments (or `GitWorker` merge).

**Entry points:**

- **`run.py`** — the real entry point (and the PyInstaller target). Loads config, validates, creates
  first-run files, then serves the Flask app with **waitress**. Never use `app.run()`.
- **`app/main.py`** — the Flask app object plus the `/` health check. Registers the webhook
  blueprint under `/webhook`.

**Core layers:**

- **`app/core/paths.py`** — `diretorio_base()` (folder of the `.exe`, or repo root in development)
  and `caminho_recurso()` (files bundled inside PyInstaller's `_MEIPASS`). Every path that the user
  must be able to edit goes through `diretorio_base()`; never use `__file__` for those, because
  under PyInstaller it points at a temp directory that is deleted on exit.
- **`app/core/config.py`** — INI layer described above.
- **`app/core/logger.py`** — `configurar_logging()` (console + `RotatingFileHandler`, UTF-8 forced
  for the Windows console) and `registrar_execucao()` (structured per-PR JSON record). Use
  `obter_logger(__name__)`; do not add `print()` calls.
- **`app/api/webhook.py`** — `POST /webhook/bitbucket`. Validates the optional `X-PyAgent-Token`
  header, answers `202` immediately and processes in a background thread (`processamento_assincrono`),
  and keeps an in-flight PR set so a Bitbucket retry does not process the same PR twice.
- **`app/services/reviewer.py`** — orchestrator, and the **validation layer** between the AI and the
  PR. See below.
- **`app/services/diff_utils.py`** — unified-diff parsing: file list, valid line anchors, markdown
  fence removal, content truncation.
- **`app/services/git_worker.py`** — real Git merges in a temp clone. Returns a dict
  (`sucesso`, `motivo`, `aplicados`, `nao_resolvidos`, `ignorados`) and preserves the file's original
  line endings (CRLF matters in Delphi repos). Git's list of unmerged paths is the **only** write
  authorization, checked both ways: the merge is aborted if the AI missed a conflicted file, and any
  file the AI returns that Git did **not** flag is discarded without being written. That second check
  is what keeps the agent from silently "fixing" a semantic conflict — see below.
- **`app/clients/bitbucket.py`** — Bitbucket REST API 2.0 wrapper (diff, file content, comments,
  commits). Email + app-password basic auth. Every call has a timeout.

**AI layer (`app/clients/ai/`):**

- `base.py` — `BaseAIAgent` ABC, plus `carregar_contexto()` which loads the user-editable
  `ai_context/` folder (cached by mtime).
- `prompt_builder.py` — **single source of truth for prompts.** Both agents call `montar_prompt()`.
  Never write prompt text inside an agent: the two agents previously had duplicated prompts that
  drifted apart. Contains the per-language rule blocks (Delphi, SQL, C#, JavaScript, Python,
  generic), the severity scale, the mandatory comment format, and the `responseSchema` definitions.
- `gemini_agent.py` — `GeminiAgent`, the primary backend. Structured output
  (`responseMimeType: application/json` + `responseSchema`), API key in the `x-goog-api-key` header
  (never in the URL), retry with exponential backoff on 429/5xx, and **progressive degradation**: an
  HTTP 400 causes the request to be retried without `responseSchema`, then without
  `systemInstruction`, instead of failing.
- `claude_agent.py` — `ClaudeAgent`. Same contract; assistant prefill with `{` to force JSON. Less
  tuned than the Gemini agent — that work is pending.
- `mock.py` — `MockAIAgent`, returns the full contract using real anchors from the PR.

**Adding a new AI backend:** create a class in `app/clients/ai/` extending `BaseAIAgent`, call
`montar_prompt()` for the prompt, normalize the response into the contract below, and add a branch
in `reviewer.py:obter_agente_ia()`.

## AI response contract

```python
{
  "sugestoes_clean_code": [
    {"arquivo": str, "linha": int, "severidade": "BLOQUEADOR|ALTO|MEDIO|BAIXO",
     "categoria": str, "titulo": str, "comentario": str, "confianca": "alta|media|baixa"}
  ],
  "resolucao_conflito": [
    {"arquivo": str, "codigo_completo": str, "explicacao": str, "requer_revisao_humana": bool}
  ],
  "resumo_geral": str,
  "_erro_parse": bool, "_motivo_erro": str, "_tokens": dict, "_modelo": str, "_truncado": bool,
}
```

Fields other than `arquivo`/`linha`/`comentario` are optional on read — `reviewer.py` supplies
defaults, so an older or sloppier model response does not break the pipeline.

## The validation layer (do not weaken it)

`reviewer.py` deliberately does not trust the model output. `_validar_sugestoes()` and
`_validar_resolucoes()`:

- drop suggestions whose `arquivo` is not in the diff (hallucinated paths);
- snap `linha` to a real diff anchor via `ajustar_linha()` — Bitbucket's `inline.to` is a
  **destination-file** line number, so an unvalidated number silently misplaces the comment;
- drop `confianca: baixa` and duplicates, filter by `severidade_minima`, cap at `max_sugestoes`;
- strip markdown fences of any language before code is committed;
- reject resolutions that still contain Git conflict markers;
- route blocked extensions (`.dfm`, `.dproj`, ...) and `requer_revisao_humana` to a "needs manual
  merge" list reported in the PR comment.

**Scope rule — conflicts are resolved, semantic conflicts are only flagged.** Auto-merge is triggered
by Git, never by the AI: `GitWorker.verificar_conflito()` runs a real `git merge --no-commit`, so only
textual conflicts reach resolution mode. A semantic conflict produces no marker, so the PR goes down
the clean-code path and is reported as a comment with category `inconsistencia_semantica` — nothing
is ever committed for it. The `ignorados` guard in `GitWorker` enforces the same rule from the other
side, and those files are surfaced in the PR comment as "verify manually". Do not relax either half.

There is also a circuit breaker: processing is skipped when the latest commit message on the source
branch contains `🤖 IA Auto-fix`.

## Customization files (`ai_context/`)

Every `.md`/`.txt` in the folder is loaded on each review. Files named `regras*` become **project
rules with maximum priority** in the prompt; everything else becomes calibration examples. Templates
live in `app/ai_context/` and are copied next to the executable on first run. `*.example.md` files
are skipped by the loader.

## Local Development with Ngrok

Bitbucket webhooks require a public URL. Use ngrok to tunnel to the local server, then point the
Bitbucket webhook at `https://<ngrok-url>/webhook/bitbucket`, adding the `X-PyAgent-Token` header
when `token_webhook` is configured.
