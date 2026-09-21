"""Nó `decidir` — Módulo 4 (Decisão de classe), docs/arquitetura.md.

`decidir` é a lógica pura, testável sem montar o grafo; `decidir_classe` é
o nó no formato que o LangGraph espera. A regra de decisão é a tabela de
docs/arquitetura.md ("Regra de decisão (em `decidir`)"), aplicada por
cardinalidade dos candidatos sem conflito duro — nunca por ranking de
`score`, porque para jurisprudência o Módulo 3 emite a constante `1.0` em
todo candidato (`nos/buscar_no_catalogo.py`) e todo empate é exato.

`metodo_decisao` registra a proveniência real da decisão (valores em
docs/contratos.md, "EstadoCitacao"); é o sinal que o Módulo 5 (`calibrar`)
consome via `Contexto.tabela_confianca`, então tem de ser fiel ao ramo que
de fato decidiu, não um rótulo de depuração.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from citacoes.catalogo.esquema import Candidato, Natureza
from citacoes.grafo.estados import Contexto, EstadoCitacao, TipoBruto

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

# `estados.py` guarda `classificacao`/`metodo_decisao` como `str | None`;
# os valores fechados vivem aqui (docs/contratos.md, linhas de `decidir`).
Classificacao = Literal["real", "inventada", "incompleta"]
MetodoDecisao = Literal[
    "sem_identificador",
    "cardinalidade_0",
    "cardinalidade_1",
    "cardinalidade_2mais",
    "veto_quimera",
    "juiz",
]
TipoCitacao = Literal["jurisprudencia", "lei"]


@dataclass(frozen=True)
class ParametrosDecisao:
    """Parâmetros do Módulo 4. Defaults conservadores: o juiz fica
    desligado até a análise de erro justificar (docs/arquitetura.md,
    "Agentes LLM")."""

    habilitar_juiz: bool = False


PARAMETROS_PADRAO = ParametrosDecisao()


class Juiz(Protocol):
    """Agente-juiz (docs/arquitetura.md, nó `agente_juiz`): escolhe um id
    entre candidatos empatados ou devolve `None`. Nunca decide classe nem
    confiança (invariante de docs/contratos.md) — quem decide é `decidir`,
    e a justificativa do agente é só log, nunca vira confiança."""

    def escolher(self, estado: EstadoCitacao, candidatos: Sequence[Candidato]) -> int | None: ...


@dataclass(frozen=True)
class JuizDesligado:
    """Implementação padrão: nunca desempata — todo empate vira
    `incompleta`, a aposta documentada em docs/arquitetura.md."""

    def escolher(self, estado: EstadoCitacao, candidatos: Sequence[Candidato]) -> int | None:
        return None


@dataclass(frozen=True)
class JuizLLM:
    """Esqueleto do juiz com modelo local. Determinismo conforme
    docs/arquitetura.md ("Agentes LLM"): `temperature=0` e seed explícita,
    porque o padrão do `ChatLlamaCpp` é seed aleatória (`-1`)."""

    modelo: object
    temperature: float = 0.0
    seed: int = 42

    def escolher(self, estado: EstadoCitacao, candidatos: Sequence[Candidato]) -> int | None:
        raise NotImplementedError(
            "Agente-juiz ainda não implementado — a v1 entrega o Módulo 4 com o juiz "
            "desligado (docs/arquitetura.md, agentes desligados por padrão)."
        )


JUIZ_PADRAO = JuizDesligado()


def _tipo_por_natureza(natureza: Natureza) -> TipoCitacao:
    # Súmula tem `tipo="jurisprudencia"` no banco e no gabarito, mesmo sendo
    # resolvida pelo caminho de lei (catalogo/construir.py).
    return "lei" if natureza == "dispositivo" else "jurisprudencia"


def _resolver_tipo(escolhido: Candidato | None, tipo_bruto: TipoBruto) -> TipoCitacao:
    """`tipo` é contrato de `decidir` (docs/contratos.md) mas não pontua.
    Com candidato escolhido vale a natureza do registro; sem candidato,
    repassa o `tipo_bruto` do Módulo 1 e cai em "jurisprudencia" quando
    ele ficou indefinido — adivinhar pelo `trecho` é trabalho do Módulo 1,
    não deste nó."""
    if escolhido is not None:
        return _tipo_por_natureza(escolhido.natureza)
    if tipo_bruto == "indefinido":
        return "jurisprudencia"
    return tipo_bruto


def _saida(
    classificacao: Classificacao,
    metodo_decisao: MetodoDecisao,
    escolhido: Candidato | None,
    tipo_bruto: TipoBruto,
) -> dict:
    # `classificacao == "real"` <=> `id_canonico` preenchido (docs/contratos.md,
    # invariante de `decidir`) — o id vem sempre de `Candidato.id`, que é a
    # coluna `id` da base, nunca `documento_id`.
    return {
        "classificacao": classificacao,
        "id_canonico": escolhido.id if escolhido is not None else None,
        "tipo": _resolver_tipo(escolhido, tipo_bruto),
        "metodo_decisao": metodo_decisao,
    }


def decidir(
    estado: EstadoCitacao,
    parametros: ParametrosDecisao = PARAMETROS_PADRAO,
    juiz: Juiz = JUIZ_PADRAO,
) -> dict:
    """Aplica a tabela de decisão de docs/arquitetura.md, nesta ordem de
    guardas:

    1. sem busca (`metodo_busca` em `None`/`"sem_busca"`) -> incompleta;
    2. candidatos existem mas todos têm conflito duro -> inventada (quimera);
    3. cardinalidade dos ids distintos sem conflito: 0 -> inventada,
       1 -> real, 2+ -> incompleta (salvo se o juiz desempatar).

    A guarda 1 vem antes de olhar os candidatos porque o roteamento pula o
    nó `buscar` para spans sem identificador (docs/arquitetura.md, aresta
    "sem identificador" -> `decidir`), deixando `metodo_busca=None`; e o
    Módulo 3 emite `"sem_busca"` quando o identificador não é buscável
    (menos de 5 dígitos — ver `dominio/campos.py`). A regra documentada
    manda incompleta nos dois casos, sem tentar recuperar nada aqui.
    """
    if estado.metodo_busca in (None, "sem_busca"):
        return _saida("incompleta", "sem_identificador", None, estado.tipo_bruto)

    candidatos = estado.candidatos
    limpos = [c for c in candidatos if not c.conflitos_duros]

    # Identificador que casa mas diverge em atributo duro em todo candidato
    # é quimera montada pelo gerador (H2 em docs/avaliacao.md): invenção,
    # não ambiguidade — por isso vence a cardinalidade.
    if candidatos and not limpos:
        return _saida("inventada", "veto_quimera", None, estado.tipo_bruto)

    # A cardinalidade é de ids distintos: o mesmo registro repetido na lista
    # não é empate, é um candidato só.
    por_id = {c.id: c for c in limpos}

    if not por_id:
        return _saida("inventada", "cardinalidade_0", None, estado.tipo_bruto)

    if len(por_id) == 1:
        (escolhido,) = por_id.values()
        return _saida("real", "cardinalidade_1", escolhido, estado.tipo_bruto)

    if parametros.habilitar_juiz:
        escolha = juiz.escolher(estado, tuple(por_id.values()))
        # O juiz só escolhe entre os ids dados (docs/arquitetura.md, "Agentes
        # LLM"); qualquer outra resposta equivale a não ter decidido.
        escolhido = por_id.get(escolha) if escolha is not None else None
        classificacao: Classificacao = "real" if escolhido is not None else "incompleta"
        return _saida(classificacao, "juiz", escolhido, estado.tipo_bruto)

    return _saida("incompleta", "cardinalidade_2mais", None, estado.tipo_bruto)


def decidir_classe(estado: EstadoCitacao, runtime: Runtime[Contexto]) -> dict:
    """Nó do grafo. Lê só a flag `usar_juiz` do contexto (docs/contratos.md,
    "Contexto"); `ParametrosDecisao` não faz parte do contexto."""
    contexto = runtime.context
    if not contexto.usar_juiz:
        return decidir(estado, ParametrosDecisao(habilitar_juiz=False), JUIZ_PADRAO)
    if contexto.modelo_llm is None:
        raise RuntimeError("Contexto.usar_juiz ligado sem Contexto.modelo_llm carregado.")
    return decidir(estado, ParametrosDecisao(habilitar_juiz=True), JuizLLM(contexto.modelo_llm))
