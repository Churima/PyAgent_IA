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

## ⚙️ Setup and Installation

### 1. Prerequisites
Ensure you have Python 3.10+ installed and the API keys for the respective AI providers ready.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
