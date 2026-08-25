# Plano de Evolução — PyAgent_IA para Produção

> Documento de proposta. Nada foi alterado no código ainda.
> Leia, marque o que aprova no checklist do final e me devolva.

---

## 1. Objetivo

Transformar o PyAgent_IA de protótipo local (Flask dev server + `.env` + exemplos embutidos no
pacote Python) em um **executável distribuível** que roda numa pasta autocontida, configurado por
`config.ini`, com o contexto de treinamento **editável pelo usuário final**, e com prompts
preparados para um sistema majoritariamente **Delphi** (e não Python).

Quatro frentes:

| # | Frente | Por quê |
|---|--------|---------|
| A | Empacotamento `.exe` | Rodar em servidor do cliente sem Python instalado |
| B | Configuração via `config.ini` | Substituir `.env` por algo editável fora do binário |
| C | Contexto de treinamento externo | Regras específicas do cliente / Delphi sem recompilar |
| D | Prompts melhores | Clean code multi-linguagem + mensagens claras ao usuário |

---

## 2. Diagnóstico — o que hoje impede a ida para produção

Levantamento do código atual. Itens marcados 🔴 quebram no `.exe`, 🟡 são risco em produção.

| Item | Local | Problema |
|---|---|---|
| 🔴 Caminho de exemplos por `__file__` | [base.py:12](app/clients/ai/base.py:12) | Sob PyInstaller o `__file__` aponta para pasta temporária extraída; o usuário nunca conseguiria editar o arquivo |
| 🔴 `debug_payloads` por `__file__` | [webhook.py:10](app/api/webhook.py:10) | Escreveria dentro do temp do PyInstaller e se perderia a cada execução |
| 🔴 `app.run(debug=True)` | [main.py:22](app/main.py:22) | Reloader do Flask cria 2 processos — em `.exe` isso vira bug/loop. Servidor dev não é para produção |
| 🔴 `import json_repair` sem dependência | [claude_agent.py:168](app/clients/ai/claude_agent.py:168) | Não está no `requirements.txt`. Hoje o `except` engole a falha; no `.exe` nunca seria empacotado |
| 🟡 `requests.post/get` sem `timeout` | todos os clients | Uma chamada travada segura o worker do Flask indefinidamente |
| 🟡 `app/core/config.py` vazio | [config.py](app/core/config.py) | Arquivo existe mas está vazio — é exatamente o lugar da nova camada de config |
| 🟡 `replace("```python", "")` | [reviewer.py:115](app/services/reviewer.py:115) | Só limpa fence de Python. Em Delphi a IA devolve fence `pascal`/`delphi` e as crases entram no commit |
| 🟡 Prompts duplicados | gemini_agent.py / claude_agent.py | Dois textos quase idênticos que já divergem entre si; toda melhoria precisa ser feita 2x |
| 🟡 Prompts assumem Python | ambos os agentes | Não há uma palavra sobre Delphi, `.dfm`, `try..finally`, `uses` |
| 🟡 `linha` = "numero da linha no diff" | ambos os agentes | O Bitbucket espera a linha **do arquivo de destino** no campo `inline.to`. Comentários podem cair na linha errada silenciosamente |
| 🟡 Sem `generationConfig` no Gemini | [gemini_agent.py:117](app/clients/ai/gemini_agent.py:117) | Sem `responseMimeType: application/json` nem `temperature: 0` — daí a necessidade de limpar crases na mão |
| 🟡 Modelo Claude fixo no código | [claude_agent.py:10](app/clients/ai/claude_agent.py:10) | Trocar modelo exige recompilar o `.exe` |
| 🟡 `max_tokens: 8192` | [claude_agent.py:136](app/clients/ai/claude_agent.py:136) | Arquivo Delphi grande (`.pas` de 3000 linhas) devolvido inteiro estoura o limite → JSON truncado → falha de parse |
| 🟡 Webhook síncrono | [webhook.py:33](app/api/webhook.py:33) | O Bitbucket tem timeout curto e **reenvia** o evento. Claude leva ~16s → risco de processar o mesmo PR 2x |
| 🟡 `google-genai` no requirements | [requirements.txt](requirements.txt) | Não é usado (o Gemini é chamado via `requests`). Só engorda o `.exe` |
| 🟡 Mensagem de auto-fix genérica | [reviewer.py:136](app/services/reviewer.py:136) | "Conflitos resolvidos" não diz **o que** a IA decidiu — o dev não tem como auditar |

