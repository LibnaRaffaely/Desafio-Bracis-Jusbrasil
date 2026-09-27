"""Montagem do grafo do documento e do subgrafo da citação —
docs/arquitetura.md. Só ligação: cada nó vem de `nos/`, cada aresta
condicional de `grafo/roteamento.py`.

Divergências do mermaid de docs/arquitetura.md, por falta do nó no código:

- `calibrar` roda depois de `decidir` e lê a tabela de `params/` pelo
  contexto; sem tabela, a `confianca` fica `None` (vira `-` no CSV, sem
  bônus de Brier).
- `agente_extrator` e `agente_parser` não existem em `agentes/`: ligar as
  flags correspondentes levanta `NotImplementedError` na montagem.
- `agente_juiz` não é nó: o juiz roda dentro de `decidir` quando
  `Contexto.usar_juiz` está ligado (ver `grafo/roteamento.py`).
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from citacoes.grafo.estados import Contexto, EntradaDocumento, EstadoCitacao, EstadoDocumento
from citacoes.grafo.roteamento import (
    NO_PROCESSAR_CITACAO,
    NO_REUNIR,
    rota_apos_extrair,
    rota_apos_normalizar,
)
from citacoes.nos.buscar_no_catalogo import buscar_no_catalogo
from citacoes.nos.calibrar import calibrar_confianca
from citacoes.nos.decidir import decidir_classe
from citacoes.nos.extrair_spans import extrair_spans
from citacoes.nos.ler_documento import ler_documento
from citacoes.nos.normalizar import normalizar
from citacoes.nos.reunir_e_formatar import reunir_e_formatar

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

_CAMPOS_CITACAO = frozenset(f.name for f in fields(EstadoCitacao))


def _recusar_agentes_ausentes(usar_extrator_llm: bool, usar_parser_llm: bool) -> None:
    ausentes = [
        nome
        for nome, ligado in (
            ("agente_extrator", usar_extrator_llm),
            ("agente_parser", usar_parser_llm),
        )
        if ligado
    ]
    if ausentes:
        raise NotImplementedError(
            f"{', '.join(ausentes)} não existe em citacoes/agentes/; desligue a flag."
        )


def montar_subgrafo_citacao(*, usar_parser_llm: bool = False) -> CompiledStateGraph:
    """`normalizar -> [buscar_no_catalogo] -> decidir -> calibrar`."""
    _recusar_agentes_ausentes(False, usar_parser_llm)
    grafo = StateGraph(EstadoCitacao, context_schema=Contexto)
    grafo.add_node("normalizar", normalizar)
    grafo.add_node("buscar_no_catalogo", buscar_no_catalogo)
    grafo.add_node("decidir", decidir_classe)
    grafo.add_node("calibrar", calibrar_confianca)
    grafo.add_edge(START, "normalizar")
    grafo.add_conditional_edges(
        "normalizar", rota_apos_normalizar, ["buscar_no_catalogo", "decidir"]
    )
    grafo.add_edge("buscar_no_catalogo", "decidir")
    grafo.add_edge("decidir", "calibrar")
    grafo.add_edge("calibrar", END)
    return grafo.compile(name="subgrafo_citacao")


def como_citacao(resultado: dict) -> EstadoCitacao:
    """O `invoke` de um grafo com estado em dataclass devolve `dict`; os nós
    a jusante (`reunir_e_formatar`) leem atributos."""
    return EstadoCitacao(**{k: v for k, v in resultado.items() if k in _CAMPOS_CITACAO})


def _ler_documento(entrada: EntradaDocumento) -> dict:
    """Adaptador: `nos.ler_documento` recebe o caminho, não o estado."""
    return ler_documento(entrada.caminho)


def montar_grafo_documento(
    *, usar_extrator_llm: bool = False, usar_parser_llm: bool = False
) -> CompiledStateGraph:
    """`ler_documento -> extrair_spans -> distribuir (Send) ->
    processar_citacao -> reunir_e_formatar`. Entrada: `{"caminho": ...}`."""
    _recusar_agentes_ausentes(usar_extrator_llm, usar_parser_llm)
    subgrafo = montar_subgrafo_citacao(usar_parser_llm=usar_parser_llm)

    def processar_citacao(span: EstadoCitacao, runtime: Runtime[Contexto]) -> dict:
        resultado = subgrafo.invoke(span, context=runtime.context)
        return {"citacoes": [como_citacao(resultado)]}

    grafo = StateGraph(EstadoDocumento, input_schema=EntradaDocumento, context_schema=Contexto)
    grafo.add_node("ler_documento", _ler_documento)
    grafo.add_node("extrair_spans", extrair_spans)
    grafo.add_node(NO_PROCESSAR_CITACAO, processar_citacao)
    grafo.add_node(NO_REUNIR, reunir_e_formatar)
    grafo.add_edge(START, "ler_documento")
    grafo.add_edge("ler_documento", "extrair_spans")
    grafo.add_conditional_edges(
        "extrair_spans", rota_apos_extrair, [NO_PROCESSAR_CITACAO, NO_REUNIR]
    )
    grafo.add_edge(NO_PROCESSAR_CITACAO, NO_REUNIR)
    grafo.add_edge(NO_REUNIR, END)
    return grafo.compile(name="grafo_documento")


def exportar_mermaid(destino: Path | str) -> str:
    """Diagrama com o subgrafo expandido, para conferir com o mermaid de
    docs/arquitetura.md."""
    diagrama = montar_grafo_documento().get_graph(xray=True).draw_mermaid()
    Path(destino).write_text(diagrama, encoding="utf-8")
    return diagrama


if __name__ == "__main__":
    exportar_mermaid(Path("docs/grafo.mmd"))
