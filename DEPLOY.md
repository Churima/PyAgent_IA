# PyAgent IA — Guia de Instalação e Operação

Guia prático para colocar o agente no ar no servidor. Para a visão geral do projeto, veja o
[README](README.md).

---

## 1. Pré-requisitos no servidor

| Item | Como verificar | Observação |
|---|---|---|
| **Git instalado** | `git --version` no prompt | Obrigatório. O agente clona, mescla e faz push via Git de verdade. Se não estiver no `PATH`, preencha `[git] executavel` no `config.ini` |
| **Porta livre** (padrão 5000) | `netstat -ano \| findstr :5000` | Ajuste `[servidor] porta` se estiver ocupada |
| **URL pública** | ngrok, Cloudflare Tunnel ou proxy reverso | O Bitbucket precisa alcançar o endpoint |
| **Saída HTTPS liberada** | — | Para `api.bitbucket.org`, `bitbucket.org` e a API da IA |

Python **não** é necessário: o executável já traz o interpretador embutido.

---

## 2. Instalação

1. Copie a pasta `PyAgentIA` inteira para o servidor (ex.: `C:\PyAgentIA`).
2. Execute `PyAgentIA.exe` uma vez. Se o `config.ini` ainda não existir, ele será criado e o
   programa encerra pedindo o preenchimento.
3. Abra o `config.ini` e preencha, no mínimo:

```ini
[ia]
ativa          = gemini
gemini_api_key = <sua chave da Google AI Studio>

[bitbucket]
email     = <e-mail da conta Atlassian>
usuario   = <usuário do Bitbucket>
api_token = <app password com permissão de leitura e escrita>
workspace = <slug do workspace>
repo_slug = <slug do repositório>

[servidor]
token_webhook = <uma senha qualquer, longa e aleatória>
```

4. Ajuste `ai_context\regras_projeto.md` com as regras do sistema (veja a seção 5).
5. Execute o `PyAgentIA.exe` novamente. Ele deve exibir:

```
INFO [run] PyAgent IA 2.0 — IA ativa: gemini
INFO [run] Repositório alvo: <workspace>/<repo>
INFO [run] Escutando em http://0.0.0.0:5000  (webhook: POST /webhook/bitbucket)
```

6. Confira no navegador: `http://localhost:5000/` deve devolver um JSON com a configuração ativa.

**Códigos de saída:** `0` encerrado normalmente · `1` configuração inválida (os erros são listados
na tela) · `2` primeira execução, arquivos recém-criados.

---

## 3. Expor para o Bitbucket

```powershell
ngrok http 5000
```

No Bitbucket: **Repository settings → Webhooks → Add webhook**

| Campo | Valor |
|---|---|
| URL | `https://<seu-ngrok>.ngrok-free.app/webhook/bitbucket` |
| Triggers | `Pull request: Created` e `Pull request: Updated` |

Se você preencheu `token_webhook`, adicione o cabeçalho `X-PyAgent-Token` com o mesmo valor.
Requisições sem o cabeçalho correto recebem `401` e são registradas no log — sem o token, qualquer
pessoa que descubra a URL do ngrok consegue disparar commits no repositório.

> A URL gratuita do ngrok muda a cada reinício. Refaça o cadastro do webhook quando isso acontecer,
> ou use um domínio reservado.

---

## 4. Rodar como serviço do Windows

Recomendado para produção — sobe no boot e reinicia sozinho se cair.

```powershell
nssm install PyAgentIA "C:\PyAgentIA\PyAgentIA.exe"
nssm set PyAgentIA AppDirectory "C:\PyAgentIA"
nssm set PyAgentIA AppStdout "C:\PyAgentIA\logs\servico.log"
nssm set PyAgentIA AppStderr "C:\PyAgentIA\logs\servico.log"
nssm start PyAgentIA
```

`AppDirectory` é obrigatório: é ele que faz o agente encontrar o `config.ini` e a pasta `ai_context`.

Alternativa sem NSSM: Agendador de Tarefas, com gatilho "Ao iniciar o computador", ação apontando
para o `.exe` e o campo "Iniciar em" preenchido com a pasta do executável.

---

## 5. Personalizar o agente para o sistema do cliente

Tudo que está em `ai_context\` entra no prompt a cada revisão. Os arquivos são relidos quando mudam
— **não é preciso reiniciar o serviço** após editar uma regra.

| Arquivo | Papel |
|---|---|
| `regras_projeto.md` (ou qualquer nome iniciado por `regras`) | **Regras do projeto, prioridade máxima.** Quando uma regra contraria uma boa prática genérica, a IA segue a regra |
| `exemplos_treinamento.md` | Exemplos de calibração: referência de profundidade e formato |

Escreva regras imperativas e com identificador, porque a IA cita o identificador no comentário do
PR e isso torna a sugestão auditável:

```markdown
- REGRA-01: Em conflito na cláusula `uses`, unir as duas listas e remover duplicatas.
- REGRA-02: Nunca resolver conflito em arquivos `.dfm` — sinalizar para revisão humana.
- REGRA-10: Todo `.Create` precisa de `try..finally ... .Free` correspondente.

