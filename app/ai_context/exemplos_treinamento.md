# Exemplos de Treinamento — PyAgent IA

Estes exemplos mostram o padrão de análise esperado para cada categoria de cenário de PR.
Use-os como referência para calibrar suas respostas aos casos reais.

---

## CATEGORIA 1: CONFLITOS DE MERGE

### EX-CM-01 — Conflito textual simples (mesma linha editada em ambas as branches)

**Contexto:** Mesma constante alterada com valores diferentes nas duas branches.

**VERSÃO DESTINO (main):**
```python
# app/config.py
TEMPO_SESSAO_MINUTOS = 60
MAX_TENTATIVAS_LOGIN = 3
```

**VERSÃO ORIGEM (developer branch):**
```python
# app/config.py
TEMPO_SESSAO_MINUTOS = 120
MAX_TENTATIVAS_LOGIN = 3
```

**DIFF:**
```diff
- TEMPO_SESSAO_MINUTOS = 30
+ TEMPO_SESSAO_MINUTOS = 120
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": true,
  "resolucao_conflito": [
    {
      "arquivo": "app/config.py",
      "codigo_completo": "TEMPO_SESSAO_MINUTOS = 120\nMAX_TENTATIVAS_LOGIN = 3\n"
    }
  ],
  "sugestoes_clean_code": []
}
```

---

### EX-CM-02 — Conflito semântico (lógica alterada de formas incompatíveis)

**Contexto:** Branch A muda a condição do `if`; branch B muda o corpo do mesmo `if`. O código não conflita textualmente no git, mas a lógica combinada é inconsistente.

**VERSÃO DESTINO (main):**
```python
def autorizar_operacao(usuario, valor):
    if usuario.ativo and valor > 0:
        registrar_auditoria(usuario.id, valor)
        return True
    return False
```

**VERSÃO ORIGEM (developer branch):**
```python
def autorizar_operacao(usuario, valor):
    if usuario.ativo:
        registrar_auditoria(usuario.id, valor)
        notificar_gestor(usuario.id)
        return True
    return False
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": true,
  "resolucao_conflito": [
    {
      "arquivo": "app/services/autorizacao.py",
      "codigo_completo": "def autorizar_operacao(usuario, valor):\n    if usuario.ativo and valor > 0:\n        registrar_auditoria(usuario.id, valor)\n        notificar_gestor(usuario.id)\n        return True\n    return False\n"
    }
  ],
  "sugestoes_clean_code": []
}
```

---

### EX-CM-03 — Conflito multi-arquivo (interface alterada em um arquivo, implementação em outro)

**Contexto:** Branch renomeia método no model; main ainda chama o nome antigo no service.

**VERSÃO DESTINO (main) — app/services/pedido.py:**
```python
def calcular_total(pedido):
    return pedido.calcular_preco()
```

**VERSÃO ORIGEM (developer branch) — app/models/produto.py:**
```python
class Produto:
    def obter_preco_final(self):  # renomeado de calcular_preco
        return self.preco * (1 - self.desconto)
```

**DIFF:**
```diff
--- app/models/produto.py
- def calcular_preco(self):
+ def obter_preco_final(self):
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": true,
  "resolucao_conflito": [
    {
      "arquivo": "app/services/pedido.py",
      "codigo_completo": "def calcular_total(pedido):\n    return pedido.obter_preco_final()\n"
    }
  ],
  "sugestoes_clean_code": []
}
```

---

### EX-CM-04 — Renomeação de variável em uma branch + edição na outra

**Contexto:** Branch A renomeia `taxa` para `taxa_juros_mensal`; branch B edita o valor de `taxa` com nova fórmula.

**VERSÃO DESTINO (main):**
```python
taxa_juros_mensal = 0.05
valor_final = principal * (1 + taxa_juros_mensal) ** meses
```

**VERSÃO ORIGEM (developer branch):**
```python
taxa = inflacao_atual() * 1.2
valor_final = principal * (1 + taxa) ** meses
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": true,
  "resolucao_conflito": [
    {
      "arquivo": "app/calculadora.py",
      "codigo_completo": "taxa_juros_mensal = inflacao_atual() * 1.2\nvalor_final = principal * (1 + taxa_juros_mensal) ** meses\n"
    }
  ],
  "sugestoes_clean_code": []
}
```

---

### EX-CM-05 — Conflito em imports (branches adicionam imports diferentes na mesma região)

**VERSÃO DESTINO (main):**
```python
from flask import request, jsonify, abort
```

