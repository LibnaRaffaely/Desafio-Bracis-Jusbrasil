"""Tipos do catálogo canônico (Módulo 3) — ver docs/contratos.md.

Só estrutura de dados aqui, sem I/O (SQLite fica em `construir.py`) — para
que `nos/buscar_no_catalogo.py` e os testes possam montar um
`CatalogoCanonico` sintético sem tocar em banco nenhum.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from citacoes.dominio.campos import CamposIdentificador

Natureza = Literal["acordao", "sumula", "dispositivo"]
TipoDocumento = Literal["jurisprudencia", "lei"]


@dataclass(frozen=True)
class RegistroCatalogo:
    """Um registro de `documentos`, já com os campos do seu próprio
    cabeçalho extraídos pela mesma `extrair_campos` usada na citação."""

    id: int
    documento_id: str
    natureza: Natureza
    tipo: TipoDocumento
    tribunal: str | None
    ano: int | None
    relator: str | None
    campos: CamposIdentificador
    # sha1(texto) — permite ao Módulo 4 diferenciar colisão de chave por
    # duplicata real (mesmo texto) de colisão por metadados iguais e texto
    # diferente (RELATORIO_MODULO4.md §8: das 14 colisões do catálogo, 9 são
    # duplicata e 5 não são). `None` só em registros construídos à mão sem
    # o texto (testes) — nunca em registro vindo de `construir_registro`.
    hash_texto: str | None = None


@dataclass(frozen=True)
class Candidato:
    """Ver docs/contratos.md — "Campo de Candidato"."""

    id: int
    tribunal: str | None
    natureza: Natureza
    score: float
    conflitos_duros: tuple[str, ...] = ()
    divergencias_brandas: tuple[str, ...] = ()


def _score_lei_sumula(consulta: CamposIdentificador, registro: CamposIdentificador) -> float:
    """Matching de leis/súmulas por texto normalizado — sem embeddings, sem
    modelo semântico (Plano_de_acao.docx §3.3). Súmula casa pelo número (e
    penaliza, sem descartar, divergência de vinculante); artigo de lei casa
    por diploma+número, penalizando parágrafo/inciso divergentes."""
    if consulta.sumula is not None:
        if registro.sumula != consulta.sumula:
            return 0.0
        return 0.5 if consulta.vinculante != registro.vinculante else 1.0

    if consulta.artigo is not None:
        if registro.artigo != consulta.artigo:
            return 0.0
        if consulta.diploma and registro.diploma and consulta.diploma != registro.diploma:
            return 0.0
        score = 1.0
        if consulta.paragrafo and registro.paragrafo and consulta.paragrafo != registro.paragrafo:
            score -= 0.3
        if consulta.inciso and registro.inciso and consulta.inciso != registro.inciso:
            score -= 0.3
        if consulta.alinea and registro.alinea and consulta.alinea != registro.alinea:
            score -= 0.3
        return max(score, 0.0)

    return 0.0


@dataclass
class CatalogoCanonico:
    """Base congelada carregada em memória (`Contexto.catalogo`,
    docs/contratos.md). `por_chave` cobre jurisprudência (acórdãos);
    `leis_sumulas` cobre os 18 registros (13 dispositivos + 5 súmulas),
    casados por matching de texto, não por chave exata."""

    registros: list[RegistroCatalogo] = field(default_factory=list)
    por_chave: dict[str, list[RegistroCatalogo]] = field(default_factory=dict)
    leis_sumulas: list[RegistroCatalogo] = field(default_factory=list)

    def buscar_jurisprudencia(self, numero_normalizado: str | None) -> list[RegistroCatalogo]:
        """Query primária do Módulo 3: lookup exato pela chave-esqueleto —
        o filtro de posição (cabeçalho vs. corpo) já foi aplicado na
        construção do catálogo, que só indexa o identificador próprio de
        cada registro (catalogo/README.md), então nenhum filtro extra é
        preciso aqui."""
        if not numero_normalizado:
            return []
        return self.por_chave.get(numero_normalizado, [])

    def buscar_lei_sumula(
        self, consulta: CamposIdentificador
    ) -> list[tuple[RegistroCatalogo, float]]:
        pares = [
            (registro, score)
            for registro in self.leis_sumulas
            if (score := _score_lei_sumula(consulta, registro.campos)) > 0.0
        ]
        pares.sort(key=lambda par: par[1], reverse=True)
        return pares

    def relatorio_colisoes(self) -> dict[str, list[int]]:
        """Chaves que apontam para 2+ registros (catalogo/README.md)."""
        return {
            chave: [registro.id for registro in registros]
            for chave, registros in self.por_chave.items()
            if len(registros) > 1
        }
