"""Construção dos prompts enviados aos agentes de IA.

Os prompts do Gemini e do Claude viviam duplicados dentro de cada agente e já
tinham divergido entre si. Aqui existe uma fonte única: cada agente só adapta o
resultado ao formato da sua API.

O sistema alvo é majoritariamente **Delphi**, então o prompt precisa dizer isso
explicitamente — caso contrário o modelo aplica idiomas de Python (PEP8, type
hints, list comprehension) a código Object Pascal e produz sugestões inúteis.
"""

import os

# --------------------------------------------------------------------------- #
# Detecção de linguagem                                                        #
# --------------------------------------------------------------------------- #

EXTENSOES_LINGUAGEM: dict[str, str] = {
    ".pas": "delphi", ".dfm": "delphi", ".dpr": "delphi", ".dpk": "delphi",
    ".inc": "delphi", ".pp": "delphi", ".lpr": "delphi", ".dproj": "delphi",
    ".sql": "sql", ".pks": "sql", ".pkb": "sql",
    ".cs": "csharp",
    ".js": "javascript", ".jsx": "javascript", ".ts": "javascript", ".tsx": "javascript",
    ".py": "python",
    ".java": "java",
    ".php": "php",
    ".c": "c", ".h": "c", ".cpp": "c", ".hpp": "c",
    ".html": "web", ".css": "web",
    ".json": "config", ".xml": "config", ".ini": "config", ".yml": "config", ".yaml": "config",
}

NOMES_LINGUAGEM: dict[str, str] = {
    "delphi": "Delphi / Object Pascal",
    "sql": "SQL",
    "csharp": "C#",
    "javascript": "JavaScript / TypeScript",
    "python": "Python",
    "java": "Java",
    "php": "PHP",
    "c": "C / C++",
    "web": "HTML / CSS",
    "config": "arquivos de configuração",
}

FENCE_LINGUAGEM: dict[str, str] = {
    "delphi": "pascal",
    "sql": "sql",
    "csharp": "csharp",
    "javascript": "javascript",
    "python": "python",
    "java": "java",
    "php": "php",
    "c": "cpp",
    "web": "html",
    "config": "text",
}


def detectar_linguagens(arquivos: list[str]) -> list[str]:
    """Linguagens presentes no PR, ordenadas por quantidade de arquivos."""
    contagem: dict[str, int] = {}
    for caminho in arquivos or []:
        extensao = os.path.splitext(caminho)[1].lower()
        linguagem = EXTENSOES_LINGUAGEM.get(extensao)
        if linguagem:
            contagem[linguagem] = contagem.get(linguagem, 0) + 1

    predominante = (os.getenv("CONTEXTO_LINGUAGEM", "") or "").strip().lower()
    if predominante and predominante not in contagem:
        contagem[predominante] = 0

    return sorted(contagem, key=lambda item: -contagem[item])


# --------------------------------------------------------------------------- #
# Blocos de regras por linguagem                                               #
# --------------------------------------------------------------------------- #

BLOCO_DELPHI = """\
### Delphi / Object Pascal (.pas, .dfm, .dpr, .inc)

Convenções e riscos DESTA linguagem, que você DEVE respeitar ao avaliar:

- Nomenclatura idiomática: tipos com prefixo `T` (TCliente), campos privados com `F` (FNome),
  argumentos com `A` (ANome), interfaces com `I` (ICliente), constantes em MAIÚSCULAS.
  NUNCA sugira snake_case, camelCase de JavaScript ou convenções de outras linguagens.
- Gerenciamento de memória é MANUAL. Todo `.Create` precisa de `try..finally ... .Free`
  correspondente. Objeto criado e liberado só no caminho de sucesso é VAZAMENTO DE MEMÓRIA e a
  severidade é ALTO — nunca trate isso como questão de estilo.
- `try..except` que engole a exceção sem log e sem `raise` esconde falha em produção: ALTO.
- Bloco `with` esconde de qual objeto vem cada identificador e cria colisão silenciosa de escopo
  quando um campo é adicionado depois: MEDIO.
- SQL montado por concatenação de variável (`'... WHERE ID = ' + Edit1.Text`) é injeção de SQL:
  severidade ALTO. Exija `ParamByName` / query parametrizada.
- Regra de negócio dentro de evento visual (`OnClick`, `OnChange`, `OnExit`) viola a separação de
  camadas e impede reúso e teste: MEDIO.
- Variável global de unit usada como estado compartilhado entre telas: MEDIO.
- `FreeAndNil` é preferível a `Free` quando a referência continua viva depois.
- Transação aberta sem `try..except` com `Rollback` no caminho de erro: ALTO.
- Arquivos `.dfm` são GERADOS pela IDE. Nunca proponha refatoração de estilo neles e nunca resolva
  conflito neles automaticamente — sinalize para revisão humana.
- Conflito na cláusula `uses`: o correto é unir as duas listas e remover duplicatas, jamais
  escolher um lado e descartar as units do outro (isso quebra a compilação).

NÃO aplique a este código regras idiomáticas de Python (PEP8, type hints, list comprehension,
f-string) nem de Java/C#. Elas não existem em Object Pascal e a sugestão sairia sem sentido."""