**VERSÃO ORIGEM (developer branch):**
```python
from flask import request, jsonify, redirect, url_for
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": true,
  "resolucao_conflito": [
    {
      "arquivo": "app/api/webhook.py",
      "codigo_completo": "from flask import request, jsonify, abort, redirect, url_for\n"
    }
  ],
  "sugestoes_clean_code": []
}
```

---

### EX-CM-06 — Conflito em arquivo de configuração (requirements.txt)

**VERSÃO DESTINO (main):**
```
requests==2.28.0
flask==2.3.0
```

**VERSÃO ORIGEM (developer branch):**
```
requests==2.31.0
flask==2.3.0
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": true,
  "resolucao_conflito": [
    {
      "arquivo": "requirements.txt",
      "codigo_completo": "requests==2.31.0\nflask==2.3.0\n"
    }
  ],
  "sugestoes_clean_code": []
}
```

---

### EX-CM-07 — Conflito de ordenação (mesma função movida para posições diferentes)

**Contexto:** Ambas as branches moveram `validar_token()` para diferentes posições no arquivo, causando duplicação e conflito de ordem.

**VERSÃO DESTINO (main):**
```python
def validar_token(token):
    return token == os.getenv("API_TOKEN")

def processar_requisicao(dados):
    pass
```

**VERSÃO ORIGEM (developer branch):**
```python
def processar_requisicao(dados):
    pass

def validar_token(token):
    return token == os.getenv("API_TOKEN")
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": true,
  "resolucao_conflito": [
    {
      "arquivo": "app/utils.py",
      "codigo_completo": "def validar_token(token):\n    return token == os.getenv(\"API_TOKEN\")\n\ndef processar_requisicao(dados):\n    pass\n"
    }
  ],
  "sugestoes_clean_code": []
}
```

---

### EX-CM-08 — Conflito com deleção (branch A edita função, branch B a deleta)

**VERSÃO DESTINO (main):**
```python
def processar_pagamento(pedido, cartao):
    validar_cartao(cartao)
    if pedido.valor > 1000:
        requer_autorizacao_extra(pedido)
    return gateway.cobrar(pedido.valor, cartao)
```

**VERSÃO ORIGEM (developer branch):**
```python
# processar_pagamento removida; pagamentos agora via PagamentoService
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": true,
  "resolucao_conflito": [
    {
      "arquivo": "app/services/pagamento.py",
      "codigo_completo": "# processar_pagamento migrada para PagamentoService\n# Verificar chamadas remanescentes em: checkout.py, pedido_service.py\n"
    }
  ],
  "sugestoes_clean_code": []
}
```

---

### EX-CM-09 — Conflito em bloco de múltiplas linhas (merge marker cortando lógica complexa)

**Contexto:** Ambas as branches modificaram partes diferentes de um bloco `if/elif/else`.

**VERSÃO DESTINO (main):**
```python
def classificar_cliente(cliente):
    if cliente.compras_total > 10000:
        return "premium"
    elif cliente.compras_total > 1000:
        return "regular"
    else:
        return "novo"
```

**VERSÃO ORIGEM (developer branch):**
```python
def classificar_cliente(cliente):
    if cliente.compras_total > 10000 and cliente.ativo:
        return "premium"
    elif cliente.compras_total > 5000:
        return "gold"
    elif cliente.compras_total > 1000:
        return "regular"
    else:
        return "novo"
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": true,
  "resolucao_conflito": [
    {
      "arquivo": "app/services/cliente.py",
      "codigo_completo": "def classificar_cliente(cliente):\n    if cliente.compras_total > 10000 and cliente.ativo:\n        return \"premium\"\n    elif cliente.compras_total > 5000:\n        return \"gold\"\n    elif cliente.compras_total > 1000:\n        return \"regular\"\n    else:\n        return \"novo\"\n"
    }
  ],
  "sugestoes_clean_code": []
}
```

---

### EX-CM-10 — Conflito encadeado (resolução de um conflito gera inconsistência em outro ponto)

**Contexto:** `calcular_desconto()` tem semântica diferente nas branches — uma retorna o valor do desconto, a outra retorna o valor já descontado. `calcular_total()` depende dessa semântica.

**VERSÃO DESTINO (main):**
```python
def calcular_desconto(valor, percentual):
    return valor * percentual  # retorna apenas o valor do desconto

def calcular_total(valor, percentual):
    desconto = calcular_desconto(valor, percentual)
    return valor - desconto
```

