from __future__ import annotations
import re
from typing import TYPE_CHECKING
from citacoes.dominio.cabecalho import extrair_cabecalho
from citacoes.dominio.lexico import CLASSES_PROCESSUAIS, TRIBUNAIS
from citacoes.grafo.estados import EstadoCitacao, EstadoDocumento

if TYPE_CHECKING:
    from langgraph.runtime import Runtime
    from citacoes.grafo.estados import Contexto


##  --------------------Deduplicação por IoU--------------------------

def _iou(a: EstadoCitacao, b: EstadoCitacao) -> float:
    overlap = max(0, min(a.fim, b.fim) - max(a.inicio, b.inicio))
    union = max(a.fim, b.fim) - min(a.inicio, b.inicio)
    return overlap / union if union > 0 else 0.0


_PRIORIDADE = {"regex_camada1": 0, "heuristica_camada2": 1, "agente_extrator_llm": 2}


def _deduplicar(spans: list[EstadoCitacao]) -> list[EstadoCitacao]:
    """mantem so um span por região IoU >= 0.5 --> prioriza regex."""
    ordenados = sorted(spans, key=lambda s: _PRIORIDADE.get(s.origem, 99))
    mantidos: list[EstadoCitacao] = []
    for span in ordenados:
        if not any(_iou(span, k) >= 0.5 for k in mantidos):
            mantidos.append(span)
    return mantidos

## ------------------ Filtro distratores-------------------------------
_DISTRATOR_RE = re.compile(
    r"Protocolo\s+n[º°o]?\.?\s*\d"
    r"|\bOAB[/\s]\w+"
    r"|\bfls?\.\s*\d"
    r"|R\$\s*[\d\.,]+",
    re.IGNORECASE,
)

_CNJ_LIMPO = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")


def _e_distrator(span: EstadoCitacao, cabecalho_fim: int) -> bool:
    if span.inicio < cabecalho_fim and _CNJ_LIMPO.search(span.trecho):
        return True
    return bool(_DISTRATOR_RE.match(span.trecho))



### ---------------------- CAMADA 1 REGEX----------------------------: 

#  nº, n°, No, N., etc.
_PREFIX_N = r"(?:[Nn][º°o]?\.?\s*)?"

_UF = r"(?:[\s/\-\(]+[A-Z]{2}\)?)?"

_DIPLOMA = (
    r"Lei\s+(?:Complementar\s+)?n[º°o]?\.?\s*[\d\.\s]+[/\s]\d{4}"
    r"|C[oó]digo[\s\w]{0,40}"
    r"|Consolida[çc][aã]o\s+das\s+Leis\s+do\s+Trabalho"
    r"|Constitui[çc][aã]o[\s\w\n]{0,40}"
    r"|CLT|CPC|CP(?:P|M)?|CDC|CTN|ECA|Código\s+Eleitoral"
)

# Lei: art./artigo + número + incisos + diploma
_LEI_RE = re.compile(
    r"art(?:igo)?s?\.?\s*\n?\s*"
    r"[\d\.OoIlSs]+[º°o]?"
    r"(?:[,\s]*(?:[§IVXLivxl]+|\d+)[º°o]?(?:-[A-Z])?"
    r"|[,\s]+['\"]?[a-z]['\"]?)*"
    r"(?:[,\s\n]+(?:d[aoe]\s+)?(?:" + _DIPLOMA + r"))?",
    re.IGNORECASE,
)

_SUMULA_RE = re.compile(
    r"S[uú]m(?:ula)?\.?\s+"
    r"(?:Vinculante\s+)?"
    r"n?[º°o]?\.?\s*"
    r"[\d\.OoIlSs]+"
    r"(?:\s+d[aoe]\s+(?:STF|STJ|TST|TSE|STM))?",
    re.IGNORECASE,
)


_VARIANTES = sorted(
    (v for vs in CLASSES_PROCESSUAIS.values() for v in vs),
    key=len,
    reverse=True,
)

_CLASSE = "|".join(re.escape(v) for v in _VARIANTES)
_CONECTOR = r"(?:\s+(?:no|na|nos|nas|em)\s+)"
_CLASSE_COMP = rf"(?:{_CLASSE})(?:{_CONECTOR}(?:{_CLASSE}))*"

