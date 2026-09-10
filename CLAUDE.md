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
  and keeps an in-flight PR set so a Bitbucket retry does not process the same PR twice. It also
  short-circuits on `reviewer.branch_ignorada()` before starting the thread, so an ignored source
  branch costs no API call, no clone and no thread — it answers `200` with
  `motivo: branch_origem_ignorada`.
- **`app/services/reviewer.py`** — orchestrator, and the **validation layer** between the AI and the
  PR. See below.
- **`app/services/diff_utils.py`** — unified-diff parsing: file list, valid line anchors, markdown
  fence removal, content truncation. Also the token-reduction helpers: `filtrar_diff_por_extensao()`
  (drops `.dfm`/`.dproj` sections — the diff used to be sent whole, with no cap at all),
  `filtrar_diff_por_arquivos()` (per-batch diff), `extrair_janelas()` (windows around each hunk,
  carrying the file's real line numbers) and `estimar_tokens()`.
- **`app/services/simbolos.py`** — symbol map and cross-file reference lookup. Windowing the files
  would otherwise weaken semantic-inconsistency detection: a caller that this PR did *not* touch
  appears in neither the diff nor the window. `montar_mapa_simbolos()` lists each file's
  declarations (2-3% of the source size) and `janelas_de_referencia()` greps the changed
  identifiers across the other files of the PR and returns short excerpts around each use.
- **`app/services/git_worker.py`** — real Git merges in a temp clone. `verificar_conflito()`
  returns `(tem_conflito, arquivos_em_conflito)` — the list matters as much as the flag, because
  only those files need to go to the AI in resolution mode. `resolve_with_merge()` returns a dict
  (`sucesso`, `motivo`, `aplicados`, `nao_resolvidos`, `ignorados`) and preserves the file's original
  line endings (CRLF matters in Delphi repos). Git's list of unmerged paths is the **only** write
  authorization, checked both ways: the merge is aborted if the AI missed a conflicted file, and any
  file the AI returns that Git did **not** flag is discarded without being written. That second check
  is what keeps the agent from silently "fixing" a semantic conflict — see below.
- **`app/clients/bitbucket.py`** — Bitbucket REST API 2.0 wrapper (diff, file content, comments,
  commits). Email + app-password basic auth. Every call has a timeout.

**AI layer (`app/clients/ai/`):**

- `base.py` — `BaseAIAgent` ABC, plus `carregar_contexto(modo, linguagens)` which loads the
  user-editable `ai_context/` folder (cached by mtime) and **filters it by mode**: conflict-
  resolution rules and examples are not sent on a clean-code review, and vice versa. Scope comes
  from `<!-- pyagent: modo=... linguagem=... -->` marker lines (each applies until the next one) or
  from the filename (`exemplos.conflito.md`). Unmarked content still goes to both modes, so an
  older install keeps working. HTML comments are stripped before the prompt is built — maintainer
  notes in these files cost nothing.
- `prompt_builder.py` — **single source of truth for prompts.** Both agents call `montar_prompt()`.
  Never write prompt text inside an agent: the two agents previously had duplicated prompts that
  drifted apart. Contains the per-language rule blocks (Delphi, SQL, C#, JavaScript, Python,
  generic), the severity scale, the mandatory comment format, and the `responseSchema` definitions.
- `gemini_agent.py` — `GeminiAgent`, the primary backend. Structured output
  (`responseMimeType: application/json` + `responseSchema`), API key in the `x-goog-api-key` header
  (never in the URL), retry with exponential backoff on 429/5xx, and **progressive degradation**: an
  HTTP 400 causes the request to be retried without `responseSchema`, then without
  `systemInstruction`, instead of failing.
- `claude_agent.py` — `ClaudeAgent`. Same contract; assistant prefill with `{` to force JSON. The
  system prompt goes as a `cache_control: ephemeral` block (`[ia] usar_cache_prompt`), which pays
  off because batching means several calls share the same system prompt. Still pending here: tool
  use for structured output instead of the prefill.
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

**Source-branch filter.** `[revisao] branches_origem_ignoradas` lists source branches that are never
reviewed — a PR from `version` to `master` is a release promotion whose content was already reviewed
when it entered the source branch. Matching is by `fnmatch` (so `release/*` works), case-insensitive,
and an empty list (the default) ignores nothing. The rule lives in `reviewer.branch_ignorada()` and
is enforced at both the webhook edge and the top of `process_pull_request()`, so calling the service
function directly is covered too.

## Token budget (do not undo this either)

A 10-file PR used to build a ~640k-token prompt and got rejected by the model's limit before the
review even started. Four things keep it down; each one has a config knob, none of them may be
silently reverted:

1. **Clean-code mode never sends whole files.** `_montar_contexto()` fetches only the source-branch
   version and puts *windows around the hunks* in the prompt (`[contexto] margem_linhas`), with the
   real destination-file line numbers shown and changed lines flagged with `>`. The full text stays
   in memory only, for `simbolos.py`. Conflict mode still sends both versions in full — the AI
   returns `codigo_completo` there and anything missing is lost code.
2. **Conflict mode only loads the files Git flagged**, from `verificar_conflito()`.
3. **Blocked extensions are stripped from the diff**, not just from the context.
4. **A PR that still doesn't fit is split into batches** (`[ia] max_tokens_entrada`), one request
   per batch, results merged in `_mesclar_analises()`. A batch that fails no longer costs the whole
   PR its review. The symbol map and cross-file references are built over *all* files and repeated
   in every batch, which is what preserves semantic detection across batch boundaries.

When touching the prompt, check the effect with a large synthetic PR before assuming it is free:
the file content, not the instructions, is what dominates the bill.

## Customization files (`ai_context/`)

Every `.md`/`.txt` in the folder is loaded on each review. Files named `regras*` become **project
rules with maximum priority** in the prompt; everything else becomes calibration examples. Templates
live in `app/ai_context/` and are copied next to the executable on first run. `*.example.md` files
are skipped by the loader.

Content is scoped per mode three ways, weakest to strongest:

1. **Subfolder** — `ai_context/conflito/`, `ai_context/cleancode/delphi/`. The loader walks
   subdirectories; a path segment naming a mode or a language scopes everything under it, and any
   other segment (`conflito/fiscal/`) is just organization. Folders starting with `.` or `_` are
   skipped.
2. **Filename** — `exemplos.conflito.md`, `regras.cleancode.delphi.md` (dot-separated tokens after
   the first).
3. **Marker line inside the file** — `<!-- pyagent: modo=conflito -->`, `modo=cleancode`,
   `modo=ambos`, optionally `linguagem=delphi,sql`. Valid until the next marker in that file.

Unmarked content goes to both modes, so an install predating this keeps working. Any other HTML
comment is dropped before the prompt is built, so notes for whoever maintains the file are free.
`regras*` on the **basename** still decides rules-vs-examples, inside a subfolder too. Sources are
identified by path relative to `ai_context/`, so `conflito/notas.md` and `cleancode/notas.md` do
not collide in the PR summary footer.

**Which to use.** Folders for self-contained, single-mode material. Markers for the two big files
already there: they switch mode five times each, share §1 (system context) between both modes, and
cite each other by rule identifier across mode boundaries — splitting them into folders would force
duplicating the shared section and cutting §8 in half. Do not migrate them without re-reading that
trade-off. Watch for **dangling rule references**: a rule cited from one mode but defined in a block
scoped to the other silently ships without its definition (this happened to REGRA-05 and REGRA-58;
both are now `modo=ambos`).

## Local Development with Ngrok

Bitbucket webhooks require a public URL. Use ngrok to tunnel to the local server, then point the
Bitbucket webhook at `https://<ngrok-url>/webhook/bitbucket`, adding the `X-PyAgent-Token` header
when `token_webhook` is configured.
