"""Agente Google Gemini — backend principal do PyAgent IA.

Chama a Generative Language API via `requests` (sem SDK) e trabalha com saída
estruturada: `responseMimeType: application/json` mais `responseSchema` fazem a
própria API garantir a forma do JSON, o que elimina quase toda a classe de erro
de parse que existia antes.

A chamada degrada em etapas: se o modelo configurado não aceitar `responseSchema`
ou `systemInstruction`, a requisição é refeita sem esses campos em vez de falhar.
"""

import json
import os
import random
import time

import requests

from app.clients.ai.base import BaseAIAgent
from app.clients.ai.prompt_builder import montar_prompt, resposta_vazia, schema_para
from app.core.logger import obter_logger

log = obter_logger(__name__)

URL_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
STATUS_TEMPORARIOS = {429, 500, 502, 503, 504}


class GeminiAgent(BaseAIAgent):
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self._modelo = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite") or "gemini-3.1-flash-lite"
        self.timeout = _inteiro("AI_TIMEOUT", 180)
        self.max_tokens = _inteiro("AI_MAX_TOKENS", 16000)
        self.temperatura = _decimal("AI_TEMPERATURA", 0.0)
        self.tentativas = max(1, _inteiro("AI_TENTATIVAS", 3))
        self.usar_schema = _booleano("AI_SCHEMA_ESTRITO", True)

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

        system_prompt, user_prompt = montar_prompt(
            modo=modo,
            pr_diff=pr_diff,
            commit_messages=commit_messages,
            contexto_arquivos=contexto_arquivos,
            contexto_extra=self.carregar_contexto(),
            arquivos_alterados=kwargs.get("arquivos_alterados"),
            mapa_ancoras=kwargs.get("mapa_ancoras"),
            source_branch=kwargs.get("source_branch", "origem"),
            dest_branch=kwargs.get("dest_branch", "destino"),
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
        """
        cabecalhos = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        self._ultima_falha_recuperavel = False

        for tentativa in range(1, self.tentativas + 1):
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


def _resumo(dados: dict) -> str:
    return json.dumps(dados, ensure_ascii=False)[:500]


def _esperar(tentativa: int) -> None:
    """Backoff exponencial com jitter, para não sincronizar retentativas."""
    espera = min(2 ** tentativa, 20) + random.uniform(0, 1)
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