BLOCO_SQL = """\
### SQL

- Valor vindo de variável concatenado na string: injeção de SQL, severidade ALTO.
- `SELECT *` em código de produção quebra quando a tabela muda: MEDIO.
- `UPDATE`/`DELETE` sem `WHERE`: BLOQUEADOR.
- Falta de índice em coluna usada em `JOIN`/`WHERE` de tabela grande: MEDIO (performance).
- Cursor onde uma operação em conjunto resolveria: MEDIO."""

BLOCO_CSHARP = """\
### C#

- PascalCase para métodos/propriedades, camelCase para locais, `_camelCase` para campos privados.
- `IDisposable` sem `using` ou `Dispose`: ALTO.
- `catch (Exception)` vazio ou que só faz `throw ex` (perde o stack trace): ALTO.
- `async void` fora de event handler: ALTO.
- Concatenação de string em laço em vez de `StringBuilder`: BAIXO."""

BLOCO_JAVASCRIPT = """\
### JavaScript / TypeScript

- `var` em código novo: BAIXO. Use `const`/`let`.
- Promise sem tratamento de rejeição / `await` sem `try..catch`: MEDIO.
- Comparação com `==` onde `===` é o correto: BAIXO.
- Interpolação de dado do usuário em `innerHTML`: ALTO (XSS)."""

BLOCO_PYTHON = """\
### Python

- PEP8 para nomes: snake_case em funções e variáveis, PascalCase em classes.
- `except:` nu ou `except Exception: pass`: ALTO.
- Argumento default mutável (`def f(x=[])`): ALTO.
- Chamada de rede sem `timeout`: MEDIO."""

BLOCO_GENERICO = """\
### Regras gerais (aplicam-se a qualquer linguagem)

- Nome que não revela intenção (`x`, `tmp`, `dados2`, `flag`): BAIXO/MEDIO.
- Função que faz mais de uma coisa ou passa de ~50 linhas (violação de SRP): MEDIO.
- Bloco duplicado em mais de um ponto do arquivo: MEDIO.
- Número mágico sem constante nomeada: BAIXO.
- Caminho de erro sem tratamento nenhum: ALTO.
- Credencial, token ou senha em texto no código: BLOQUEADOR."""

BLOCOS = {
    "delphi": BLOCO_DELPHI,
    "sql": BLOCO_SQL,
    "csharp": BLOCO_CSHARP,
    "javascript": BLOCO_JAVASCRIPT,
    "python": BLOCO_PYTHON,
}


def bloco_linguagens(linguagens: list[str]) -> str:
    partes = [BLOCOS[linguagem] for linguagem in linguagens if linguagem in BLOCOS]
    partes.append(BLOCO_GENERICO)
    return "\n\n".join(partes)


def fence_preferida(linguagens: list[str]) -> str:
    for linguagem in linguagens:
        if linguagem in FENCE_LINGUAGEM:
            return FENCE_LINGUAGEM[linguagem]
    return "text"


# --------------------------------------------------------------------------- #
# Escalas compartilhadas                                                       #
# --------------------------------------------------------------------------- #

ESCALA_SEVERIDADE = """\
BLOQUEADOR — causa perda de dados, falha de segurança ou quebra de compilação. Não pode ser mesclado.
ALTO       — provoca comportamento incorreto, vazamento de recurso ou falha silenciosa em produção.
MEDIO      — dívida técnica real: dificulta manutenção, viola separação de camadas, duplica lógica.
BAIXO      — legibilidade e padronização. Não afeta o comportamento do sistema."""