> Observação importante: o `.exe` **continua dependendo do `git.exe` instalado na máquina**, porque
> o [GitWorker](app/services/git_worker.py) chama `subprocess.run(["git", ...])`. Isso não tem como
> ser embutido no binário Python. Proponho validar no startup e avisar claramente (Fase 6.4).

---

## 3. Layout final da pasta de deploy

```
PyAgentIA/
├── PyAgentIA.exe                  <- binário único (PyInstaller --onefile)
├── config.ini                     <- toda a configuração (substitui o .env)
├── ai_context/                    <- contexto editável pelo usuário
│   ├── exemplos_treinamento.md    <- exemplos genéricos (vai junto por padrão)
│   └── regras_projeto.md          <- regras específicas do cliente / Delphi
├── logs/
│   ├── resultados_testes.json     <- log estruturado de execuções (já existe)
│   └── pyagent.log                <- log de aplicação rotativo (novo)
└── debug_payloads/                <- só se ligado no config.ini
```

**Primeira execução:** se `config.ini` ou `ai_context/` não existirem ao lado do `.exe`, o programa
os cria a partir dos modelos embutidos, imprime *"Arquivos de configuração criados. Preencha o
config.ini e execute novamente."* e encerra com código de saída 2. Sem isso, o primeiro contato do
usuário com o produto seria um stack trace.

---

## 4. Fases

### Fase 0 — Correções de base (pré-requisito de tudo)

| Arquivo | Mudança |
|---|---|
| `requirements.txt` | `+ json-repair`, `+ waitress`, `+ pyinstaller` (dev), `- google-genai` |
| `app/clients/bitbucket.py` | `timeout=` em todas as 5 chamadas `requests` |
| `app/clients/ai/*.py` | `timeout=` configurável nas chamadas de IA |
| `app/services/reviewer.py` | Trocar o `.replace("```python","")` por um `re.sub` que remove fence de **qualquer** linguagem |

Baixo risco, sem mudança de comportamento visível. Deveria entrar mesmo que o resto seja recusado.

---

### Fase 1 — Camada de configuração (`config.ini`)

**Arquivo:** `app/core/config.py` (hoje vazio)

**Estratégia escolhida:** ler o INI e **injetar os valores em `os.environ`** no startup, mantendo
todos os `os.getenv(...)` espalhados pelo código funcionando sem alteração. É a mudança de menor
risco possível — não preciso tocar em `BitbucketClient`, `GitWorker` nem na assinatura dos agentes.

Ordem de precedência (do mais forte para o mais fraco):

1. Variável de ambiente já definida no sistema (permite sobrescrever em CI/Docker)
2. `config.ini` ao lado do executável
3. `.env` (mantido como fallback, para o desenvolvimento local não quebrar)
4. Valor default embutido

API pública do módulo:

```python
carregar_configuracao()      # chamada única no startup; popula os.environ
validar_configuracao()       # -> list[str] de erros legíveis
garantir_arquivos_iniciais() # cria config.ini e ai_context/ na primeira execução
diretorio_base()             # pasta do .exe (ou raiz do repo em dev)
caminho_recurso(rel)         # arquivo embutido no bundle (PyInstaller _MEIPASS)
```

**Modelo do `config.ini`** (vai também como `config.ini.example` no repositório):

