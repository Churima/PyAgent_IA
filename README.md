# 🤖 PyAgent_IA: Agente de Code Review & Resolução de Conflitos de Merge

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0.0-green.svg)](https://flask.palletsprojects.com/)
[![Bitbucket](https://img.shields.io/badge/Bitbucket-API-blue.svg)](https://developer.atlassian.com/cloud/bitbucket/)

Este repositório contém um **Agente Inteligente** síncrono e *stateless* desenvolvido para otimizar o fluxo de integração contínua (CI) em ambientes ágeis. O sistema intercepta eventos de Pull Requests do Bitbucket Cloud via Webhooks, analisa alterações semânticas, gera revisões de código (*code review*) e realiza a **resolução ativa e automatizada de conflitos de merge** utilizando Modelos de Linguagem de Grande Escala (LLMs).

---

## 🚀 Principais Funcionalidades

*   **Integração Automatizada via Webhooks:** Captura automática de eventos de criação ou atualização de Pull Requests no Bitbucket Cloud.
*   **Recuperação de Contexto Ampliado:** O agente analisa o arquivo completo modificado e não apenas as linhas do *diff*, mitigando falsos positivos e compreendendo melhor a estrutura semântica do código.
*   **Resolução Ativa de Conflitos:** Identifica marcadores de conflito, efetua o merge lógico utilizando inteligência artificial, realiza o commit de resolução com histórico de múltiplos pais e atualiza a branch de origem automaticamente.
*   **Revisões de Código Inline:** Publicação de comentários técnicos e sugestões de melhoria (Clean Code e boas práticas) diretamente nas linhas correspondentes do arquivo na interface do Bitbucket.
*   **Arquitetura Extensível (Padrão Strategy):** Permite o intercâmbio dinâmico em tempo de execução entre provedores de IA (como Google Gemini e Anthropic Claude) via variáveis de ambiente.

---

## 🛠️ Tecnologias e Frameworks

*   **Linguagem:** Python 3.10+
*   **Framework Web:** Flask (Microsserviço de baixo esforço e alta performance)
*   **Modelos de IA Homologados:** Google Gemini Flash Lite & Claude Sonnet
*   **Integração:** Bitbucket REST API & Ngrok (Túnel seguro para testes de Webhooks locais)

---

## 📐 Arquitetura do Sistema

O fluxo de processamento funciona de maneira síncrona e estruturada seguindo o fluxo abaixo:

1. **Gatilho (PR/Push):** O Bitbucket Cloud dispara uma notificação para o endpoint `/webhook/bitbucket` do microsserviço.
2. **Orquestração:** O módulo principal consome as APIs do Bitbucket para extrair o *diff*, metadados dos commits e arquivos originais.
3. **Decisão do Agente (Strategy):** O prompt estruturado é enviado à LLM configurada para identificar se há conflito de merge ou necessidade de revisão de qualidade.
4. **Execução:** 
    *   *Se houver conflito:* O GitWorker resolve o código, gera uma nova árvore de commit e envia o código limpo ao Bitbucket.
    *   *Se não houver conflito:* O agente publica comentários em linha (*inline*) pontuando oportunidades de refatoração no Pull Request.

---

## 📊 Resultados e Performance (Estudo Comparativo)

Durante o desenvolvimento do projeto, os agentes foram validados em **20 cenários experimentais** complexos, divididos em categorias de conflitos textuais, semânticos, padrões de código e inconsistências de contexto.

| Métrica Avaliada | Google Gemini Flash Lite | Claude Sonnet |
| :--- | :---: | :---: |
| **Precisão** | 1.00 | 1.00 |
| **Recall (Revocação)** | 1.00 | 0.93 |
| **F1-Score** | 1.00 | 0.96 |
| **Tempo Médio de Resposta** | **6.51 segundos** | 16.22 segundos |
| **Nota Média de Qualidade** | **4.21 / 5.00** | 4.00 / 5.00 |
| **Ocorrências de Alucinação** | 2 | 3 |

*   **Google Gemini Flash Lite:** Destacou-se pelo excelente equilíbrio entre velocidade e objetividade, apresentando baixíssima latência operacional e alta aderência ao escopo do commit.
*   **Claude Sonnet:** Demonstrou profundidade analítica superior em padrões estruturais complexos de código, embora com maior variabilidade de latência.

---

## ⚙️ Configuração e Execução

### 1. Requisitos Prévios
Certifique-se de possuir o Python 3.10+ instalado e as chaves de acesso (API Keys) dos provedores configuradas.

### 2. Instalação das Dependências
```bash
pip install -r requirements.txt