**VERSÃO ORIGEM (developer branch):**
```python
def calcular_desconto(valor, percentual):
    return valor * (1 - percentual)  # retorna o valor já com desconto aplicado

def calcular_total(valor, percentual):
    return calcular_desconto(valor, percentual)  # já retorna o total
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": true,
  "resolucao_conflito": [
    {
      "arquivo": "app/services/desconto.py",
      "codigo_completo": "def calcular_desconto(valor: float, percentual: float) -> float:\n    return valor * (1 - percentual)\n\ndef calcular_total(valor: float, percentual: float) -> float:\n    return calcular_desconto(valor, percentual)\n"
    }
  ],
  "sugestoes_clean_code": []
}
```

---

## CATEGORIA 2: PADRÕES DE CÓDIGO

### EX-PC-11 — Nomes de variáveis pouco descritivos

**DIFF:**
```diff
+def calc(x, y, z):
+    r = x * y / z
+    t = r * 0.1
+    return r - t
```

**VERSÃO ORIGEM:**
```python
def calc(x, y, z):
    r = x * y / z
    t = r * 0.1
    return r - t
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": false,
  "resolucao_conflito": [],
  "sugestoes_clean_code": [
    {
      "arquivo": "app/services/financeiro.py",
      "linha": 1,
      "comentario": "Nome da função pouco descritivo. Renomeie para algo como `calcular_valor_liquido(preco: float, quantidade: int, divisor: float) -> float` e adicione type hints."
    },
    {
      "arquivo": "app/services/financeiro.py",
      "linha": 2,
      "comentario": "Variáveis `r` e `t` não comunicam intenção. Use nomes como `valor_bruto` e `valor_taxa`."
    }
  ]
}
```

---

### EX-PC-12 — Função excessivamente longa (violação de SRP)

**DIFF:**
```diff
+def processar_pedido(dados):
+    if not dados.get('cliente_id'):
+        return {'erro': 'cliente obrigatório'}
+    if not dados.get('itens'):
+        return {'erro': 'itens obrigatórios'}
+    cliente = db.query(Cliente).filter_by(id=dados['cliente_id']).first()
+    if not cliente or not cliente.ativo:
+        return {'erro': 'cliente inválido'}
+    subtotal = sum(i['preco'] * i['qtd'] for i in dados['itens'])
+    desconto = subtotal * 0.1 if cliente.tipo == 'premium' else 0
+    frete = 15.0 if subtotal < 100 else 0
+    total = subtotal - desconto + frete
+    pedido = Pedido(cliente_id=cliente.id, total=total)
+    db.add(pedido)
+    db.commit()
+    enviar_email(cliente.email, f'Pedido {pedido.id} confirmado')
+    return {'pedido_id': pedido.id, 'total': total}
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": false,
  "resolucao_conflito": [],
  "sugestoes_clean_code": [
    {
      "arquivo": "app/services/pedido.py",
      "linha": 1,
      "comentario": "Esta função viola o Princípio da Responsabilidade Única (SRP): valida, calcula, persiste e notifica. Separe em `validar_dados_pedido()`, `calcular_totais()`, `salvar_pedido()` e `notificar_cliente()`."
    }
  ]
}
```

---

### EX-PC-13 — Imports não utilizados

**DIFF:**
```diff
+import os
+import re
+import json
+from datetime import datetime, timedelta
+from flask import request, jsonify, redirect
```

**VERSÃO ORIGEM:**
```python
import os
import re
import json
from datetime import datetime, timedelta
from flask import request, jsonify, redirect

def webhook():
    dados = request.get_json()
    agora = datetime.now()
    return jsonify({'status': 'ok', 'hora': str(agora)})
```