```ini
[ia]
; Backend ativo: gemini | claude | mock
ativa            = gemini
gemini_api_key   =
gemini_modelo    = gemini-3.1-flash-lite
claude_api_key   =
claude_modelo    = claude-sonnet-5
max_tokens       = 16000
temperatura      = 0.0
timeout_segundos = 180

[bitbucket]
email     =
usuario   =
api_token =
workspace =
repo_slug =

[servidor]
host  = 0.0.0.0
porta = 5000
; Token opcional exigido no header X-PyAgent-Token do webhook
token_webhook =

[contexto]
pasta                  = ai_context
max_caracteres         = 60000
linguagem_predominante = delphi

[revisao]
max_sugestoes        = 15
severidade_minima    = BAIXO
idioma_comentarios   = pt-BR
postar_resumo        = true
; Extensões que a IA NUNCA deve resolver sozinha (vão para revisão humana)
extensoes_bloqueadas = .dfm,.dproj,.res,.dpr,.groupproj

[git]
; Deixe vazio para usar o git do PATH, ou aponte para um Git portátil
executavel =

[log]
pasta            = logs
nivel            = INFO
salvar_payloads  = false
```

> Nota sobre `claude_modelo`: hoje está fixo em `claude-sonnet-4-20250514`. Deixando no INI você
> troca de modelo sem recompilar. Sugiro `claude-sonnet-5` como padrão (mais recente), mas
> **confirme custo e disponibilidade na sua conta antes de eu mudar o default** — se preferir,
> mantenho o `sonnet-4` e você só edita o INI quando quiser.

**Risco:** se a máquina tiver uma variável de ambiente antiga com o mesmo nome, ela vence o INI. É
intencional (precedência 1), mas vou logar a origem de cada valor no startup para não virar mistério.

---

### Fase 2 — Resolução de caminhos e primeira execução

| Arquivo | Mudança |
|---|---|
| `run.py` *(novo, raiz)* | Ponto de entrada do PyInstaller: carrega config → valida → cria arquivos ausentes → sobe o servidor |
| `app/core/paths.py` *(novo)* | `diretorio_base()` distinguindo `sys.frozen` (usa `os.path.dirname(sys.executable)`) de execução normal |
| `app/api/webhook.py` | `_salvar_payload` passa a usar `diretorio_base()` e só grava se `salvar_payloads = true` |
| `app/core/logger.py` | `LOG_PATH` derivado de `diretorio_base()/logs` |
| `app/clients/ai/base.py` | `_carregar_exemplos()` reescrito (Fase 3) |
| `app/main.py` | Remove `debug=True`; a subida do servidor migra para `run.py` com **waitress** |

Esqueleto do `run.py`:

```python
import sys
from app.core.config import (
    carregar_configuracao, validar_configuracao, garantir_arquivos_iniciais
)

def main() -> int:
    if garantir_arquivos_iniciais():
        print("Arquivos de configuração criados. Preencha o config.ini e execute novamente.")
        return 2

    carregar_configuracao()

    erros = validar_configuracao()
    if erros:
        print("\n".join(f"  [ERRO] {e}" for e in erros))
        return 1

    from waitress import serve
    from app.main import app
    serve(app, host=..., port=..., threads=4)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

**Por que waitress e não o `app.run` do Flask:** o servidor de desenvolvimento do Flask é
single-threaded por padrão, não trata reconexão e imprime o aviso de "não use em produção". Waitress
é WSGI puro-Python, roda bem em Windows e entra no bundle sem DLL externa.

---

### Fase 3 — Contexto de treinamento externo e customizável

Este é o ponto central do seu pedido: as regras do sistema Delphi do cliente precisam entrar sem
recompilar o executável.

**Comportamento novo do `_carregar_exemplos()`:**

1. Procura a pasta `ai_context/` **ao lado do `.exe`**.
2. Lê **todos** os `.md` e `.txt` da pasta, em ordem alfabética, concatenando com um cabeçalho por
   arquivo (`### Fonte: regras_projeto.md`) para a IA saber a origem de cada bloco.
3. Se a pasta não existir, cai para o `exemplos_treinamento.md` embutido no bundle.
4. Corta em `contexto.max_caracteres` (default 60.000) para não estourar contexto e custo, avisando
   no log quando cortar.
5. **Cacheia em memória com base no mtime** dos arquivos — hoje o arquivo de 791 linhas é lido do
   disco a cada PR.

**Separação de papéis dentro da pasta:**

