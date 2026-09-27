"""Nó `extrair_spans` — Módulo 1 (Extração), docs/arquitetura.md.

Duas camadas determinísticas e um esqueleto para o agente LLM:

- camada 1 (regex): citações com identificador (lei, súmula, tema,
  jurisprudência com classe + número, CNJ solto, forma do TST);
- camada 2 (heurística): citações sem identificador no modelo "gatilho do
  TRIBUNAL, de ANO, relatoria de NOME" (as incompletas do gabarito) e
  classes por extenso com número, como rede de segurança.

Regras de fronteira, conferidas contra `goldenset_offsets.csv`:

- espaço entre palavras pode ter no máximo uma quebra de linha; linha em
  branco separa parágrafos e nunca fica dentro de um span;
- o span termina no identificador (ou na UF) e na incompleta, no nome do
  relator — nunca em pontuação ou espaço;
- entre spans que se sobrepõem com IoU >= 0,5, fica o da camada mais
  confiável e, empatado, o mais longo ("Terceiro AG.REG na Rcl nº ..." vence
  "Rcl nº ...", "processo nº TST-RR-..." vence o CNJ sozinho).

O ruído do Nível 2 aparece também aqui: letra no lugar de dígito dentro do
número (O/l/S/G/g), espaço não separável e quebra de linha no meio do
número. A normalização do número fica com `dominio/chave.py`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from citacoes.dominio.cabecalho import extrair_cabecalho
from citacoes.dominio.lexico import CLASSES_PROCESSUAIS, UFS
from citacoes.grafo.estados import EstadoCitacao, EstadoDocumento

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

    from citacoes.grafo.estados import Contexto


# ── blocos de regex ─────────────────────────────────────────────────────────

_H = r"[ \t ]"  # espaço horizontal (o Nível 2 usa espaço não separável)
_V = rf"{_H}*\n?{_H}*"  # espaço opcional com no máximo uma quebra de linha
_WS = rf"(?:{_H}+\n?{_H}*|\n{_H}*)"  # espaço obrigatório, no máximo uma quebra

_CONFUNDIVEL = r"[\dOoIlSsGg]"
_GRUPO_COM_DIGITO = rf"{_CONFUNDIVEL}*\d{_CONFUNDIVEL}*"
_GRUPO = rf"{_CONFUNDIVEL}+"
_SEP_PONTUACAO = rf"(?:{_V}[.\-]){{1,2}}{_V}"
_SEP_ESPACO = rf"(?:{_H}{{1,2}}|{_H}*\n{_H}*)"
# Número de processo: grupos ligados por "." / "-" (com o espaço solto do
# Nível 2) ou só por espaço, quando o grupo seguinte também tem dígito.
_NUMERO = rf"{_GRUPO_COM_DIGITO}(?:{_SEP_PONTUACAO}{_GRUPO}|{_SEP_ESPACO}{_GRUPO_COM_DIGITO})*"

_UF_ALT = "|".join(sorted(UFS))
_UF = (
    rf"(?:{_H}*/{_H}*(?-i:{_UF_ALT})\b"
    rf"|{_V}-{_H}*(?-i:{_UF_ALT})\b"
    rf"|{_V}\({_H}*(?-i:{_UF_ALT}){_H}*\))?"
)

# "nº", "n°", "No", "N.", "n." — sempre seguido de dígito (ou letra de OCR).
_PREFIXO_N = rf"(?:n(?:[º°o]|\.)?\.?{_V}(?={_CONFUNDIVEL}))?"


def _flexivel(variante: str) -> str:
    """Variante do léxico com espaço flexível entre as palavras; o ponto
    final de uma abreviação é opcional ("AG.REG na Rcl")."""
    padrao = _WS.join(re.escape(p) for p in variante.split())
    return padrao[:-2] + r"\.?" if variante.endswith(".") else padrao


_VARIANTES_CLASSE = sorted(
    {v for vs in CLASSES_PROCESSUAIS.values() for v in vs},
    key=len,
    reverse=True,
)
_CLASSE = (
    r"(?<![\w.])(?:" + "|".join(_flexivel(v) for v in _VARIANTES_CLASSE) + r")(?:(?<=\.)|\.?(?!\w))"
)
_ORDINAL = r"(?:Primeir[oa]|Segund[oa]|Terceir[oa]|Quart[oa]|Quint[oa])"
_CONECTOR = rf"(?:{_WS}(?:no|na|nos|nas|em){_WS}|{_H}?-{_H}?)"
_CLASSE_COMPOSTA = rf"(?:{_ORDINAL}{_WS})?{_CLASSE}(?:{_CONECTOR}{_CLASSE})*"

_DIPLOMA = (
    r"(?:"
    r"Lei\s+(?:Complementar\s+)?n[º°o]?\.?\s*[\d\.\s]+[/\s]\d{4}"
    r"|C[oó]digo\s+de\s+Processo\s+Penal\s+Militar"
    r"|C[oó]digo\s+Penal\s+Militar"
    r"|C[oó]digo\s+(?:de\s+)?(?:Processo\s+)?(?:Civil|Penal|Eleitoral"
    r"|Defesa\s+do\s+Consumidor|Tribut[aá]rio\s+Nacional)"
    r"|Consolida[çc][aã]o\s+das\s+Leis\s+do\s+Trabalho"
    # "Federal" com ruído de letra ("Fedcral") ainda fecha o nome.
    r"|Constitui[çc][aã]o(?:\s+F[a-zç]{5,7}\b|\s+da\s+Rep[uú]\w{3,6}\b)?"
    r"|Estatuto\s+da\s+Crian[çc]a\s+e\s+do\s+Adolescente"
    r"|CLT|CPC|CPPM|CP(?:P|M)?|CDC|CTN|ECA|CF"
    r")"
)

_LEI_RE = re.compile(
    r"art(?:igo)?s?\.?\s*\n?\s*"
    r"[\d\.OoIlSs]+[º°o]?"
    r"(?:"
    r"[,\s]*(?:[§IVXLivxl]+|\d+)[º°o]?(?:-[A-Z])?"
    r"|[,\s]+['\"][a-z]['\"]"
    r")*"
    r"(?:"
    r"[,\s\n]+(?:d[aoe]\s+)?"
    rf"(?:{_DIPLOMA})"
    r")?",
    re.IGNORECASE,
)

_TRIBUNAL_SIGLA = r"(?:STF|STJ|TST|TSE|STM)"

_SUMULA_RE = re.compile(
    rf"(?<!\w)[S5][uú]m(?:ula)?\.?{_WS}"
    rf"(?:Vinculante{_WS})?"
    rf"(?:n[º°o]?\.?{_V})?"
    rf"{_NUMERO}"
    rf"(?:{_WS}d[aoe]{_WS}{_TRIBUNAL_SIGLA})?",
    re.IGNORECASE,
)

# Tema de repercussão geral: a base não tem temas, então a citação é
# resolvida contra o catálogo e, sem candidato, vira inventada.
_TEMA_RE = re.compile(
    rf"(?<!\w)Tem[aã]{_WS}(?:n[º°o]?\.?{_V})?{_NUMERO}"
    rf"(?:{_WS}d[ao]{_WS}repercuss[aã]o{_WS}geral)?",
    re.IGNORECASE,
)

# Classe (ou cadeia de classes) + número.
_JURIS_RE = re.compile(
    rf"{_CLASSE_COMPOSTA}{_V}{_PREFIXO_N}{_NUMERO}{_UF}",
    re.IGNORECASE,
)

# CNJ sem classe na frente: NNNNNNN-DD.AAAA.J.TR.OOOO, com ruído.
_CNJ_CORPO = (
    rf"{_CONFUNDIVEL}{{1,7}}{_SEP_PONTUACAO}{_CONFUNDIVEL}{{2}}{_SEP_PONTUACAO}"
    rf"{_CONFUNDIVEL}{{4}}{_SEP_PONTUACAO}{_CONFUNDIVEL}{_SEP_PONTUACAO}"
    rf"{_CONFUNDIVEL}{{2}}{_SEP_PONTUACAO}{_CONFUNDIVEL}{{4}}"
)
_CNJ_RE = re.compile(rf"(?<![\w.\-]){_CNJ_CORPO}(?![\w]){_UF}", re.IGNORECASE)

# Forma do TST/TSE com siglas ligadas por hífen ao CNJ:
# "processo nº TST-ED-E-ED-RR-3400-05.2011.5.21.0009", "ARR-213-85.2010...".
# Sem IGNORECASE nas siglas: com ele, o fim de "ignorar" virava a sigla "ar".
_TST_RE = re.compile(
    rf"(?:(?i:processo){_H}+(?i:n[º°o]?\.?){_H}*)?"
    rf"(?<![\w\-])(?:[A-Z][A-Za-z]{{0,5}}{_H}*-{_H}*)+"
    rf"{_CNJ_CORPO}(?!\w){_UF}"
)

_EXTRATORES_REGEX: tuple[tuple[re.Pattern[str], str], ...] = (
    (_LEI_RE, "lei"),
    (_SUMULA_RE, "jurisprudencia"),
    (_TEMA_RE, "jurisprudencia"),
    (_CNJ_RE, "jurisprudencia"),
    (_JURIS_RE, "jurisprudencia"),
    (_TST_RE, "jurisprudencia"),
)


# ── camada 2: citação sem identificador ─────────────────────────────────────

_GATILHO = (
    r"(?:julgado|precedente|ac[óo]rd[ãa]o|decis[ãa]o"
    r"|entendimento(?:\s+(?:sumulado|consolidado|firmado|pac[íi]fico))?)"
)
_SEM_NUMERO = r"(?:[^\d.;\n]|\n(?![ \t ]*\n))"
_MEIO_COM_ANO = rf"{_SEM_NUMERO}{{0,60}}?(?:19|20)\d{{2}}{_SEM_NUMERO}{{0,40}}?"
_RELATORIA = (
    rf"(?i:(?:(?:da|sob|pela){_WS})?relatoria{_WS}d\w"
    rf"|Rel\.{_V}(?:Min(?:istr[oa])?\.?)?)"
)
_PALAVRA_NOME = r"[A-ZÀ-ÖØ-Þ][\wÀ-ÿ'’\-]*"
_PARTICULA = r"d[aeo]s?"
_NOME = rf"{_PALAVRA_NOME}(?:{_WS}(?:{_PARTICULA}{_WS})?{_PALAVRA_NOME})*"

# "julgado do STF proferido em 2024 pela relatoria de Dias Toffoli",
# "Rcl de 2025, Rel. Min. CÁRMEN LÚCIA", "Agravo em Recurso Especial do STJ,
# de 2023, Rel. Min. Assusete Magalhães". O nome do relator é uma sequência
# de palavras com inicial maiúscula (e partículas "de", "da"...), então o
# span para antes do texto que segue (", no ponto em que...").
_INCOMPLETA_RE = re.compile(
    rf"(?<!\w)(?:(?i:{_GATILHO})|(?i:{_CLASSE_COMPOSTA}))"
    rf"{_MEIO_COM_ANO}{_RELATORIA}{_V}{_NOME}"
)

_CLASSE_EXTENSO_RE = re.compile(
    r"(?:Agravo[\s\n]+(?:Regimental|Interno|em[\s\n]+Recurso[\s\n]+Especial)"
    r"|Embargos?[\s\n]+de[\s\n]+Declara[çc][aã]o"
    r"|Recurso[\s\n]+em[\s\n]+(?:Habeas[\s\n]+Corpus|Mandado[\s\n]+de[\s\n]+Segurança)"
    r"|Agravo[\s\n]+de[\s\n]+Instrumento"
    r"|Suspens[aã]o[\s\n]+de[\s\n]+Liminar)"
    r"(?:[\s\n]+(?:no|na|nos|nas|em|do|da))*[\s\n]+"
    r"(?:[A-Z][\w\s\n]+[\s\n]+)?"
    rf"{_PREFIXO_N}{_NUMERO}{_UF}",
    re.IGNORECASE,
)


# ── spans ───────────────────────────────────────────────────────────────────

_SPAN_MINIMO = 8
_PRIORIDADE = {"regex_camada1": 0, "heuristica_camada2": 1, "agente_extrator_llm": 2}
_FIM_DESCARTAVEL = " \t \r\n.,;:-"


def _novo_span(
    texto: str, inicio: int, fim: int, tipo: str, tem_id: bool, origem: str
) -> EstadoCitacao | None:
    while fim > inicio and texto[fim - 1] in _FIM_DESCARTAVEL:
        fim -= 1
    while inicio < fim and texto[inicio] in _FIM_DESCARTAVEL:
        inicio += 1
    if fim <= inicio:
        return None
    return EstadoCitacao(
        inicio=inicio,
        fim=fim,
        trecho=texto[inicio:fim],
        tipo_bruto=tipo,
        tem_identificador=tem_id,
        origem=origem,
    )


def _filtrar_curtos(spans: list[EstadoCitacao]) -> list[EstadoCitacao]:
    return [s for s in spans if (s.fim - s.inicio) >= _SPAN_MINIMO]


def _iou(a: EstadoCitacao, b: EstadoCitacao) -> float:
    overlap = max(0, min(a.fim, b.fim) - max(a.inicio, b.inicio))
    union = max(a.fim, b.fim) - min(a.inicio, b.inicio)
    return overlap / union if union > 0 else 0.0


def _deduplicar(spans: list[EstadoCitacao]) -> list[EstadoCitacao]:
    """Um span por região de IoU >= 0,5 (ou contido em outro já mantido):
    primeiro a camada, depois o mais longo, depois o que começa antes
    (desempate determinístico)."""
    ordenados = sorted(
        spans, key=lambda s: (_PRIORIDADE.get(s.origem, 99), -(s.fim - s.inicio), s.inicio)
    )
    mantidos: list[EstadoCitacao] = []
    for span in ordenados:
        if any(_iou(span, k) >= 0.5 or _contido(span, k) for k in mantidos):
            continue
        mantidos.append(span)
    return mantidos


def _contido(span: EstadoCitacao, maior: EstadoCitacao) -> bool:
    """O CNJ dentro de "Recurso Especial Eleitoral nº <CNJ>" é o mesmo
    identificador, não outra citação."""
    return maior.inicio <= span.inicio and span.fim <= maior.fim


# ── distratores ─────────────────────────────────────────────────────────────

_DISTRATOR_RE = re.compile(
    r"Protocolo\s+n[º°o]?\.?\s*\d"
    r"|\bOAB[/\s]\w+"
    r"|\bfls?\.\s*\d"
    r"|R\$\s*[\d\.,]+",
    re.IGNORECASE,
)
_CNJ_LIMPO = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
# Número dos autos do próprio documento ("Referência: autos nº ...").
_AUTOS_PROPRIOS = re.compile(r"\bautos\s+n[º°o]?\.?\s*$", re.IGNORECASE)


def _e_distrator(span: EstadoCitacao, cabecalho_fim: int, texto: str = "") -> bool:
    margem = cabecalho_fim + 50  # tolerância para \n depois do CNJ
    if span.inicio < margem and _CNJ_LIMPO.search(span.trecho):
        return True
    if texto and _AUTOS_PROPRIOS.search(texto[max(0, span.inicio - 20) : span.inicio]):
        return True
    return bool(_DISTRATOR_RE.match(span.trecho))


# ── camadas ─────────────────────────────────────────────────────────────────


def _extrair_regex(texto: str) -> list[EstadoCitacao]:
    spans = []
    for padrao, tipo in _EXTRATORES_REGEX:
        for m in padrao.finditer(texto):
            span = _novo_span(texto, m.start(), m.end(), tipo, True, "regex_camada1")
            if span is not None:
                spans.append(span)
    return spans


def _extrair_heuristica(texto: str) -> list[EstadoCitacao]:
    spans = []
    for padrao, tem_id in ((_INCOMPLETA_RE, False), (_CLASSE_EXTENSO_RE, True)):
        for m in padrao.finditer(texto):
            span = _novo_span(
                texto, m.start(), m.end(), "jurisprudencia", tem_id, "heuristica_camada2"
            )
            if span is not None:
                spans.append(span)
    return spans


def _extrair_llm(texto: str, modelo: object) -> list[EstadoCitacao]:
    return []


def extrair(texto: str, modelo: object | None = None) -> list[EstadoCitacao]:
    """Lógica pura do nó: spans candidatos, sem distratores nem duplicatas."""
    cabecalho_fim = len(extrair_cabecalho(texto))
    spans = _extrair_regex(texto) + _extrair_heuristica(texto)
    if modelo is not None:
        spans += _extrair_llm(texto, modelo)
    spans = _filtrar_curtos(spans)
    spans = [s for s in spans if not _e_distrator(s, cabecalho_fim, texto)]
    return _deduplicar(spans)


def extrair_spans(estado: EstadoDocumento, runtime: Runtime[Contexto]) -> dict:
    contexto = runtime.context
    modelo = contexto.modelo_llm if contexto.usar_extrator_llm else None
    return {"spans": extrair(estado.texto, modelo)}
