"""Agente Google Gemini — backend principal do PyAgent IA.

Chama a Generative Language API via `requests` (sem SDK) e trabalha com saída
estruturada: `responseMimeType: application/json` mais `responseSchema` fazem a
própria API garantir a forma do JSON, o que elimina quase toda a classe de erro
de parse que existia antes.

A chamada degrada em etapas: se o modelo configurado não aceitar `responseSchema`
ou `systemInstruction`, a requisição é refeita sem esses campos em vez de falhar.

O HTTP 429 de cota por minuto é tratado à parte do erro temporário comum: a API
diz quanto falta para a janela reabrir ("Please retry in 34.8s") e o agente
espera exatamente isso, em vez de reenviar em 2s e 4s e queimar as tentativas
dentro da mesma janela fechada.
"""

import json
import os
import random
import re
import threading
import time

import requests

from app.clients.ai.base import BaseAIAgent
from app.clients.ai.prompt_builder import (
    detectar_linguagens,
    montar_prompt,
    resposta_vazia,
    schema_para,
)
from app.core.logger import obter_logger
from app.services.diff_utils import estimar_tokens

log = obter_logger(__name__)

URL_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
STATUS_TEMPORARIOS = {429, 500, 502, 503, 504}

# Somada ao "retry in Xs" da API: o relógio de lá e o daqui não batem no
# milissegundo, e reenviar um instante antes da janela abrir custa outro 429.
_FOLGA_COTA = 2.0

_RE_RETRY_IN = re.compile(r"retry in\s+([\d.]+)\s*(ms|s)\b", re.IGNORECASE)

# A cota por minuto é da chave, não da thread. Quando uma requisição leva 429,
# o próximo lote — e o PR que ocupa a outra vaga de revisão — iam bater na
# mesma janela fechada e falhar também. Todo envio espera até este instante.
_cota_liberada_em = 0.0
_trava_cota = threading.Lock()