- `exemplos_treinamento.md` — os 20 exemplos genéricos que já existem (formato cenário → JSON esperado).
- `regras_projeto.md` — **novo arquivo, o mais importante para o cliente**. Regras imperativas, não
  exemplos. Entra no prompt numa seção de prioridade mais alta que os exemplos, com instrução
  explícita: **em caso de divergência, a regra do projeto vence o comportamento padrão da IA**.

Modelo que eu geraria para `regras_projeto.md`:

```markdown
# Regras do Projeto — <Nome do Cliente>

## Contexto do sistema
Linguagem predominante: Delphi (Object Pascal), <versão>. Também há: <SQL, C#, ...>.

## Regras de resolução de conflito
- REGRA-01: Em conflito na cláusula `uses`, unir as duas listas, remover duplicatas, ordem alfabética.
- REGRA-02: Nunca resolver conflito em arquivos `.dfm` — sinalizar para revisão humana.
- REGRA-03: Em conflito em <arquivo específico>, a versão da branch <X> sempre prevalece.

## Regras de clean code
- REGRA-10: Todo objeto criado com `.Create` deve ter `try..finally ... .Free`.
- REGRA-11: SQL sempre parametrizado — nunca concatenar valor de variável na string.
- REGRA-12: Não comentar sobre <padrão legado que o time aceita de propósito>.

## O que NÃO comentar
- <padrões que o time já decidiu manter e não quer ver na revisão>
```

A seção "O que NÃO comentar" resolve na prática o maior incômodo de agente de revisão: repetir a
mesma crítica que o time já rejeitou.

---

### Fase 4 — Prompts (o coração da melhoria de qualidade)

**Arquivo novo:** `app/clients/ai/prompt_builder.py`

Hoje os prompts vivem duplicados em `gemini_agent.py` e `claude_agent.py` e **já divergiram**: o
Gemini recebe os exemplos no meio do prompt do usuário, o Claude recebe no system prompt; o Claude
tem regras de escape de JSON que o Gemini não tem. Centralizar:

```python
def montar_prompt(modo, pr_diff, commit_messages, contexto_arquivos, contexto_extra) -> tuple[str, str]:
    """Devolve (system_prompt, user_prompt). Cada agente só adapta ao formato da sua API."""
```

#### 4.1 Consciência de linguagem (Delphi first)

O builder detecta as linguagens envolvidas **pelas extensões dos arquivos do diff** e injeta um
bloco de regras específico. Bloco Delphi proposto:

```
LINGUAGEM DETECTADA: Delphi / Object Pascal (.pas, .dfm, .dpr)

Convenções desta linguagem que você DEVE respeitar ao avaliar:
- Nomenclatura: tipos com prefixo T (TCliente), campos com F (FNome), argumentos com A (ANome),
  interfaces com I. NÃO sugira snake_case nem camelCase de outras linguagens.
- Gerenciamento de memória é MANUAL: todo Create precisa de try..finally/Free correspondente.
  Vazamento de memória é severidade ALTO, não questão de estilo.
- Blocos `with` prejudicam legibilidade e escondem colisão de escopo — sinalize.
- `try..except` que engole exceção sem log nem re-raise é severidade ALTO.
- SQL concatenado com valores de variável é vulnerabilidade — exija parâmetros.
- Regra de negócio dentro de evento de formulário (OnClick, OnChange) é violação de separação de
  camadas — sinalize como MEDIO.
- Arquivos .dfm são gerados pela IDE: NUNCA proponha refatoração neles e NUNCA resolva conflito
  neles automaticamente.
- NÃO aplique regras idiomáticas de Python (PEP8, list comprehension, type hints) a este código.
```

O último item é o mais importante: sem ele o modelo tende a puxar hábitos de Python para código
Pascal e gerar sugestões sem sentido. Blocos equivalentes, mais curtos, para SQL, C#, JavaScript e
um bloco genérico de fallback.

#### 4.2 Contrato de saída enriquecido (retrocompatível)

Campos novos, todos opcionais na leitura (se a IA não mandar, uso default) — assim nada quebra:

```json
{
  "sugestoes_clean_code": [
    {
      "arquivo": "src/UCliente.pas",
      "linha": 142,
      "severidade": "ALTO",
      "categoria": "vazamento_memoria",
      "titulo": "TStringList criado sem try..finally",
      "comentario": "<texto formatado, ver 4.3>",
      "confianca": "alta"
    }
  ],
  "resumo_geral": "string curta com a avaliação geral do PR"
}
```

