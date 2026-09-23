"""Estrutura de campos extraída de um identificador (Módulo 2, saída final).

`CamposIdentificador` é o que `nos/normalizar.py` preenche em
`EstadoCitacao.campos` (docs/contratos.md) e o que `catalogo/construir.py`
extrai do cabeçalho de cada registro — a mesma função, aplicada nos dois
lados, é o que garante que citação e catálogo cheguem à mesma chave.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from citacoes.dominio.chave import (
    classes_processuais,
    corrigir_ocr_numerico,
    diploma_legal,
    extrair_uf,
    tribunal_citado,
)


@dataclass(frozen=True)
class CamposIdentificador:
    """Ver docs/contratos.md — "EstadoCitacao.campos"."""

    numero_normalizado: str | None = None
    classe: str | None = None
    classes_compostas: tuple[str, ...] = ()
    tribunal: str | None = None
    uf: str | None = None
    diploma: str | None = None
    artigo: str | None = None
    paragrafo: str | None = None
    inciso: str | None = None
    alinea: str | None = None
    sumula: str | None = None
    vinculante: bool = False
    # Atributos raramente presentes no próprio trecho citado (mais comuns
    # como coluna do catálogo) — ficam aqui para o mesmo tipo servir aos
    # dois lados; normalizar() não costuma preenchê-los.
    ano: int | None = None
    relator: str | None = None
    orgao: str | None = None
    variantes_texto: tuple[str, ...] = field(default_factory=tuple)


_SUMULA = re.compile(
    r"s[uú]mula\s+(?P<vinculante>vinculante\s+)?n?[º°o]?\.?\s*(?P<num>[\dOolISs]+)",
    re.IGNORECASE,
)
# Número do artigo: dígitos agrupados de 3 em 3 por ponto de milhar
# ("1.134") OU uma cadeia sem separador ("927") — nessa ordem, senão o milhar
# casa só o primeiro grupo ("1.134" -> "1", perdendo os outros dígitos).
_ARTIGO = re.compile(
    r"\bart(?:igo)?s?\.?\s*(?P<num>[\dOolISs]{1,3}(?:\.[\dOolISs]{3})+|[\dOolISs]+)\s*[º°o]?",
    re.IGNORECASE,
)
_PARAGRAFO_UNICO = re.compile(r"par[aá]grafo\s+[uú]nico|§\s*[uú]nico", re.IGNORECASE)
_PARAGRAFO = re.compile(r"(?:§|par[aá]grafo)\s*(?P<num>[\dOolISs]+)\s*[º°o]?", re.IGNORECASE)
_INCISO = re.compile(r"\binc(?:iso)?\.?\s*(?P<num>[IVXLCM]+)\b", re.IGNORECASE)
_ALINEA = re.compile(r"\bal[ií]nea\.?\s*[\"'“]?(?P<letra>[a-zA-Z])[\"'”]?\b")
# Uma cadeia numérica (dígitos ligados por "." ou "-", sem espaço) — mesma
# ideia de dominio.chave._CADEIA_NUMERICA, mas já sobre o texto pós-OCR
# (só dígitos e pontuação interna, letra confundível já virou dígito).
_CADEIA_NUMERO = re.compile(r"\d(?:[\d.\-]*\d)?")
# Acima disto, `trecho` é cabeçalho de catálogo, não span de citação — ver
# extrair_campos(). O maior trecho do goldenset tem 84 caracteres; o menor
# cabeçalho real (extrair_cabecalho sobre desafio1_bracis.db) tem 172 —
# folga de sobra dos dois lados para não confundir um com o outro.
_LIMITE_TRECHO_CURTO = 120


def _so_digitos(bruto: str) -> str | None:
    corrigido, _ = corrigir_ocr_numerico(bruto)
    digitos = "".join(c for c in corrigido if c.isdigit())
    return digitos or None


def _variantes(classes: tuple[str, ...], diploma: str | None) -> tuple[str, ...]:
    from citacoes.dominio.lexico import CLASSES_PROCESSUAIS, DIPLOMAS

    todas: list[str] = []
    for c in classes:
        todas.extend(CLASSES_PROCESSUAIS.get(c, ()))
    if diploma:
        todas.extend(DIPLOMAS.get(diploma, ()))
    return tuple(dict.fromkeys(todas))  # remove duplicatas, preserva ordem


def extrair_campos(trecho: str, tipo_bruto: str) -> tuple[CamposIdentificador, bool]:
    """Núcleo do Módulo 2: `trecho` -> (`CamposIdentificador`, `ocr_corrigido`).

    `tipo_bruto` decide qual identificador se espera (número de processo
    para jurisprudência, artigo/parágrafo/inciso/alínea para lei); súmula é
    reconhecida em qualquer um dos dois, porque no banco ela tem
    `tipo="jurisprudencia"` mas é resolvida como o dicionário de leis
    (ver catalogo/README e Plano_de_acao.docx §3.3).
    """
    corrigido, ocr_corrigido = corrigir_ocr_numerico(trecho)
    classes = classes_processuais(trecho)
    tribunal = tribunal_citado(trecho)
    uf = extrair_uf(trecho)
    classe_principal = classes[-1] if classes else None

    m_sumula = _SUMULA.search(corrigido)
    if m_sumula:
        campos = CamposIdentificador(
            classe="Súmula",
            classes_compostas=classes,
            tribunal=tribunal,
            uf=uf,
            sumula=_so_digitos(m_sumula.group("num")),
            vinculante=bool(m_sumula.group("vinculante")),
            variantes_texto=_variantes(classes, None),
        )
        return campos, ocr_corrigido

    if tipo_bruto == "lei":
        diploma = diploma_legal(trecho)
        m_art = _ARTIGO.search(corrigido)
        m_par = _PARAGRAFO.search(corrigido)
        m_inc = _INCISO.search(corrigido)
        m_al = _ALINEA.search(corrigido)
        campos = CamposIdentificador(
            classe=classe_principal,
            classes_compostas=classes,
            tribunal=tribunal,
            uf=uf,
            diploma=diploma,
            artigo=_so_digitos(m_art.group("num")) if m_art else None,
            paragrafo=(
                "único"
                if _PARAGRAFO_UNICO.search(corrigido)
                else (_so_digitos(m_par.group("num")) if m_par else None)
            ),
            inciso=m_inc.group("num").upper() if m_inc else None,
            alinea=m_al.group("letra").lower() if m_al else None,
            variantes_texto=_variantes(classes, diploma),
        )
        return campos, ocr_corrigido

    # jurisprudência (ou tipo ainda indefinido): o identificador é o número
    # do processo. Um trecho curto (span do Módulo 1, no máximo ~84
    # caracteres no goldenset) já veio recortado para conter só o próprio
    # identificador — concatena todos os dígitos, o que também absorve sem
    # esforço o ruído de Nível 2 (espaço solto/quebra de linha dentro do
    # número, dominio/ruido.py). Um trecho longo é o cabeçalho de um
    # registro do catálogo (dominio/cabecalho.py) — aí não dá para
    # concatenar tudo: mistura data de julgamento, número de turma e o
    # número de outro processo citado ali dentro (ex.: "Reclamação" contra
    # decisão de origem, que traz o próprio número CNJ do processo de
    # origem) com o número do próprio registro. Usa em vez disso a primeira
    # cadeia numérica (dígitos ligados por "." ou "-", já com OCR corrigido)
    # com um mínimo de 5 dígitos (o menor número real visto no goldenset,
    # "Rcl 66.516" — Analise_Exploratoria.docx §c) — a primeira cadeia é
    # sempre a do próprio registro, nunca a de algo citado depois dela.
    if len(corrigido) <= _LIMITE_TRECHO_CURTO:
        digitos_brutos = "".join(c for c in corrigido if c.isdigit())
        numero = digitos_brutos if len(digitos_brutos) >= 5 else None
    else:
        numero = None
        for m_num in _CADEIA_NUMERO.finditer(corrigido):
            digitos = "".join(c for c in m_num.group(0) if c.isdigit())
            if len(digitos) >= 5:
                numero = digitos
                break
    campos = CamposIdentificador(
        numero_normalizado=numero,
        classe=classe_principal,
        classes_compostas=classes,
        tribunal=tribunal,
        uf=uf,
        variantes_texto=_variantes(classes, None),
    )
    return campos, ocr_corrigido