class GeminiAgent(BaseAIAgent):
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self._modelo = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite") or "gemini-3.1-flash-lite"
        self.timeout = _inteiro("AI_TIMEOUT", 180)
        self.max_tokens = _inteiro("AI_MAX_TOKENS", 16000)
        self.temperatura = _decimal("AI_TEMPERATURA", 0.0)
        self.tentativas = max(1, _inteiro("AI_TENTATIVAS", 3))
        self.usar_schema = _booleano("AI_SCHEMA_ESTRITO", True)
        self.espera_maxima_cota = max(0, _inteiro("AI_ESPERA_MAXIMA_COTA", 180))

    @property
    def url(self) -> str:
        return f"{URL_BASE}/{self._modelo}:generateContent"

    # ------------------------------------------------------------------ #
    # Entrada principal                                                   #
    # ------------------------------------------------------------------ #

    def analyze_pr(
        self,
        pr_diff: str,
        commit_messages: list,
        contexto_arquivos: list = None,
        modo: str = "clean_code",
        **kwargs,
    ) -> dict:
        log.info("Gemini (%s) iniciando análise — modo: %s", self._modelo, modo)

        if not self.api_key:
            return resposta_vazia(erro=True, motivo="GEMINI_API_KEY não configurada")

        arquivos_alterados = kwargs.get("arquivos_alterados")
        system_prompt, user_prompt = montar_prompt(
            modo=modo,
            pr_diff=pr_diff,
            commit_messages=commit_messages,
            contexto_arquivos=contexto_arquivos,
            # Só as regras e exemplos do modo em execução — ver base.carregar_contexto.
            contexto_extra=self.carregar_contexto(modo, detectar_linguagens(arquivos_alterados or [])),
            arquivos_alterados=arquivos_alterados,
            mapa_ancoras=kwargs.get("mapa_ancoras"),
            source_branch=kwargs.get("source_branch", "origem"),
            dest_branch=kwargs.get("dest_branch", "destino"),
            contexto_global=kwargs.get("contexto_global"),
        )

        resposta = self._chamar_com_degradacao(system_prompt, user_prompt, modo)
        if resposta is None:
            return resposta_vazia(erro=True, motivo=self._ultimo_motivo)

        texto, metadados = resposta
        resultado = _interpretar_json(texto)
        if resultado is None:
            log.error("Gemini devolveu conteúdo que não é JSON válido nem reparável")
            log.debug("Conteúdo recebido: %s", texto[:2000])
            return resposta_vazia(erro=True, motivo="resposta não é JSON válido")

        resultado.setdefault("sugestoes_clean_code", [])
        resultado.setdefault("resolucao_conflito", [])
        resultado.setdefault("resumo_geral", "")
        resultado["_erro_parse"] = False
        resultado["_tokens"] = metadados.get("tokens")
        resultado["_modelo"] = self._modelo

        if metadados.get("truncado"):
            resultado["_truncado"] = True
            log.error(
                "Resposta do Gemini truncada em %d tokens de saída. "
                "Aumente [ia] max_tokens no config.ini — o resultado pode estar incompleto.",
                self.max_tokens,
            )

        log.info(
            "Gemini concluiu: %d sugestão(ões), %d resolução(ões), tokens=%s",
            len(resultado.get("sugestoes_clean_code") or []),
            len(resultado.get("resolucao_conflito") or []),
            metadados.get("tokens"),
        )
        return resultado

    # ------------------------------------------------------------------ #
    # Chamada HTTP                                                        #
    # ------------------------------------------------------------------ #

    def _chamar_com_degradacao(self, system_prompt: str, user_prompt: str, modo: str):
        """Tenta a chamada em perfis cada vez mais simples.

        Um HTTP 400 quase sempre significa que o modelo não suporta algum campo
        opcional do corpo. Em vez de desistir, refazemos sem aquele campo.
        """
        self._ultimo_motivo = "falha desconhecida"

        perfis = []
        if self.usar_schema:
            perfis.append({"schema": True, "system": True})
        perfis.append({"schema": False, "system": True})
        perfis.append({"schema": False, "system": False})

        for indice, perfil in enumerate(perfis):
            corpo = self._montar_corpo(system_prompt, user_prompt, modo, **perfil)
            resposta = self._enviar(corpo)

            if resposta is not None:
                return resposta

            if not self._ultima_falha_recuperavel:
                return None

            if indice + 1 < len(perfis):
                log.warning(
                    "Gemini recusou o formato da requisição (%s). Repetindo sem %s.",
                    self._ultimo_motivo,
                    "responseSchema" if perfil.get("schema") else "systemInstruction",
                )

        return None

    def _montar_corpo(self, system_prompt: str, user_prompt: str, modo: str,
                      schema: bool, system: bool) -> dict:
        texto_usuario = user_prompt if system else f"{system_prompt}\n\n---\n\n{user_prompt}"

        corpo = {
            "contents": [{"role": "user", "parts": [{"text": texto_usuario}]}],
            "generationConfig": {
                "temperature": self.temperatura,
                "maxOutputTokens": self.max_tokens,
                "responseMimeType": "application/json",
            },
        }
        if system:
            corpo["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        if schema:
            corpo["generationConfig"]["responseSchema"] = schema_para(modo)
        return corpo

    def _enviar(self, corpo: dict):
        """Envia com retentativa em erro temporário.

        Devolve (texto, metadados) ou None. Em caso de None,
        `_ultima_falha_recuperavel` indica se vale tentar outro perfil de corpo.

        O 429 de cota por minuto não gasta tentativa: a espera que a API pediu é
        cumprida e a requisição volta a ser enviada, até somar
        `[ia] espera_maxima_cota` segundos de espera nesta requisição. Antes,
        as três tentativas saíam em 2s e 4s, todas dentro da mesma janela
        esgotada, e o lote era dado como perdido com a cota prestes a voltar.
        """
        cabecalhos = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        self._ultima_falha_recuperavel = False
        tentativa = 0
        esperas_cota = 0
        primeiro_429 = None

        while tentativa < self.tentativas:
            tentativa += 1
            _aguardar_janela_de_cota()
            try:
                resposta = requests.post(
                    self.url, json=corpo, headers=cabecalhos, timeout=self.timeout
                )
            except requests.Timeout:
                self._ultimo_motivo = f"timeout de {self.timeout}s"
                log.warning("Gemini: timeout na tentativa %d/%d", tentativa, self.tentativas)
                if tentativa < self.tentativas:
                    _esperar(tentativa)
                    continue
                return None
            except requests.RequestException as erro:
                self._ultimo_motivo = f"falha de rede: {erro}"
                log.warning("Gemini: falha de rede na tentativa %d/%d: %s",
                            tentativa, self.tentativas, erro)
                if tentativa < self.tentativas:
                    _esperar(tentativa)
                    continue
                return None

            if resposta.status_code == 200:
                try:
                    return self._extrair(resposta.json())
                except ValueError:
                    self._ultimo_motivo = "corpo da resposta não é JSON"
                    log.error("Gemini devolveu HTTP 200 com corpo inválido: %s",
                              (resposta.text or "")[:300])
                    return None

            detalhe = _detalhe_erro(resposta)

            if resposta.status_code == 429:
                espera, diaria, limite = _info_cota(resposta)

                if diaria:
                    self._ultimo_motivo = f"HTTP 429: cota diária esgotada — {detalhe}"
                    log.error("Gemini: cota DIÁRIA da chave esgotada. Esperar segundos não "
                              "resolve; as revisões voltam quando a cota renovar.")
                    return None

                if espera is not None:
                    _fechar_janela_de_cota(espera + _FOLGA_COTA)
                    if primeiro_429 is None:
                        primeiro_429 = time.monotonic()
                    # Relógio de parede, não soma dos "retry in": conta também
                    # o envio de cada tentativa, que num lote grande leva ~15s.
                    decorrido = time.monotonic() - primeiro_429

                    # Requisição maior que a cota inteira nunca cabe numa janela,
                    # por mais que se espere. Uma janela limpa ainda é tentada
                    # (a contagem de lá não bate exatamente com a estimativa
                    # daqui); depois disso, esperar é só segurar a vaga de revisão.
                    estimativa = _tokens_estimados(corpo)
                    grande_demais = bool(limite) and estimativa > limite
                    if grande_demais and esperas_cota == 0:
                        log.warning(
                            "Esta requisição tem ~%d tokens estimados, acima da cota de %d por "
                            "minuto: dificilmente cabe numa janela. Reduza [ia] "
                            "max_tokens_entrada no config.ini.", estimativa, limite,
                        )

                    if grande_demais:
                        pode_esperar = esperas_cota == 0
                    else:
                        pode_esperar = decorrido + espera <= self.espera_maxima_cota

                    if pode_esperar:
                        esperas_cota += 1
                        tentativa -= 1
                        log.warning(
                            "Gemini devolveu HTTP 429: cota por minuto esgotada%s. A API pediu "
                            "%.1fs; o envio fica suspenso até lá (%.0fs de %ds já esperando a "
                            "cota nesta requisição).",
                            f" (limite {limite})" if limite else "", espera,
                            decorrido, self.espera_maxima_cota,
                        )
                        continue

                    self._ultimo_motivo = f"HTTP 429: {detalhe}"
                    log.error(
                        "Gemini: cota por minuto ainda esgotada depois de %.0fs esperando nesta "
                        "requisição. Lote dado como perdido; aumente [ia] espera_maxima_cota "
                        "ou reduza [ia] max_tokens_entrada.", decorrido,
                    )
                    return None

            if resposta.status_code in STATUS_TEMPORARIOS and tentativa < self.tentativas:
                log.warning(
                    "Gemini devolveu HTTP %s (%s). Tentativa %d/%d.",
                    resposta.status_code, detalhe, tentativa, self.tentativas,
                )
                _esperar(tentativa)
                continue

            self._ultimo_motivo = f"HTTP {resposta.status_code}: {detalhe}"
            log.error("Gemini recusou a requisição — HTTP %s: %s", resposta.status_code, detalhe)

            if resposta.status_code == 400:
                # Provável campo não suportado pelo modelo: vale degradar o corpo.
                self._ultima_falha_recuperavel = True
            elif resposta.status_code in (401, 403):
                log.error("Verifique [ia] gemini_api_key no config.ini.")
            elif resposta.status_code == 404:
                log.error("Modelo '%s' não encontrado. Verifique [ia] gemini_modelo.", self._modelo)

            return None

        return None

    def _extrair(self, dados: dict):
        """Puxa o texto da resposta e os metadados úteis."""
        feedback = dados.get("promptFeedback") or {}
        if feedback.get("blockReason"):
            self._ultimo_motivo = f"prompt bloqueado: {feedback['blockReason']}"
            log.error("Gemini bloqueou o prompt (%s).", feedback["blockReason"])
            return None

        candidatos = dados.get("candidates") or []
        if not candidatos:
            self._ultimo_motivo = "resposta sem candidates"
            log.error("Gemini devolveu resposta sem 'candidates': %s", _resumo(dados))
            return None

        candidato = candidatos[0]
        motivo_parada = candidato.get("finishReason", "")

        partes = (candidato.get("content") or {}).get("parts") or []
        texto = "".join(parte.get("text", "") for parte in partes).strip()

        if not texto:
            self._ultimo_motivo = f"resposta vazia (finishReason={motivo_parada or 'desconhecido'})"
            log.error("Gemini devolveu conteúdo vazio (finishReason=%s)", motivo_parada)
            return None

        uso = dados.get("usageMetadata") or {}
        metadados = {
            "truncado": motivo_parada == "MAX_TOKENS",
            "tokens": {
                "entrada": uso.get("promptTokenCount"),
                "saida": uso.get("candidatesTokenCount"),
                "total": uso.get("totalTokenCount"),
            },
        }
        return texto, metadados


# --------------------------------------------------------------------------- #
# Auxiliares                                                                   #
# --------------------------------------------------------------------------- #

def _interpretar_json(texto: str) -> dict | None:
    """Parse do JSON com duas redes de segurança."""
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass

    limpo = texto.strip()
    if limpo.startswith("```"):
        limpo = limpo.split("\n", 1)[-1]
        if limpo.rstrip().endswith("```"):
            limpo = limpo.rstrip()[:-3]
    inicio = limpo.find("{")
    fim = limpo.rfind("}")
    if inicio != -1 and fim > inicio:
        limpo = limpo[inicio:fim + 1]

    try:
        return json.loads(limpo)
    except json.JSONDecodeError:
        pass

    try:
        from json_repair import repair_json
        reparado = repair_json(limpo)
        resultado = json.loads(reparado)
        log.warning("JSON do Gemini precisou de reparo — resposta pode estar incompleta.")
        return resultado if isinstance(resultado, dict) else None
    except Exception as erro:
        log.error("Reparo de JSON falhou: %s", erro)
        return None


def _detalhe_erro(resposta) -> str:
    try:
        dados = resposta.json()
        erro = dados.get("error") or {}
        return erro.get("message") or str(dados)[:300]
    except ValueError:
        return (resposta.text or "")[:300]


def _info_cota(resposta) -> tuple[float | None, bool, int | None]:
    """Do 429: (segundos que a API mandou esperar, cota é diária, limite da cota).

    A espera vem de três jeitos, e serve o primeiro que aparecer: `RetryInfo`
    nos `details` ("34.842950224s"), o "Please retry in 34.84s." no fim da
    mensagem e o cabeçalho `Retry-After`. A `QuotaFailure` diz qual cota
    estourou — `...PerDay...` só volta no dia seguinte, então nem adianta esperar.
    """
    try:
        dados = resposta.json()
    except ValueError:
        dados = {}
    if isinstance(dados, list):
        dados = dados[0] if dados else {}
    erro = (dados.get("error") if isinstance(dados, dict) else None) or {}

    espera = None
    diaria = False
    limite = None

    for item in erro.get("details") or []:
        if not isinstance(item, dict):
            continue
        tipo = str(item.get("@type", ""))
        if tipo.endswith("RetryInfo"):
            espera = _duracao(item.get("retryDelay"))
        elif tipo.endswith("QuotaFailure"):
            for violacao in item.get("violations") or []:
                cota = f"{violacao.get('quotaId', '')} {violacao.get('quotaMetric', '')}".lower()
                if "perday" in cota:
                    diaria = True
                # Só a cota de tokens serve de régua para o tamanho da
                # requisição; a de requisições por minuto tem valor tipo 15.
                if "token" not in cota:
                    continue
                try:
                    limite = int(violacao.get("quotaValue"))
                except (TypeError, ValueError):
                    pass

    if espera is None:
        achado = _RE_RETRY_IN.search(str(erro.get("message") or ""))
        if achado:
            espera = _duracao(achado.group(1) + achado.group(2))

    if espera is None:
        espera = _duracao((resposta.headers or {}).get("Retry-After"))

    return espera, diaria, limite


def _duracao(texto) -> float | None:
    """'34.84s', '332.4ms' ou '30' (Retry-After) em segundos."""
    valor = str(texto or "").strip().lower()
    divisor = 1.0
    if valor.endswith("ms"):
        valor, divisor = valor[:-2], 1000.0
    elif valor.endswith("s"):
        valor = valor[:-1]
    try:
        segundos = float(valor) / divisor
    except ValueError:
        return None
    return segundos if segundos >= 0 else None


def _tokens_estimados(corpo: dict) -> int:
    """Tamanho da requisição pela mesma régua que divide o PR em lotes."""
    textos = [
        parte.get("text", "")
        for bloco in [*(corpo.get("contents") or []), corpo.get("systemInstruction") or {}]
        for parte in (bloco.get("parts") or [])
    ]
    return estimar_tokens("".join(textos))


def _fechar_janela_de_cota(segundos: float) -> None:
    """Marca a cota como esgotada pelos próximos `segundos`, para todas as threads."""
    global _cota_liberada_em
    with _trava_cota:
        _cota_liberada_em = max(_cota_liberada_em, time.monotonic() + segundos)


def _aguardar_janela_de_cota() -> None:
    """Segura o envio enquanto a cota por minuto estiver marcada como esgotada.

    É o que faz o próximo lote esperar a janela reabrir em vez de ser enviado
    logo atrás do que levou 429 — e falhar do mesmo jeito.
    """
    with _trava_cota:
        restante = _cota_liberada_em - time.monotonic()
    if restante > 0:
        log.info("Aguardando %.0fs a cota por minuto do Gemini reabrir antes de enviar.", restante)
        # O jitter evita que as duas vagas de revisão reenviem no mesmo instante.
        time.sleep(restante + random.uniform(0, 1))


def _resumo(dados: dict) -> str:
    return json.dumps(dados, ensure_ascii=False)[:500]


def _esperar(tentativa: int) -> None:
    """Backoff exponencial com jitter, para não sincronizar retentativas.

    Começa em 5s (5, 10, 20, 40, até 60): o 503 "model is currently experiencing
    high demand" é pico de carga do lado do Google, e com 2s e 4s as tentativas
    se esgotavam em menos de dez segundos, ainda dentro do mesmo pico.
    """
    espera = min(5 * 2 ** (tentativa - 1), 60) + random.uniform(0, 1)
    time.sleep(espera)


def _inteiro(variavel: str, padrao: int) -> int:
    try:
        return int(str(os.getenv(variavel, padrao)).strip())
    except (TypeError, ValueError):
        return padrao


def _decimal(variavel: str, padrao: float) -> float:
    try:
        return float(str(os.getenv(variavel, padrao)).strip().replace(",", "."))
    except (TypeError, ValueError):
        return padrao


def _booleano(variavel: str, padrao: bool) -> bool:
    valor = str(os.getenv(variavel, "")).strip().lower()
    if valor in ("1", "true", "sim", "yes", "on"):
        return True
    if valor in ("0", "false", "nao", "não", "no", "off"):
        return False
    return padrao