## O que NÃO comentar
- Não comentar sobre <padrão legado que o time mantém de propósito>.
```

A seção **"O que NÃO comentar"** é tão importante quanto as regras: é ela que impede o agente de
repetir sugestões que o time já avaliou e rejeitou.

---

## 6. Operação diária

| Onde olhar | O quê |
|---|---|
| `logs\pyagent.log` | Log da aplicação, rotativo (5 MB × 5 arquivos) |
| `logs\resultados_testes.json` | Uma entrada por PR processado: agente, modelo, tempo, tokens, sugestões, resultado do merge |
| `http://localhost:5000/` | Configuração efetivamente carregada pela instância em execução |

---

## 7. Diagnóstico de problemas

### `build.ps1` abre o Bloco de Notas em vez de compilar

Use **`build.bat`**. O Windows associa arquivos `.ps1` ao Bloco de Notas de propósito, para evitar
execução acidental por duplo clique — então tanto o duplo clique quanto `.\build.ps1` digitado no
`cmd.exe` apenas abrem o editor. Além disso, a `ExecutionPolicy` padrão (`Restricted`) bloqueia
`.ps1` mesmo dentro do PowerShell.

O `build.bat` chama `powershell -ExecutionPolicy Bypass -File build.ps1`, o que contorna as duas
coisas sem alterar nenhuma configuração da máquina. Para verificar a política atual:

```powershell
Get-ExecutionPolicy -List
```

### O executável abre e fecha na hora

Rode pelo prompt (`cmd`) em vez de dar duplo clique, para ler a mensagem. Quase sempre é
configuração faltando (saída `1`) ou primeira execução (saída `2`).

### `git não encontrado no PATH`

Instale o Git ou preencha:

```ini
[git]
executavel = C:\Program Files\Git\cmd\git.exe
```

### O antivírus bloqueou o `.exe`

Falso positivo comum com executáveis gerados por PyInstaller. Adicione a pasta como exceção no
Windows Defender. Para uma distribuição ampla, o caminho definitivo é assinar o binário.

### O webhook responde `401`

O cabeçalho `X-PyAgent-Token` não bate com `[servidor] token_webhook`. Confira nos dois lados.

### O Bitbucket entrega o evento duas vezes

Mantenha `[servidor] processamento_assincrono = true`. Assim o agente responde `202` na hora e
processa em segundo plano, e ainda descarta eventos repetidos do mesmo PR enquanto ele está sendo
processado.

### `Falha ao buscar diff: 401`

Credenciais do Bitbucket inválidas. Use o **e-mail da conta Atlassian** em `[bitbucket] email` e um
**app password** com permissão de leitura e escrita em `api_token`. Lembre que `[bitbucket] usuario`
é o nome de usuário do Bitbucket, que pode ser diferente do e-mail — ele é usado na URL de clone.

### "Resposta da IA truncada por limite de tokens"

Aumente `[ia] max_tokens`. Acontece com arquivos `.pas` grandes devolvidos inteiros na resolução de
conflito. O agente avisa no log e no comentário do PR quando isso ocorre, em vez de commitar um
arquivo pela metade.

### A IA comentou algo que o time não quer ver

Acrescente o caso à seção "O que NÃO comentar" do `regras_projeto.md`. Efeito imediato, sem
reiniciar.

### Comentários demais no PR

Reduza `[revisao] max_sugestoes` ou suba `[revisao] severidade_minima` para `MEDIO` ou `ALTO`.

### O conflito não foi resolvido automaticamente

O agente comenta o motivo no próprio PR. As causas previstas:

| Motivo | Significado |
|---|---|
| `resolucao_incompleta` | A IA não cobriu todos os arquivos que o Git marcou como conflitantes. O merge foi abortado de propósito — commitar assim deixaria marcadores `<<<<<<<` no repositório |
| `conflito_remanescente` | Ainda havia caminho não mesclado após aplicar as resoluções |
| Arquivo listado como "verifique manualmente" | A IA quis alterar um arquivo que o Git **não** marcou como conflitante. Nada foi gravado nele. Costuma indicar inconsistência semântica: vale conferir se as mudanças combinadas se encaixam |
| Extensão bloqueada | `.dfm`, `.dproj` e afins nunca são resolvidos automaticamente |
| `requer_revisao_humana` | A própria IA se recusou a resolver por falta de contexto de negócio |

### Loop de commits

Já existe proteção: se o commit mais recente da branch for do próprio agente (`🤖 IA Auto-fix`), o
evento é ignorado. Se ainda assim houver loop, verifique se algum outro processo está reescrevendo
a mensagem de commit.
