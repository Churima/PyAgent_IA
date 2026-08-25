# 🤖 PyAgent_IA: Code Review Agent & Automated Merge Conflict Resolver

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0.0-green.svg)](https://flask.palletsprojects.com/)
[![Bitbucket](https://img.shields.io/badge/Bitbucket-API-blue.svg)](https://developer.atlassian.com/cloud/bitbucket/)

This repository contains a synchronous, stateless **Intelligent Agent** designed to optimize continuous integration (CI) workflows in agile environments. The system intercepts Bitbucket Cloud Pull Request events via Webhooks, analyzes semantic changes, generates code reviews, and performs active, automated resolution of merge conflicts using Large Language Models (LLMs).

---

## 🚀 Key Features

*   **Automated Webhook Integration:** Automatically captures Pull Request creation and update events on Bitbucket Cloud.
*   **Extended Context Retrieval:** The agent analyzes the entire modified file rather than just the raw *diff* lines, reducing false positives and improving semantic code comprehension.
*   **Active Conflict Resolution:** Automatically identifies conflict markers, resolves logical merges using AI, creates a resolution commit with a multi-parent history, and updates the source branch without manual intervention.
*   **Inline Code Reviews:** Publishes technical comments and Clean Code suggestions directly onto the corresponding code lines within the Bitbucket PR interface.
*   **Extensible Architecture (Strategy Pattern):** Supports dynamic, runtime switching between AI providers (such as Google Gemini and Anthropic Claude) via environment variables.

---

## 🛠️ Tech Stack

*   **Language:** Python 3.10+
*   **Web Framework:** Flask (Lightweight microframework for high performance)
*   **Supported LLMs:** Google Gemini Flash Lite & Claude Sonnet
*   **Integrations:** Bitbucket REST API & Ngrok (Secure tunneling for local webhook testing)

---

## 📐 System Architecture

The stateless microservice operates synchronously following this workflow:

1. **Trigger (PR/Push):** Bitbucket Cloud sends a payload notification to the `/webhook/bitbucket` endpoint.
2. **Orchestration:** The core orchestrator calls the Bitbucket API to extract the *diff*, commit metadata, and raw original files.
3. **Agent Decision (Strategy):** A structured prompt is sent to the active LLM to determine whether a merge conflict exists or a quality review is needed.
4. **Execution:** 
    *   *If conflicts exist:* The GitWorker resolves the code, creates a merge commit, and pushes the clean code back to Bitbucket.
    *   *If no conflicts exist:* The agent posts inline code review comments highlighting refactoring opportunities in the Pull Request.

---

## 📊 Results and Performance (Comparative Study)

The prototype was validated against **20 complex experimental scenarios** spanning merge conflicts, semantic discrepancies, clean code violations, and context inconsistencies.

| Evaluated Metric | Google Gemini Flash Lite | Claude Sonnet |
| :--- | :---: | :---: |
| **Precision** | 1.00 | 1.00 |
| **Recall** | 1.00 | 0.93 |
| **F1-Score** | 1.00 | 0.96 |
| **Average Response Time** | **6.51 seconds** | 16.22 seconds |
| **Average Quality Score** | **4.21 / 5.00** | 4.00 / 5.00 |
| **Hallucination Occurrences** | 2 | 3 |

*   **Google Gemini Flash Lite:** Demonstrated an outstanding balance between speed and objectivity, offering very low operational latency and strict adherence to the commit scope.
*   **Claude Sonnet:** Provided superior analytical depth regarding structural code quality, albeit with higher latency variability.

---

## 📦 Distribution: Building the Executable

The agent ships as a **single self-contained `.exe`** that runs from a folder holding its own
configuration and AI context files. No Python installation is required on the target machine.

### Build

Double-click **`build.bat`**, or run it from any shell:

```bat
build.bat
```

Add `-Limpar` to rebuild the build environment from scratch: `build.bat -Limpar`.

> **Use `build.bat`, not `build.ps1` directly.** Windows associates `.ps1` files with Notepad, so
> double-clicking one (or invoking it from `cmd.exe`) opens the editor instead of running anything.
> On top of that, the default `ExecutionPolicy` (`Restricted`) blocks `.ps1` files even inside
> PowerShell. `build.bat` is a one-line wrapper that calls PowerShell with `-ExecutionPolicy Bypass`,
> clearing both obstacles. From an already-open PowerShell session with scripts enabled,
> `.\build.ps1` works too.

The script creates an isolated build virtualenv (`.venv-build`), installs `requirements-build.txt`,
runs PyInstaller against `pyagent.spec`, and assembles `dist\PyAgentIA\` ready to copy to the server.

Building inside an isolated virtualenv is what keeps the binary around 12 MB — building from a
global interpreter drags every installed package into the bundle.

Expected output on success:

```
[1/5] Criando ambiente virtual de build...
[2/5] Instalando dependencias...
[3/5] Limpando artefatos anteriores...
[4/5] Compilando com PyInstaller...
[5/5] Montando a pasta de distribuicao...

Build concluido.
  Executavel: ...\dist\PyAgentIA\PyAgentIA.exe (11,6 MB)
```

### Deployment folder layout

```
PyAgentIA\
├── PyAgentIA.exe                  # the agent
├── config.ini                     # all configuration (replaces .env)
├── ai_context\                    # user-editable AI context
│   ├── exemplos_treinamento.md    # generic calibration examples
│   └── regras_projeto.md          # client-specific rules  <- edit this one
├── logs\
│   ├── pyagent.log                # rotating application log (5 MB x 5)
│   └── resultados_testes.json     # structured per-execution record
└── debug_payloads\                # only when [log] salvar_payloads = true
```

**First run:** if `config.ini` or `ai_context\` are missing, the agent creates them from the
embedded templates, prints what it created, and exits with code `2`. Fill in `config.ini` and run
again.

**Startup validation:** before opening the port, the agent checks every required setting and reports
all problems at once, then exits with code `1`. It also verifies that Git is reachable.

### Requirements on the target machine

| Requirement | Why |
| :--- | :--- |
| **Git** installed and on `PATH` | `GitWorker` performs real clone/merge/commit/push via `subprocess`. Cannot be embedded in the binary. Point `[git] executavel` at a portable Git if it is not on `PATH`. |
| **Inbound port** (default 5000) | Where the webhook listens. |
| **Public URL** (ngrok or reverse proxy) | Bitbucket must be able to reach the endpoint. |

### Running as a service

Double-clicking the `.exe` works for testing. For production, register it as a Windows service with
[NSSM](https://nssm.cc/) so it starts on boot and restarts on failure:

```powershell
nssm install PyAgentIA "C:\PyAgentIA\PyAgentIA.exe"
nssm set PyAgentIA AppDirectory "C:\PyAgentIA"
nssm start PyAgentIA
```

Task Scheduler with an "at system startup" trigger is a valid alternative when installing NSSM is
not an option.

---

## 🔧 Configuration Reference (`config.ini`)

`config.ini` lives **next to the executable** and must be saved as UTF-8. A fully commented template
ships as [`config.ini.example`](config.ini.example).

Resolution order for every setting, strongest first: **system environment variable → `config.ini` →
`.env` → built-in default**. The startup log prints the origin of each value, so a setting that is
not taking effect is easy to trace.

| Section | Key | Notes |
| :--- | :--- | :--- |
| `[ia]` | `ativa` | `gemini`, `claude` or `mock` |
| | `gemini_api_key`, `gemini_modelo` | Model is configurable — no rebuild needed to switch |
| | `claude_api_key`, `claude_modelo` | Same for the Claude backend |
| | `max_tokens` | Raise it for large files; a truncated response is reported explicitly |
| | `temperatura` | Keep at `0.0` for code review |
| | `timeout_segundos`, `tentativas` | Retries apply to transient errors (429/503) with backoff |
| `[bitbucket]` | `email`, `usuario`, `api_token`, `workspace`, `repo_slug` | `usuario` may differ from `email`: it is used to build the Git clone URL |
| `[servidor]` | `porta`, `host`, `threads` | Served by waitress, not the Flask dev server |
| | `token_webhook` | When set, requests must carry the `X-PyAgent-Token` header |
| | `processamento_assincrono` | `true` answers `202` immediately and works in the background, preventing Bitbucket retry duplicates |
| `[contexto]` | `pasta`, `max_caracteres`, `linguagem_predominante` | See below |
| `[revisao]` | `max_sugestoes`, `severidade_minima`, `idioma_comentarios` | Controls comment volume and language |
| | `extensoes_bloqueadas` | Extensions the AI must never auto-resolve (`.dfm`, `.dproj`, ...) |
| `[git]` | `executavel` | Empty uses `git` from `PATH` |
| `[log]` | `pasta`, `nivel`, `salvar_payloads` | `salvar_payloads` is for debugging only |

---

## 🧠 Customizing the Agent (`ai_context\`)

Every `.md` and `.txt` file in the `ai_context\` folder is loaded into the prompt on every review.
This is how the agent learns rules that are specific to a codebase — particularly relevant when the
target system is written in **Delphi** rather than Python.

Files are split by name:

| File name | Role in the prompt |
| :--- | :--- |
| starts with **`regras`** (e.g. `regras_projeto.md`) | **Project rules — highest priority.** When a rule contradicts a generic best practice, the AI follows the rule. |
| any other name (e.g. `exemplos_treinamento.md`) | Calibration examples: reference for depth and output format. |

Files are read fresh whenever their modification time changes — editing a rule does **not** require
restarting the agent. Total context is capped by `[contexto] max_caracteres` (default 60,000).

### Writing `regras_projeto.md`

Start from [`app/ai_context/regras_projeto.example.md`](app/ai_context/regras_projeto.example.md).
Write imperative, verifiable rules and give each one an identifier — the agent cites that identifier
in the PR comment, which makes the suggestion auditable:

```markdown
- REGRA-01: On `uses` clause conflicts, merge both lists and remove duplicates.
- REGRA-02: Never auto-resolve `.dfm` files — flag for human review.
- REGRA-10: Every `.Create` needs a matching `try..finally ... .Free`.

## O que NÃO comentar
- Do not comment on <legacy pattern the team keeps deliberately>.
```

The **"what NOT to comment"** section matters as much as the rules themselves: it stops the agent
from repeating suggestions the team has already evaluated and rejected.

---

## ⚙️ Local Development

### 1. Prerequisites

Python 3.10+ and Git installed.

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure

```bash
python run.py
```

The first run creates `config.ini` and `ai_context/` in the repository root and exits. Fill in
`config.ini` and run again. A `.env` file still works as a fallback for values missing from the INI.

### 4. Expose the webhook

Bitbucket needs a public URL:

```bash
ngrok http 5000
```

Then point the Bitbucket webhook at `https://<ngrok-url>/webhook/bitbucket` and, if
`token_webhook` is set, add the `X-PyAgent-Token` header with the same value.

### Health check

`GET /` returns the active AI, target repository and effective configuration — useful to confirm
which `config.ini` a running instance actually loaded.

---

## 🛡️ Response Validation

What the AI returns is not what reaches the pull request. Between the two there is a validation
layer that:

*   **drops hallucinated file paths** — any suggestion pointing at a file not present in the diff;
*   **snaps line numbers to real diff anchors** — Bitbucket anchors inline comments by destination
    file line, so an unvalidated number lands the comment in the wrong place;
*   **drops low-confidence suggestions** and duplicates, and caps the total by severity;
*   **strips markdown fences of any language** from resolved code before it is committed;
*   **rejects resolutions that still contain Git conflict markers**;
*   **aborts the merge** when the AI did not cover every file Git flagged as conflicted, instead of
    committing a half-resolved tree;
*   **preserves the original line endings** (CRLF in Delphi repositories) so the merge commit diff
    shows only what actually changed.
