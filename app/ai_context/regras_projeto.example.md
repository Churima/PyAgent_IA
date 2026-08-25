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

## 1. Contexto do sistema

- **Linguagem predominante:** Delphi (Object Pascal), versão `<XX>`.
- **Outras linguagens presentes:** `<SQL Server / Firebird, C#, JavaScript...>`.
- **Banco de dados:** `<Firebird 3 / SQL Server 2019 / ...>`.
- **Camadas:** `<descreva brevemente a organização: telas, regras de negócio, acesso a dados>`.
- **O que NÃO pode quebrar em hipótese alguma:** `<módulos críticos: faturamento, fiscal, integração>`.

---

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