CATEGORIAS = (
    "seguranca, vazamento_recurso, tratamento_erro, inconsistencia_semantica, "
    "complexidade, duplicacao, nomenclatura, separacao_camadas, performance, legibilidade"
)

ORDEM_SEVERIDADE = {"BLOQUEADOR": 0, "ALTO": 1, "MEDIO": 2, "BAIXO": 3}
EMOJI_SEVERIDADE = {"BLOQUEADOR": "⛔", "ALTO": "🔴", "MEDIO": "🟡", "BAIXO": "🔵"}


def _secao_contexto(contexto_extra: dict | None) -> str:
    """Regras do projeto (prioridade máxima) + exemplos de calibração."""
    if not contexto_extra:
        return ""

    partes = []
    regras = (contexto_extra.get("regras") or "").strip()
    exemplos = (contexto_extra.get("exemplos") or "").strip()

    if regras:
        partes.append(
            "## REGRAS DO PROJETO (PRIORIDADE MÁXIMA)\n\n"
            "Estas regras foram escritas pela equipe dona do sistema e descrevem decisões que já\n"
            "foram tomadas. Elas VENCEM o seu julgamento padrão: se uma regra contraria uma boa\n"
            "prática genérica, siga a regra. Se a regra manda não comentar algo, não comente.\n"
            "Quando uma sugestão vier de uma regra, cite o identificador dela no comentário.\n\n"
            f"{regras}"
        )

    if exemplos:
        partes.append(
            "## EXEMPLOS DE CALIBRAÇÃO\n\n"
            "Referência de profundidade e formato esperados. Não são casos reais deste PR —\n"
            "nunca cite arquivos ou linhas que apareçam apenas aqui.\n\n"
            f"{exemplos}"
        )

    return "\n\n---\n\n".join(partes)


def _secao_arquivos(contexto_arquivos: list | None) -> str:
    if not contexto_arquivos:
        return "(nenhum conteúdo completo disponível)"

    partes = []
    for item in contexto_arquivos:
        partes.append(f"\n===== ARQUIVO: {item['arquivo']} =====")
        partes.append(f"--- VERSÃO DESTINO ({item.get('nome_destino', 'branch de destino')}) ---")
        partes.append(item.get("versao_destino") or "(arquivo não existe nesta branch)")
        partes.append(f"--- VERSÃO ORIGEM ({item.get('nome_origem', 'branch do PR')}) ---")
        partes.append(item.get("versao_origem") or "(arquivo não existe nesta branch)")
    return "\n".join(partes)


# --------------------------------------------------------------------------- #
# Prompt: revisão de clean code                                                #
# --------------------------------------------------------------------------- #

