# Regras do Projeto — <NOME DO CLIENTE / SISTEMA>

> Este arquivo é lido em toda revisão e tem **prioridade máxima** no prompt: quando uma regra daqui
> contraria uma boa prática genérica, a IA segue a regra daqui.
>
> Renomeie para `regras_projeto.md` dentro da pasta `ai_context/` para ativá-lo.
> Todo arquivo cujo nome comece com `regras` é tratado como regra de projeto.
>
> Escreva regras **imperativas e verificáveis**. Dê um identificador a cada uma (REGRA-01, REGRA-02),
> porque a IA cita esse identificador no comentário do PR e isso torna a sugestão auditável.

---
<!--
ESCOPO POR MODO - nota para quem mantem este arquivo.

As marcacoes abaixo (comentario HTML com prefixo "pyagent:") dizem em qual modo cada trecho entra
no prompt. Cada uma vale da linha em que aparece ate a proxima marcacao do arquivo:

    modo=conflito     -> so quando o Git acusou conflito de merge
    modo=cleancode    -> so na revisao de clean code
    modo=ambos        -> nos dois (e tambem o padrao de quem nao tem marcacao)

Opcionalmente, "linguagem=delphi,sql" restringe o trecho as linguagens presentes no PR.

Ha mais duas formas de escopar, para material que ja nasce de um modo so:

  - pelo nome do arquivo:  exemplos.conflito.md, regras.cleancode.delphi.md
  - pela subpasta:         ai_context/conflito/, ai_context/cleancode/delphi/

Precedencia, do mais fraco para o mais forte: subpasta, nome do arquivo, marcador interno.
Subpasta cujo nome nao seja um modo nem uma linguagem e so organizacao e nao escopa nada.

Use marcador quando o arquivo alterna de modo ou tem trecho compartilhado; use pasta quando o
arquivo inteiro pertence a um modo so.

Sem isso, o arquivo inteiro ia nos dois modos - e exemplo de resolucao de conflito nao ajuda em
nada numa revisao de clean code, so ocupa cota de token.

Todo comentario HTML (este inclusive) e descartado antes de montar o prompt: nota de manutencao
nao custa token nenhum.
-->


## 1. Contexto do sistema

- **Linguagem predominante:** Delphi (Object Pascal), versão `<XX>`.
- **Outras linguagens presentes:** `<SQL Server / Firebird, C#, JavaScript...>`.
- **Banco de dados:** `<Firebird 3 / SQL Server 2019 / ...>`.
- **Camadas:** `<descreva brevemente a organização: telas, regras de negócio, acesso a dados>`.
- **O que NÃO pode quebrar em hipótese alguma:** `<módulos críticos: faturamento, fiscal, integração>`.

---

<!-- pyagent: modo=conflito -->

## 2. Regras de resolução de conflito

- **REGRA-01:** Em conflito na cláusula `uses`, unir as duas listas, remover duplicatas e manter a
  ordem alfabética. Nunca escolher um lado e descartar as units do outro.
- **REGRA-02:** Nunca resolver conflito automaticamente em arquivos `.dfm` — sinalizar para revisão
  humana, porque são gerados pela IDE.
- **REGRA-03:** Em conflito no arquivo `<caminho/do/arquivo.pas>`, a versão da branch `<X>` sempre
  prevalece, porque `<motivo>`.
- **REGRA-04:** Em conflito envolvendo número de versão ou build, manter sempre o **maior** valor.
- **REGRA-05:** Conflito que envolva `<script de migração de banco>` nunca deve ser resolvido
  automaticamente: exigir revisão humana.

---

<!-- pyagent: modo=cleancode -->

## 3. Regras de clean code

- **REGRA-10:** Todo objeto criado com `.Create` precisa de `try..finally ... .Free` correspondente.
- **REGRA-11:** SQL sempre parametrizado (`ParamByName`). Nunca concatenar valor de variável na
  string da query.
- **REGRA-12:** Toda transação precisa de `Rollback` no caminho de erro.
- **REGRA-13:** Regra de negócio não pode ficar em evento de tela (`OnClick`, `OnChange`); deve ir
  para `<a camada/unit que vocês usam>`.
- **REGRA-14:** Nome de método precisa começar com verbo (`CalcularTotal`, `ValidarCliente`).
- **REGRA-15:** `<sua regra específica aqui>`.

---

## 4. O que NÃO comentar

> Esta seção é tão importante quanto as outras: ela impede o agente de repetir sugestões que o time
> já avaliou e decidiu rejeitar.

- Não comentar sobre `<padrão legado que o time mantém de propósito>`.
- Não sugerir renomear identificadores em `<unidade/módulo legado>` — refatoração está congelada lá.
- Não sugerir troca de `<biblioteca/componente>`; a decisão já foi tomada.
- Não comentar formatação (espaçamento, indentação): resolvido pelo formatador da IDE.

---

<!-- pyagent: modo=ambos -->

## 5. Exemplos específicos deste sistema

> Opcional, mas é o que mais melhora o resultado. Mostre um conflito real que já aconteceu e como
> vocês esperam que ele seja resolvido.

### EX-01 — `<título do caso>`

**Contexto:** `<o que estava acontecendo>`

**VERSÃO DESTINO (main):**
```pascal
// cole aqui
```

**VERSÃO ORIGEM (branch):**
```pascal
// cole aqui
```

**Resolução esperada:**
```pascal
// cole aqui o resultado correto
```

**Por quê:** `<a razão da decisão — é isso que ensina a IA a generalizar>`