**Contexto:** `re`, `json`, `timedelta` e `redirect` não são usados em nenhum ponto do arquivo.

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": false,
  "resolucao_conflito": [],
  "sugestoes_clean_code": [
    {
      "arquivo": "app/api/webhook.py",
      "linha": 2,
      "comentario": "Import `re` não utilizado no arquivo. Remova para manter o cabeçalho limpo."
    },
    {
      "arquivo": "app/api/webhook.py",
      "linha": 3,
      "comentario": "Import `json` não utilizado. Remova."
    },
    {
      "arquivo": "app/api/webhook.py",
      "linha": 4,
      "comentario": "`timedelta` importado mas nunca utilizado. Remova."
    },
    {
      "arquivo": "app/api/webhook.py",
      "linha": 5,
      "comentario": "`redirect` importado mas nunca utilizado. Remova."
    }
  ]
}
```

---

### EX-PC-14 — Código duplicado entre métodos

**DIFF:**
```diff
+def buscar_usuario_por_email(email):
+    usuario = db.query(Usuario).filter_by(email=email).first()
+    if not usuario:
+        raise ValueError('Usuário não encontrado')
+    if not usuario.ativo:
+        raise ValueError('Usuário inativo')
+    return usuario
+
+def buscar_usuario_por_cpf(cpf):
+    usuario = db.query(Usuario).filter_by(cpf=cpf).first()
+    if not usuario:
+        raise ValueError('Usuário não encontrado')
+    if not usuario.ativo:
+        raise ValueError('Usuário inativo')
+    return usuario
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": false,
  "resolucao_conflito": [],
  "sugestoes_clean_code": [
    {
      "arquivo": "app/services/usuario.py",
      "linha": 1,
      "comentario": "Bloco de validação idêntico duplicado em `buscar_usuario_por_email` e `buscar_usuario_por_cpf`. Extraia para um método privado `_validar_usuario_ativo(usuario)` e reutilize nos dois."
    }
  ]
}
```

---

## CATEGORIA 3: CENÁRIOS MISTOS

### EX-CM-15 — Conflito textual + nome de variável inadequado no trecho conflitante

**VERSÃO DESTINO (main):**
```python
def aplicar_desconto(p, d):
    r = p - (p * d)
    return r
```

**VERSÃO ORIGEM (developer branch):**
```python
def aplicar_desconto(p, d):
    r = p * (1 - d)
    return round(r, 2)
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": true,
  "resolucao_conflito": [
    {
      "arquivo": "app/services/preco.py",
      "codigo_completo": "def aplicar_desconto(preco: float, desconto: float) -> float:\n    valor_final = preco * (1 - desconto)\n    return round(valor_final, 2)\n"
    }
  ],
  "sugestoes_clean_code": [
    {
      "arquivo": "app/services/preco.py",
      "linha": 1,
      "comentario": "Aproveite a resolução do conflito para renomear: `p` → `preco`, `d` → `desconto`, `r` → `valor_final`. Adicione type hints na assinatura."
    }
  ]
}
```

---

### EX-CM-16 — Conflito semântico + função excessivamente longa

**Contexto:** O conflito semântico está dentro de uma função de 50+ linhas que já viola o SRP.

**VERSÃO DESTINO (main) — trecho relevante:**
```python
def processar_e_salvar(dados):
    # ... ~30 linhas de validação ...
    if dados['tipo'] == 'pf':
        if not validar_cpf(dados['cpf']):
            return False
    # ... ~20 linhas de persistência ...
```

**VERSÃO ORIGEM (developer branch) — mesmo trecho:**
```python
def processar_e_salvar(dados):
    # ... ~30 linhas de validação ...
    if dados['tipo'] in ('pf', 'mei'):
        cpf = dados.get('cpf') or dados.get('cnpj')
        if not cpf:
            return False
    # ... ~20 linhas de persistência ...
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": true,
  "resolucao_conflito": [
    {
      "arquivo": "app/services/cadastro.py",
      "codigo_completo": "def processar_e_salvar(dados):\n    if dados['tipo'] in ('pf', 'mei'):\n        cpf = dados.get('cpf') or dados.get('cnpj')\n        if not cpf or not validar_cpf(cpf):\n            return False\n    # demais linhas mantidas\n"
    }
  ],
  "sugestoes_clean_code": [
    {
      "arquivo": "app/services/cadastro.py",
      "linha": 1,
      "comentario": "Função com mais de 50 linhas violando SRP. Separe em `validar_cadastro()`, `classificar_tipo_pessoa()` e `salvar_cadastro()`."
    }
  ]
}
```

---

### EX-CM-17 — Conflito multi-arquivo + falta de tratamento de exceções

**VERSÃO DESTINO (main) — app/clients/bitbucket.py:**
```python
def obter_diff(pr_id):
    response = requests.get(f"{BASE_URL}/pullrequests/{pr_id}/diff", auth=AUTH)
    return response.text