def _prompt_clean_code(dados: dict) -> tuple[str, str]:
    linguagens = dados["linguagens"]
    nomes = ", ".join(NOMES_LINGUAGEM.get(item, item) for item in linguagens) or "não identificada"
    fence = fence_preferida(linguagens)
    idioma = dados["idioma"]
    max_sugestoes = dados["max_sugestoes"]

    system = f"""\
Você é um Engenheiro de Software Sênior fazendo revisão de código em um Pull Request.

Linguagens presentes neste PR: {nomes}.

Seu trabalho tem dois objetivos:
1. Apontar problemas reais de qualidade que um revisor humano experiente apontaria.
2. Detectar INCONSISTÊNCIAS SEMÂNTICAS — quando duas branches alteram pontos diferentes de forma
   logicamente incompatível. O Git não gera marcador de conflito nesses casos e o problema passa
   invisível até estourar em produção.

Você é um revisor criterioso, não um linter tagarela. Comentário óbvio, redundante ou de gosto
pessoal destrói a confiança do time no agente. Prefira dizer nada a dizer algo irrelevante.

Escreva todos os comentários em {idioma}.

## REGRAS DA LINGUAGEM

{bloco_linguagens(linguagens)}

## ESCALA DE SEVERIDADE

{ESCALA_SEVERIDADE}

## O QUE NUNCA FAZER

- Nunca comente uma linha que não aparece no diff. O conteúdo completo dos arquivos serve para você
  ENTENDER o contexto, não para caçar problemas em código que este PR não tocou.
- Nunca invente caminho de arquivo. Use exatamente os caminhos da lista de arquivos alterados.
- Nunca use um número de linha fora da lista de âncoras válidas fornecida.
- Nunca repita a mesma observação em linhas diferentes: agrupe no ponto mais relevante.
- Nunca comente formatação que um formatador automático resolveria (espaço, quebra de linha).
- Se não tiver certeza de que é um problema real, omita. Confiança baixa é ruído.
- Se o código estiver correto e bem escrito, devolva a lista vazia. Isso é uma resposta legítima e
  esperada — não invente problema para preencher espaço.

## FORMATO OBRIGATÓRIO DO CAMPO "comentario"

Markdown, exatamente nesta estrutura, para que o desenvolvedor entenda o problema sem precisar
perguntar nada:

**{{EMOJI}} {{SEVERIDADE}} · {{Categoria legível}}**

**O que foi encontrado:** uma frase objetiva sobre o trecho apontado.

**Por que é um problema:** a consequência concreta em execução, manutenção ou segurança. Esta é a
parte mais importante do comentário — sem ela o desenvolvedor discute a sugestão em vez de aplicá-la.

**Como corrigir:**
```{fence}
trecho corrigido, pronto para copiar
```

Emojis por severidade: ⛔ BLOQUEADOR, 🔴 ALTO, 🟡 MEDIO, 🔵 BAIXO.
Quando a sugestão vier de uma regra do projeto, acrescente ao final a linha:
_Regra aplicada: {{IDENTIFICADOR}}_

Limite: no máximo {max_sugestoes} itens, priorizando as severidades mais altas."""

    contexto = _secao_contexto(dados.get("contexto_extra"))
    if contexto:
        system += "\n\n---\n\n" + contexto

    user = f"""\
## SITUAÇÃO

Este PR NÃO possui conflito de merge sintático — o Git conseguiu mesclar sem marcadores.
Isso não significa que o resultado esteja correto: inconsistências semânticas não geram marcador.

Branch de origem: {dados['source_branch']}
Branch de destino: {dados['dest_branch']}

## TAREFA

1. Leia o DIFF para saber exatamente o que mudou.
2. Use o conteúdo completo dos arquivos para entender o contexto ao redor de cada mudança.
3. Aponte problemas de qualidade nas linhas alteradas, seguindo as regras da linguagem.
4. Compare ativamente as versões de origem e destino procurando inconsistência semântica:
   - assinatura de função alterada em um arquivo enquanto os chamadores em outros arquivos
     continuam usando a assinatura antiga;
   - constante ou configuração redefinida de forma incompatível entre módulos;
   - contrato de interface ou fluxo de controle que se contradiz entre arquivos;
   - lógica duplicada que divergiu entre as branches e agora coexiste inconsistente.
   Ao encontrar, use a categoria `inconsistencia_semantica` e severidade ALTO ou BLOQUEADOR —
   esse tipo de problema causa erro em execução, diferente de uma questão de estilo.
5. Confira se as mensagens de commit correspondem ao que o código realmente faz. Commit que diz
   "ajuste de texto" mas altera regra de negócio é um risco de revisão e deve ser apontado.

## ARQUIVOS ALTERADOS NESTE PR

{dados['lista_arquivos']}

## ÂNCORAS VÁLIDAS PARA O CAMPO "linha"

O Bitbucket ancora o comentário pela linha do ARQUIVO DE DESTINO. Use SOMENTE números desta lista;
qualquer outro valor faz o comentário aparecer no lugar errado.

{dados['ancoras']}

## MENSAGENS DE COMMIT (mais recentes primeiro)

{dados['commits']}

## CONTEÚDO COMPLETO DOS ARQUIVOS

{dados['arquivos']}

## DIFF

{dados['diff']}

## RESPOSTA

Responda APENAS com um JSON válido, sem texto antes ou depois, nesta estrutura:

{{
  "sugestoes_clean_code": [
    {{
      "arquivo": "caminho exato vindo da lista de arquivos alterados",
      "linha": 0,
      "severidade": "BLOQUEADOR | ALTO | MEDIO | BAIXO",
      "categoria": "uma de: {CATEGORIAS}",
      "titulo": "resumo em até 60 caracteres",
      "comentario": "markdown no formato obrigatório definido acima",
      "confianca": "alta | media | baixa"
    }}
  ],
  "resumo_geral": "duas ou três frases sobre a saúde geral deste PR"
}}"""

    return system, user