E no modo conflito, dois campos que hoje faltam e fazem falta:

```json
{
  "resolucao_conflito": [
    {
      "arquivo": "src/UPedido.pas",
      "codigo_completo": "...",
      "explicacao": "Mantida a validação de valor > 0 da main e adicionada a notificação ao gestor da branch de origem. Nenhuma linha foi descartada.",
      "requer_revisao_humana": false
    }
  ]
}
```

`explicacao` alimenta o comentário do PR (ver 4.4) e `requer_revisao_humana` permite que a IA se
**recuse** a resolver e peça ajuda — hoje ela é obrigada a devolver algo, o que é justamente onde
alucinação em merge fica cara.

#### 4.3 Formato padronizado do comentário (clareza para o usuário)

Instrução no prompt para que **todo** `comentario` siga este molde:

> **🔴 ALTO · Vazamento de memória**
>
> **O que foi encontrado:** `TStringList` criado na linha 142 e liberado apenas no caminho de sucesso.
>
> **Por que é um problema:** Se `CarregarDados` lançar exceção, o objeto nunca é liberado — o
> vazamento se acumula a cada chamada e derruba o serviço em execuções longas.
>
> **Como corrigir:**
> ```pascal
> Lista := TStringList.Create;
> try
>   CarregarDados(Lista);
> finally
>   Lista.Free;
> end;
> ```
>
> _Regra aplicada: REGRA-10 (regras_projeto.md)_

Quatro decisões aqui, todas para responder à sua preocupação de "a mensagem vai ficar clara?":

- **Severidade com emoji e rótulo no início** — o dev bate o olho e sabe se é bloqueante.
- **"Por que é um problema" separado do "o que"** — é o que transforma crítica em aprendizado; sem
  isso o dev discute a sugestão em vez de aplicá-la.
- **Código pronto para copiar**, na linguagem correta do arquivo.
- **Citação da regra** quando a sugestão veio do `regras_projeto.md` — dá autoridade e rastreabilidade.

#### 4.4 Comentário de resumo no PR

Antes dos comentários inline, postar um comentário geral:

```
## 🤖 Revisão automática — PyAgent IA

**3 pontos encontrados** · 🔴 1 ALTO · 🟡 2 MÉDIO · Nenhum bloqueador

| Arquivo | Linha | Severidade | Ponto |
|---|---|---|---|
| UCliente.pas | 142 | 🔴 ALTO | TStringList sem try..finally |
| UPedido.pas | 88 | 🟡 MÉDIO | Regra de negócio em evento OnClick |

_Agente: gemini · 6.4s · Contexto: exemplos_treinamento.md + regras_projeto.md_
```

E no modo conflito, substituir a mensagem genérica atual por uma que **explica cada decisão**:

```
## 🤖 Conflito resolvido automaticamente

**src/UPedido.pas** — Mantida a validação `Valor > 0` da main e adicionada a notificação ao gestor
vinda da branch de origem. Nenhuma linha foi descartada.

**src/UCliente.dfm** — ⚠️ NÃO resolvido automaticamente (arquivo de formulário). Requer merge manual.

_Commit de merge real criado. A tag CONFLICTED deve desaparecer._
```

#### 4.5 Controle de ruído e alucinação

| Regra | Onde é aplicada |
|---|---|
| Só comentar linhas que aparecem no diff (o contexto serve para entender, não para caçar) | prompt |
| Máximo `revisao.max_sugestoes` itens, priorizando maior severidade | prompt + corte no código |
| Se `confianca` não for alta, omitir | prompt |
| Nunca inventar caminho de arquivo — validar contra a lista de arquivos do diff | **código** (descarta o que não bate) |
| Se o código está bom, devolver lista vazia (já existe, será reforçado) | prompt |

O descarte por caminho inválido feito no código é a proteção mais efetiva, porque não depende do
modelo obedecer.

#### 4.6 Ajustes específicos por provedor

**Gemini** — adicionar `generationConfig`:

```python
"generationConfig": {
    "temperature": 0.0,
    "responseMimeType": "application/json",
    "maxOutputTokens": <config>,
}
```

Com `responseMimeType` a API já garante JSON válido e a limpeza manual de crases vira só rede de
segurança. Isso deve derrubar boa parte das falhas de parse.

**Claude** — `max_tokens` e modelo vindos do INI, `temperature: 0.0`, e **prefill do assistant** com
`{` para forçar início de JSON:

```python
"messages": [
    {"role": "user", "content": user_message},
    {"role": "assistant", "content": "{"},
]
```

Além disso, tratar `stop_reason == "max_tokens"` explicitamente: hoje o truncamento cai no
`json.JSONDecodeError` e vira um genérico "falha de parse", sem ninguém saber a causa real. Log
claro + comentário no PR avisando que o arquivo é grande demais para resolução automática.

---

### Fase 5 — Precisão da linha do comentário inline

Problema real e silencioso: o prompt pede *"linha: numero da linha no diff"*, mas
[bitbucket.py:42](app/clients/bitbucket.py:42) manda esse número em `inline.to`, que o Bitbucket
interpreta como **linha do arquivo de destino**. Quando o diff tem múltiplos hunks os números
divergem e o comentário aparece no lugar errado.

Proposta:

1. Parser dos cabeçalhos de hunk (`@@ -a,b +c,d @@`) → conjunto de linhas válidas por arquivo.
2. Passar essas linhas para o prompt: *"Use apenas números desta lista no campo linha"*.
3. Validar a resposta: linha fora da lista → encaixar na linha válida mais próxima; se não houver
   nenhuma próxima, postar como comentário geral em vez de inline — hoje o comentário simplesmente
   se perde ou cai errado.

Função nova em `app/services/diff_utils.py`.

---

### Fase 6 — Empacotamento `.exe`

#### 6.1 Ferramenta e modo

**PyInstaller**, modo `--onefile`. Justificativa: você quer o executável numa pasta com os arquivos
de config ao lado — `--onedir` criaria um `_internal/` cheio de DLLs poluindo essa pasta. O custo do
`--onefile` é 2-4s a mais no start (descompactação), irrelevante para um serviço que sobe uma vez e
fica no ar.

#### 6.2 Arquivos novos

**`pyagent.spec`:**

```python
a = Analysis(
    ['run.py'],
    datas=[
        ('app/ai_context/exemplos_treinamento.md', 'ai_context'),
        ('config.ini.example', '.'),
    ],
    hiddenimports=['waitress', 'json_repair'],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pytest'],
)
exe = EXE(..., name='PyAgentIA', console=True, icon='assets/icone.ico')
```

`excludes` mantém o binário enxuto (estimativa: 12-18 MB). `hiddenimports` porque waitress e
json_repair são importados de forma que o analisador estático do PyInstaller pode não detectar.

**`build.ps1`:**

```powershell
python -m venv .venv-build
.\.venv-build\Scripts\pip install -r requirements.txt pyinstaller
.\.venv-build\Scripts\pyinstaller pyagent.spec --clean --noconfirm
# monta dist/PyAgentIA/ com exe + config.ini.example + ai_context/
```

Build numa venv limpa é o que evita o `.exe` de 300 MB por arrastar pacotes globais.

#### 6.3 Validação de startup (falhar cedo e com mensagem legível)

Antes de abrir a porta, checar e listar **todos** os problemas de uma vez:

```
[ERRO] config.ini: [bitbucket] api_token está vazio
[ERRO] config.ini: [ia] ativa = gemini mas gemini_api_key está vazio
[ERRO] git.exe não encontrado no PATH — o GitWorker não conseguirá resolver conflitos
[AVISO] ai_context/regras_projeto.md não encontrado — usando apenas exemplos genéricos
```

Sai com código != 0. Muito melhor que descobrir no primeiro PR real do cliente.

#### 6.4 Dependência de Git — a ressalva honesta

O `.exe` **não elimina a necessidade do Git instalado na máquina**. O `GitWorker` faz clone, merge,
commit e push via `subprocess`. Opções:

- **(a) Exigir Git no servidor** *(recomendado)* — documentar como pré-requisito e validar no startup.
- **(b) Embutir Git portátil** — copiar o MinGit (~45 MB) para a pasta e apontar o `subprocess` para
  ele via `[git] executavel`. Funciona, custa tamanho.
- **(c) Reescrever com `pygit2`/`dulwich`** — elimina a dependência, mas é reescrita grande do
  GitWorker e de todo o tratamento de conflito. Não recomendo agora.

**Preciso da sua decisão aqui.** Meu voto: **(a)**, já com o campo `[git] executavel` previsto no
INI para quem quiser apontar um Git portátil depois, sem mudar código.

#### 6.5 Como deixar rodando

- **Console** — duplo clique, janela aberta. Bom para teste.
- **Serviço do Windows via NSSM** *(recomendado para produção)* — sobe no boot, reinicia se cair,
  redireciona stdout para arquivo. Documento o passo a passo no `DEPLOY.md`.
- **Agendador de Tarefas** — alternativa sem instalar NSSM, com gatilho "ao iniciar o sistema".

#### 6.6 Riscos conhecidos do empacotamento

| Risco | Mitigação |
|---|---|
| Antivírus marca `.exe` do PyInstaller como suspeito (falso positivo comum) | Documentar exceção no Defender; se o cliente exigir, assinatura digital |
| Emojis nos logs quebram no console CP-1252 do Windows | Forçar UTF-8 no stdout dentro do `run.py` |
| Segredos em texto plano no `config.ini` | Restringir ACL da pasta e documentar. Cofre de segredos fica para depois, se você quiser |
| Firewall bloqueia a porta 5000 | Documentar a regra de entrada necessária |

---

### Fase 7 — Robustez em produção *(recomendado, mas separável)*

Marquei como fase própria porque muda comportamento e você pode querer aprovar depois.

1. **Webhook assíncrono.** Responder `202 Accepted` na hora e processar em thread de fundo. Hoje o
   Bitbucket espera 6-16s pela resposta; se estourar o timeout dele, o evento é **reenviado** e o PR
   é processado duas vezes — dois conjuntos de comentários, duas tentativas de merge.
2. **Lock por PR.** Um `set` de PRs em processamento; evento duplicado do mesmo PR é descartado.
   Complementa o circuit breaker de commit da IA que já existe em [reviewer.py:45](app/services/reviewer.py:45).
3. **Token no webhook.** Header `X-PyAgent-Token` comparado com `[servidor] token_webhook`. Hoje o
   endpoint é aberto: quem descobrir a URL dispara commits no repositório do cliente.
4. **Log rotativo em arquivo.** Substituir os `print()` por `logging` com `RotatingFileHandler`
   (5 MB × 5 arquivos). Sem isso, num serviço que roda meses, ou você perde o histórico ou enche o disco.
5. **Retry com backoff** nas chamadas de IA para erro 429/503 (2 tentativas).

Se preferir escopo mínimo agora, os itens **1 e 3** são os que eu não deixaria de fora antes de ligar
no repositório real.

---

### Fase 8 — Documentação

| Arquivo | Conteúdo |
|---|---|
| `config.ini.example` | INI comentado da Fase 1 |
| `app/ai_context/regras_projeto.example.md` | Modelo da Fase 3 |
| `DEPLOY.md` *(novo)* | Pré-requisitos, build, instalação como serviço, configuração do webhook, troubleshooting |
| `README.md` | Seção nova de distribuição; todo o conteúdo acadêmico e as métricas existentes ficam |
| `CLAUDE.md` | Atualizar: config via INI, novo entrypoint `run.py`, `prompt_builder.py`, comando de build |

---

## 5. Resumo de impacto por arquivo

