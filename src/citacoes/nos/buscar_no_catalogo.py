"""Nó `buscar_no_catalogo` — Módulo 3 (Resolução por Busca Estruturada),
docs/arquitetura.md.

`resolver` é a lógica pura, testável sem montar o grafo; `buscar_no_catalogo`
é o nó no formato que o LangGraph espera, lendo o catálogo do contexto
(`runtime.context.catalogo`), nunca do estado (convenção documentada em
docs/arquitetura.md — os 1016 registros não são copiados a cada passo).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from citacoes.catalogo.esquema import Candidato, CatalogoCanonico, RegistroCatalogo
from citacoes.dominio.campos import CamposIdentificador
from citacoes.grafo.estados import Contexto, EstadoCitacao

if TYPE_CHECKING:
    from langgraph.runtime import Runtime


# UF é o único sinal comparado aqui que já temos evidência de ser confiável
# (H4 em docs/avaliacao.md ainda não rodou) — por isso só ele vira conflito
# duro; os demais ficam como divergência branda até a Fase 0.5 confirmar
# quais atributos são seguros para o veto de "quimera" no Módulo 4.
def _para_candidato(
    registro: RegistroCatalogo, score: float, consulta: CamposIdentificador
) -> Candidato:
    duros: list[str] = []
    brandos: list[str] = []
    if consulta.uf and registro.campos.uf and consulta.uf != registro.campos.uf:
        duros.append("uf")
    if consulta.tribunal and registro.tribunal and consulta.tribunal != registro.tribunal:
        brandos.append("tribunal")
    if consulta.classe and registro.campos.classe and consulta.classe != registro.campos.classe:
        brandos.append("classe")
    return Candidato(
        id=registro.id,
        tribunal=registro.tribunal,
        natureza=registro.natureza,
        score=score,
        conflitos_duros=tuple(duros),
        divergencias_brandas=tuple(brandos),
    )


def resolver(estado: EstadoCitacao, catalogo: CatalogoCanonico) -> dict:
    """`metodo == "sem_busca"` <=> `candidatos == []` (invariante da
    fronteira 3->4, docs/contratos.md/Contrato_de_Dados.docx §5)."""
    if not estado.tem_identificador or estado.campos is None:
        return {"candidatos": [], "metodo_busca": "sem_busca"}

    campos = estado.campos
    eh_lei_sumula = estado.tipo_bruto == "lei" or campos.sumula is not None

    if eh_lei_sumula:
        candidatos = [
            _para_candidato(registro, score, campos)
            for registro, score in catalogo.buscar_lei_sumula(campos)
        ]
        return {"candidatos": candidatos, "metodo_busca": "lei_sumula"}

    if campos.numero_normalizado:
        candidatos = [
            _para_candidato(registro, 1.0, campos)
            for registro in catalogo.buscar_jurisprudencia(campos.numero_normalizado)
        ]
        return {"candidatos": candidatos, "metodo_busca": "catalogo"}

    return {"candidatos": [], "metodo_busca": "sem_busca"}


def buscar_no_catalogo(estado: EstadoCitacao, runtime: Runtime[Contexto]) -> dict:
    catalogo = runtime.context.catalogo
    if catalogo is None:
        raise RuntimeError("Contexto.catalogo não foi carregado (ver catalogo/carregar).")
    return resolver(estado, catalogo)