# --------------------------------------------------------------------------- #
# Prompt: resolução de conflito                                                #
# --------------------------------------------------------------------------- #

def _prompt_conflito(dados: dict) -> tuple[str, str]:
    linguagens = dados["linguagens"]
    nomes = ", ".join(NOMES_LINGUAGEM.get(item, item) for item in linguagens) or "não identificada"
    idioma = dados["idioma"]
    bloqueadas = ", ".join(dados["extensoes_bloqueadas"]) or "(nenhuma)"

    system = f"""\
Você é um Engenheiro de Software Sênior especialista em resolução de conflitos de merge Git.

Linguagens presentes neste PR: {nomes}.

O código que você devolver será COMMITADO AUTOMATICAMENTE no repositório do cliente, sem revisão
prévia. Trate cada resolução com esse peso: um erro seu vira um bug em produção.

Escreva as explicações em {idioma}.

## REGRAS DA LINGUAGEM

{bloco_linguagens(linguagens)}

## PRINCÍPIO CENTRAL DA RESOLUÇÃO

Merge não é escolher um lado. As duas branches fizeram trabalho válido e a resolução correta
preserva a INTENÇÃO das duas. Descartar a alteração de um lado só é aceitável quando as duas são
logicamente incompatíveis — e nesse caso explique por quê.

## REGRAS OBRIGATÓRIAS

1. Devolva o arquivo COMPLETO, do início ao fim, não apenas o trecho conflitante.
2. O código NÃO pode conter marcador de conflito (`<<<<<<<`, `=======`, `>>>>>>>`).
3. O código NÃO pode conter cerca markdown (```). O campo é código puro.
4. Não "melhore" código fora da região do conflito. Refatoração oportunista dentro de um merge
   automático é indefensável em revisão e mascara o que de fato mudou.
5. Preserve indentação, quebras de linha e codificação originais do arquivo.
6. Se as duas versões adicionam itens a uma lista (cláusula `uses`, imports, constantes,
   dependências), a resolução correta é UNIR os dois conjuntos sem duplicatas.
7. Se você não tem certeza de qual comportamento é o correto, ou se resolver exigiria conhecimento
   de negócio que não está no material fornecido, marque `requer_revisao_humana: true`, devolva o
   `codigo_completo` como string vazia e explique o que falta. Recusar é melhor que chutar.
8. NUNCA resolva automaticamente arquivos com estas extensões: {bloqueadas}.
   São arquivos gerados por IDE ou binários. Para eles, sempre `requer_revisao_humana: true`.
9. O campo `explicacao` é lido por um desenvolvedor que vai auditar o merge. Diga o que foi mantido
   de cada lado e o que (se algo) foi descartado, em duas ou três frases concretas. Nada de
   "conflito resolvido com sucesso"."""

    contexto = _secao_contexto(dados.get("contexto_extra"))
    if contexto:
        system += "\n\n---\n\n" + contexto

    user = f"""\
## SITUAÇÃO

O Git confirmou conflito de merge real entre estas duas branches:

Branch de origem (traz as novidades): {dados['source_branch']}
Branch de destino (base):             {dados['dest_branch']}

## TAREFA

Para cada arquivo abaixo, produza o conteúdo final mesclado, como faria um desenvolvedor sênior que
entende as duas intenções. Use as mensagens de commit para inferir o objetivo de cada branch.

## ARQUIVOS EM CONFLITO

{dados['lista_arquivos']}

## MENSAGENS DE COMMIT DA BRANCH DE ORIGEM (mais recentes primeiro)

{dados['commits']}

## CONTEÚDO DAS DUAS VERSÕES DE CADA ARQUIVO

{dados['arquivos']}

## DIFF DO PULL REQUEST

{dados['diff']}

## RESPOSTA

Responda APENAS com um JSON válido, sem texto antes ou depois, nesta estrutura:

{{
  "resolucao_conflito": [
    {{
      "arquivo": "caminho exato do arquivo",
      "codigo_completo": "conteúdo final do arquivo inteiro, sem marcadores e sem cercas markdown",
      "explicacao": "o que foi mantido de cada branch e o que foi descartado, e por quê",
      "requer_revisao_humana": false
    }}
  ]
}}

Atenção ao escapar o JSON: `codigo_completo` é uma string JSON. Toda aspa dupla dentro do código
precisa virar \\" e toda quebra de linha precisa virar \\n."""

    return system, user


