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
_ARTIGO = re.compile(r"\bart(?:igo)?s?\.?\s*(?P<num>[\dOolISs]+)\s*[º°o]?", re.IGNORECASE)
_PARAGRAFO_UNICO = re.compile(r"par[aá]grafo\s+[uú]nico|§\s*[uú]nico", re.IGNORECASE)
_PARAGRAFO = re.compile(r"(?:§|par[aá]grafo)\s*(?P<num>[\dOolISs]+)\s*[º°o]?", re.IGNORECASE)
_INCISO = re.compile(r"\binc(?:iso)?\.?\s*(?P<num>[IVXLCM]+)\b", re.IGNORECASE)
_ALINEA = re.compile(r"\bal[ií]nea\.?\s*[\"'“]?(?P<letra>[a-zA-Z])[\"'”]?\b")


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
    # do processo — todos os dígitos do trecho, já com OCR corrigido. Exige
    # um mínimo de 5 dígitos (o menor número real visto no goldenset, "Rcl
    # 66.516" — Analise_Exploratoria.docx §c) para não tratar um ano solto
    # ("...proferido em 2024...", típico de menção vaga) como se fosse um
    # número de processo buscável.
    digitos_brutos = "".join(c for c in corrigido if c.isdigit())
    numero = digitos_brutos if len(digitos_brutos) >= 5 else None
    campos = CamposIdentificador(
        numero_normalizado=numero,
        classe=classe_principal,
        classes_compostas=classes,
        tribunal=tribunal,
        uf=uf,
        variantes_texto=_variantes(classes, None),
    )
    return campos, ocr_corrigido