| Arquivo | Ação |
|---|---|
| `run.py` | **novo** — entrypoint do exe |
| `pyagent.spec`, `build.ps1` | **novos** — build |
| `config.ini.example` | **novo** |
| `app/core/config.py` | **implementar** (hoje vazio) |
| `app/core/paths.py` | **novo** |
| `app/clients/ai/prompt_builder.py` | **novo** — prompts unificados e multi-linguagem |
| `app/services/diff_utils.py` | **novo** — mapa de linhas válidas |
| `app/clients/ai/base.py` | contexto externo + cache por mtime |
| `app/clients/ai/gemini_agent.py` | usa prompt_builder, `generationConfig`, timeout |
| `app/clients/ai/claude_agent.py` | usa prompt_builder, modelo/tokens do INI, prefill, timeout |
| `app/clients/ai/mock.py` | ajustar ao contrato novo (severidade, resumo) |
| `app/services/reviewer.py` | fence genérico, validação de arquivo/linha, comentário resumo, explicação do conflito |
| `app/clients/bitbucket.py` | timeouts; `post_comment` também para comentário geral |
| `app/api/webhook.py` | caminhos, token, (Fase 7) assíncrono |
| `app/main.py` | remove debug/app.run |
| `app/core/logger.py` | caminho via `diretorio_base()` |
| `app/services/git_worker.py` | `[git] executavel` configurável; extensões bloqueadas |
| `requirements.txt` | +json-repair, +waitress, +pyinstaller; −google-genai |

Nenhuma alteração destrutiva: o `.env` continua funcionando como fallback, então seu ambiente de
desenvolvimento atual não quebra.

---

## 6. Ordem sugerida de execução

```
Fase 0 (correções)  →  Fase 1 (INI)  →  Fase 2 (caminhos)  →  Fase 3 (contexto externo)
                                                                       ↓
Fase 8 (docs)  ←  Fase 6 (exe)  ←  Fase 5 (linhas)  ←  Fase 4 (prompts)
                       ↓
                  Fase 7 (robustez, opcional)
```

- Fases **0-3 e 6** entregam o que você pediu de infraestrutura (exe + ini + md externo).
- Fases **4-5** entregam a melhoria de qualidade dos prompts.
- Fase **7** é o que eu recomendo antes de apontar para o repositório real do cliente.

---

## 7. Decisões que preciso de você

| # | Pergunta | Minha recomendação |
|---|---|---|
| 1 | Git: exigir instalado, embutir MinGit, ou reescrever com biblioteca? | **Exigir instalado**, com campo no INI para apontar um Git portátil depois |
| 2 | `--onefile` ou `--onedir`? | **`--onefile`** — pasta de deploy limpa |
| 3 | Modelo Claude padrão: manter `claude-sonnet-4-20250514` ou subir para `claude-sonnet-5`? | Deixar **configurável no INI**; me diga qual default |
| 4 | Fase 7 (assíncrono + token no webhook) entra agora ou depois? | **Agora** — ao menos o webhook assíncrono e o token |
| 5 | Idioma dos comentários no PR: só pt-BR ou configurável? | **Configurável no INI**, default pt-BR |
| 6 | O `regras_projeto.md` do cliente: você me passa o conteúdo real ou gero só o modelo vazio? | Gero o modelo; você preenche com as regras do sistema Delphi |
| 7 | Trocar os `print()` por `logging` estruturado? | **Sim** — necessário para serviço em produção |

---

## 8. Checklist de aprovação

Marque `[x]` no que aprova e me devolva (ou só me diga os números).

- [x] **Fase 0** — Correções de base (timeouts, json-repair, fence genérico)
- [x] **Fase 1** — `config.ini` com injeção em `os.environ` e fallback para `.env`
- [x] **Fase 2** — Resolução de caminhos + geração automática na primeira execução + waitress
- [x] **Fase 3** — Pasta `ai_context/` externa com `exemplos_treinamento.md` + `regras_projeto.md`
- [x] **Fase 4** — `prompt_builder.py` unificado, bloco Delphi, contrato enriquecido, formato de comentário
- [x] **Fase 5** — Mapa de linhas válidas do diff e validação antes de postar inline
- [x] **Fase 6** — PyInstaller `.spec` + `build.ps1` + validação de startup
- [x] **Fase 7** — Webhook assíncrono, token, lock por PR, log rotativo, retry
- [x] **Fase 8** — `DEPLOY.md`, `config.ini.example`, atualização de README/CLAUDE.md

Respostas às perguntas da seção 7: _______________________________________