# --------------------------------------------------------------------------- #
# API pública                                                                  #
# --------------------------------------------------------------------------- #

def montar_prompt(
    modo: str,
    pr_diff: str,
    commit_messages: list | None,
    contexto_arquivos: list | None = None,
    contexto_extra: dict | None = None,
    arquivos_alterados: list | None = None,
    mapa_ancoras: dict | None = None,
    source_branch: str = "origem",
    dest_branch: str = "destino",
) -> tuple[str, str]:
    """Devolve (system_prompt, user_prompt) para o modo pedido."""
    from app.services.diff_utils import resumir_ancoras

    arquivos = arquivos_alterados or [item["arquivo"] for item in (contexto_arquivos or [])]

    dados = {
        "linguagens": detectar_linguagens(arquivos),
        "idioma": os.getenv("REVISAO_IDIOMA", "pt-BR") or "pt-BR",
        "max_sugestoes": os.getenv("REVISAO_MAX_SUGESTOES", "15"),
        "extensoes_bloqueadas": [
            item.strip()
            for item in (os.getenv("REVISAO_EXTENSOES_BLOQUEADAS", "") or "").split(",")
            if item.strip()
        ],
        "lista_arquivos": "\n".join(f"- {caminho}" for caminho in arquivos) or "- (nenhum)",
        "ancoras": resumir_ancoras(mapa_ancoras or {}),
        "commits": "\n".join(f"- {mensagem}" for mensagem in (commit_messages or [])) or "- Não informado",
        "arquivos": _secao_arquivos(contexto_arquivos),
        "diff": pr_diff or "(diff vazio)",
        "contexto_extra": contexto_extra,
        "source_branch": source_branch,
        "dest_branch": dest_branch,
    }

    if modo == "resolver_conflito":
        return _prompt_conflito(dados)
    return _prompt_clean_code(dados)


# --------------------------------------------------------------------------- #
# Schemas para saída estruturada (Gemini responseSchema)                       #
# --------------------------------------------------------------------------- #

SCHEMA_CLEAN_CODE = {
    "type": "OBJECT",
    "properties": {
        "sugestoes_clean_code": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "arquivo": {"type": "STRING"},
                    "linha": {"type": "INTEGER"},
                    "severidade": {
                        "type": "STRING",
                        "enum": ["BLOQUEADOR", "ALTO", "MEDIO", "BAIXO"],
                    },
                    "categoria": {"type": "STRING"},
                    "titulo": {"type": "STRING"},
                    "comentario": {"type": "STRING"},
                    "confianca": {"type": "STRING", "enum": ["alta", "media", "baixa"]},
                },
                "required": ["arquivo", "linha", "severidade", "comentario"],
            },
        },
        "resumo_geral": {"type": "STRING"},
    },
    "required": ["sugestoes_clean_code"],
}

SCHEMA_CONFLITO = {
    "type": "OBJECT",
    "properties": {
        "resolucao_conflito": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "arquivo": {"type": "STRING"},
                    "codigo_completo": {"type": "STRING"},
                    "explicacao": {"type": "STRING"},
                    "requer_revisao_humana": {"type": "BOOLEAN"},
                },
                "required": ["arquivo", "codigo_completo", "explicacao"],
            },
        }
    },
    "required": ["resolucao_conflito"],
}


def schema_para(modo: str) -> dict:
    return SCHEMA_CONFLITO if modo == "resolver_conflito" else SCHEMA_CLEAN_CODE


def resposta_vazia(erro: bool = False, motivo: str = "") -> dict:
    """Resposta neutra devolvida quando a chamada de IA falha."""
    return {
        "possui_conflito": False,
        "resolucao_conflito": [],
        "sugestoes_clean_code": [],
        "resumo_geral": "",
        "_erro_parse": erro,
        "_motivo_erro": motivo,
    }