```

**VERSÃO ORIGEM (developer branch) — app/services/reviewer.py:**
```python
def revisar_pr(pr_id):
    diff = obter_diff_completo(pr_id)  # nome do método foi alterado no cliente
    agente.analyze_pr(diff, [])
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": true,
  "resolucao_conflito": [
    {
      "arquivo": "app/services/reviewer.py",
      "codigo_completo": "def revisar_pr(pr_id):\n    diff = obter_diff(pr_id)\n    agente.analyze_pr(diff, [])\n"
    }
  ],
  "sugestoes_clean_code": [
    {
      "arquivo": "app/clients/bitbucket.py",
      "linha": 2,
      "comentario": "Chamada HTTP sem tratamento de exceções. Envolva em try/except para capturar `requests.exceptions.RequestException` e retorne um valor seguro em caso de falha."
    }
  ]
}
```

---

### EX-CM-18 — Conflito com deleção + código duplicado introduzido pela resolução

**VERSÃO DESTINO (main):**
```python
def formatar_cpf(cpf: str) -> str:
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
```

**VERSÃO ORIGEM (developer branch):**
```python
# formatar_cpf removida; formatação inline nos pontos de uso:
cpf_formatado = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
# ...e repetida em outro ponto do arquivo...
cpf_display = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": true,
  "resolucao_conflito": [
    {
      "arquivo": "app/utils/formatacao.py",
      "codigo_completo": "def formatar_cpf(cpf: str) -> str:\n    return f\"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}\"\n"
    }
  ],
  "sugestoes_clean_code": [
    {
      "arquivo": "app/utils/formatacao.py",
      "linha": 1,
      "comentario": "A lógica de formatação de CPF foi duplicada inline em múltiplos pontos após a remoção da função. Mantenha `formatar_cpf()` e reutilize-a para evitar DRY violation."
    }
  ]
}
```

---

## CATEGORIA 4: INCONSISTÊNCIA DE CONTEXTO

### EX-IC-19 — Commit diz "fix typo" mas altera regra de negócio

**Mensagem de commit:** `fix typo in discount function`

**DIFF:**
```diff
 def calcular_desconto(valor: float, cliente: Cliente) -> float:
-    if cliente.tipo == "premium":
-        return valor * 0.10
-    return 0
+    if cliente.tipo == "premium" or cliente.compras_total > 5000:
+        return valor * 0.15
+    elif cliente.compras_total > 1000:
+        return valor * 0.05
+    return 0
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": false,
  "resolucao_conflito": [],
  "sugestoes_clean_code": [
    {
      "arquivo": "app/services/desconto.py",
      "linha": 1,
      "comentario": "ATENÇÃO: A mensagem de commit diz 'fix typo' mas esta alteração muda a regra de negócio de desconto (novos critérios e percentuais). Atualize a mensagem do commit para descrever a mudança real."
    },
    {
      "arquivo": "app/services/desconto.py",
      "linha": 3,
      "comentario": "Os limites numéricos (5000, 1000) são magic numbers. Extraia para constantes nomeadas como `LIMITE_DESCONTO_PREMIUM = 5000` e `LIMITE_DESCONTO_REGULAR = 1000`."
    }
  ]
}
```

---

### EX-IC-20 — Mensagem de commit genérica/vazia com mudanças estruturais críticas

**Mensagem de commit:** `update`

**DIFF:**
```diff
-def autenticar_usuario(email: str, senha: str) -> bool:
-    usuario = db.query(Usuario).filter_by(email=email).first()
-    return usuario and bcrypt.check_password_hash(usuario.senha_hash, senha)
+def autenticar_usuario(email: str, senha: str) -> dict:
+    usuario = db.query(Usuario).filter_by(email=email).first()
+    if usuario and bcrypt.check_password_hash(usuario.senha_hash, senha):
+        usuario.ultimo_acesso = datetime.now()
+        db.commit()
+        return {'autenticado': True, 'usuario_id': usuario.id}
+    return {'autenticado': False}
```

**RESPOSTA ESPERADA:**
```json
{
  "possui_conflito": false,
  "resolucao_conflito": [],
  "sugestoes_clean_code": [
    {
      "arquivo": "app/services/auth.py",
      "linha": 1,
      "comentario": "ATENÇÃO: Mensagem de commit 'update' não descreve mudança crítica — a assinatura de `autenticar_usuario` mudou de `bool` para `dict`, o que pode quebrar todos os chamadores. Descreva a mudança de contrato no commit."
    },
    {
      "arquivo": "app/services/auth.py",
      "linha": 7,
      "comentario": "Operação de escrita no banco (`db.commit()`) dentro da função de autenticação mistura responsabilidades. Considere separar o registro de `ultimo_acesso` em um método próprio chamado após a autenticação."
    }
  ]
}
```