_NUM_CURTO = r"[\d\.OoIlSs]+(?:[\s\-]+[\d\.OoIlSs]+)*"

_JURIS_CURTO_RE = re.compile(
    rf"(?:{_CLASSE_COMP})\s*\n?\s*{_PREFIX_N}(?:{_NUM_CURTO}){_UF}",
    re.IGNORECASE,
)

_CNJ_RE = re.compile(
    rf"(?:(?:{_CLASSE_COMP})\s*\n?\s*{_PREFIX_N})?"
    r"[\dOoIlSs]{5,7}"
    r"[\s\n]*[\-]{1,2}[\s\n]*"
    r"[\dOoIlSs]{2}"
    r"[\s\n]*\.[\s\n]*"
    r"[\dOoIlSs]{4}"
    r"[\s\n]*\.[\s\n]*"
    r"[\dOoIlSs]"
    r"[\s\n]*\.[\s\n]*"
    r"[\dOoIlSs]{2}"
    r"[\s\n]*\.[\s\n]*"
    r"[\dOoIlSs]{4}"
    rf"{_UF}",
    re.IGNORECASE,
)

def _make_span(m: re.Match, texto: str, tipo: str) -> EstadoCitacao:
    return EstadoCitacao(
        inicio=m.start(),
        fim=m.end(),
        trecho=texto[m.start() : m.end()],
        tipo_bruto=tipo,
        tem_identificador=True,
        origem="regex_camada1",
    )


def _extrair_regex(texto: str) -> list[EstadoCitacao]:
    spans = []
    for m in _LEI_RE.finditer(texto):
        spans.append(_make_span(m, texto, "lei"))
    for m in _SUMULA_RE.finditer(texto):
        spans.append(_make_span(m, texto, "jurisprudencia"))
    for m in _CNJ_RE.finditer(texto):
        spans.append(_make_span(m, texto, "jurisprudencia"))
    for m in _JURIS_CURTO_RE.finditer(texto):
        spans.append(_make_span(m, texto, "jurisprudencia"))
    return spans


_GATILHOS = (
    r"(?:julgado|acórdão|decisão|precedente"
    r"|entendimento\s+(?:sumulado|consolidado|firmado|pacífico))"
)

_TRIBUNAIS_PAT = "|".join(
    re.escape(v)
    for vs in TRIBUNAIS.values()
    for v in sorted(vs, key=len, reverse=True)
)

# citação vaga: gatilho + tribunal sem nº
# ex: "julgado do STF proferido em 2021 pela relatoria de Rosa Weber"
_VAGO_RE = re.compile(
    rf"(?:{_GATILHOS})"
    rf"[\s\n]+(?:d[aoe]\s+)?(?:{_TRIBUNAIS_PAT})"
    r"[^\.\n]{0,100}",
    re.IGNORECASE,
)

# classe + ano + relator sem nº
# ex: "Rcl de 2025, Rel. Min. CÁRMEN LÚCIA"
_CLASSE_VAGO_RE = re.compile(
    rf"(?:{_CLASSE_COMP})"
    r"\s+de\s+\d{{4}}"
    r"(?:[,\s]+Rel\.?\s+(?:Min\.?\s+)?[A-ZÁÉÍÓÚ][\w\s]{{0,40}})?",
    re.IGNORECASE,
)


def _extrair_heuristica(texto: str) -> list[EstadoCitacao]:
    spans = []
    for m in _VAGO_RE.finditer(texto):
        spans.append(EstadoCitacao(
            inicio=m.start(),
            fim=m.end(),
            trecho=texto[m.start() : m.end()],
            tipo_bruto="jurisprudencia",
            tem_identificador=False,
            origem="heuristica_camada2",
        ))
    for m in _CLASSE_VAGO_RE.finditer(texto):
        spans.append(EstadoCitacao(
            inicio=m.start(),
            fim=m.end(),
            trecho=texto[m.start() : m.end()],
            tipo_bruto="jurisprudencia",
            tem_identificador=False,
            origem="heuristica_camada2",
        ))
    return spans