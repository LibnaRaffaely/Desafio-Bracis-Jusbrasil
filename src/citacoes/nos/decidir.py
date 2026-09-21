"""Nó `decidir` — Módulo 4 (Decisão de classe), docs/arquitetura.md.

`decidir` é a lógica pura, testável sem montar o grafo; `decidir_classe` é
o nó no formato que o LangGraph espera. A regra de decisão é a tabela de
docs/arquitetura.md ("Regra de decisão (em `decidir`)"), aplicada por
cardinalidade dos candidatos sem conflito duro — não por ranking de
`score`, porque para jurisprudência o Módulo 3 emite a constante `1.0` em
todo candidato (`nos/buscar_no_catalogo.py`) e todo empate é exato; o
score só entra no desempate opcional 1b, abaixo.

`metodo_decisao` registra a proveniência real da decisão (valores em
docs/contratos.md, "EstadoCitacao"); é o sinal que o Módulo 5 (`calibrar`)
consome via `Contexto.tabela_confianca`, então tem de ser fiel ao ramo que
de fato decidiu, não um rótulo de depuração.

No ramo de 2+ candidatos há dois desempates determinísticos antes do
Agente-Juiz (`agentes/juiz.py`), nesta ordem: (1a) candidatos que são o
mesmo conteúdo — o catálogo tem pares de registros com texto idêntico sob
a mesma chave — colapsam no menor id; (1b) score estritamente maior com
margem mínima, desligado por padrão. `desempate_duplicata` e
`desempate_score` são valores novos de `metodo_decisao` (decisão de
2026-09-20 com a Isadora; ainda a levar ao trio e a docs/contratos.md).
Só o que sobra vai ao juiz; com o juiz desligado, sobra `incompleta`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

from citacoes.agentes.juiz import JuizLLM
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
    "desempate_duplicata",
    "desempate_score",
    "juiz",
]
TipoCitacao = Literal["jurisprudencia", "lei"]


@dataclass(frozen=True)
class ParametrosDecisao:
    """Parâmetros do Módulo 4. Defaults conservadores: o juiz fica
    desligado até a análise de erro justificar (docs/arquitetura.md,
    "Agentes LLM")."""

    habilitar_juiz: bool = False
    # Desempate 1b: escolhe o maior score se ele vence o segundo por pelo
    # menos `margem_minima` (e estritamente). Hoje nunca dispararia — o
    # score de jurisprudência é constante `1.0` e nenhum empate de
    # lei/súmula teve scores distintos no dev set — mas passa a valer se o
    # catálogo mudar. Desligado por padrão, como o juiz.
    habilitar_desempate_score: bool = False
    margem_minima: float = 0.0


PARAMETROS_PADRAO = ParametrosDecisao()


class Duplicatas(Protocol):
    """Oráculo de conteúdo para o desempate 1a: dois ids com a mesma
    `assinatura` (não nula) são o mesmo documento. Nem `Candidato` nem
    `RegistroCatalogo` carregam o texto ou um hash dele, e igualdade de
    metadados (tribunal/ano/relator/campos) é proxy falso — 5 das 14
    colisões do catálogo têm metadados iguais e texto diferente —, por
    isso a assinatura é injetada, não deduzida. Em produção depende de o
    Módulo 3 expor um `hash_texto` no catálogo."""

    def assinatura(self, id_: int) -> str | None: ...


@dataclass(frozen=True)
class SemDuplicatas:
    """Padrão: nenhum id tem assinatura, o desempate 1a nunca dispara."""

    def assinatura(self, id_: int) -> str | None:
        return None


@dataclass(frozen=True)
class DuplicatasPorAssinatura:
    """Assinaturas de conteúdo por id (por exemplo, hash do `texto` do
    registro). Ids ausentes não têm assinatura e nunca colapsam."""

    assinaturas: Mapping[int, str] = field(default_factory=dict)

    def assinatura(self, id_: int) -> str | None:
        return self.assinaturas.get(id_)


SEM_DUPLICATAS = SemDuplicatas()


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
class JuizFalso:
    """Juiz de resposta programada, para testes e para o harness
    (`--juiz falso`): a resposta é escolhida pelo conjunto de ids
    oferecido, e `padrao` vale para conjuntos não programados. Puro e sem
    estado, como os demais — o mesmo conjunto sempre recebe a mesma
    resposta."""

    respostas: Mapping[frozenset[int], int | None] = field(default_factory=dict)
    padrao: int | None = None

    def escolher(self, estado: EstadoCitacao, candidatos: Sequence[Candidato]) -> int | None:
        return self.respostas.get(frozenset(c.id for c in candidatos), self.padrao)


JUIZ_PADRAO = JuizDesligado()

__all__ = [
    "Duplicatas",
    "DuplicatasPorAssinatura",
    "Juiz",
    "JuizDesligado",
    "JuizFalso",
    "JuizLLM",
    "ParametrosDecisao",
    "SemDuplicatas",
    "decidir",
    "decidir_classe",
]


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


def _colapsar_duplicatas(
    por_id: Mapping[int, Candidato], duplicatas: Duplicatas
) -> dict[int, Candidato]:
    """Desempate 1a: ids com a mesma assinatura de conteúdo são o mesmo
    documento e viram um só candidato, o de menor id (escolha
    determinística; entre registros idênticos não há o que julgar). Ids
    sem assinatura ficam como estão."""
    representante: dict[str, int] = {}
    for id_ in sorted(por_id):
        assinatura = duplicatas.assinatura(id_)
        if assinatura is not None:
            representante.setdefault(assinatura, id_)
    mantidos = set(representante.values())
    return {
        id_: c for id_, c in por_id.items() if duplicatas.assinatura(id_) is None or id_ in mantidos
    }


def _melhor_por_score(
    por_id: Mapping[int, Candidato], limpos: Sequence[Candidato], margem_minima: float
) -> Candidato | None:
    """Desempate 1b: o maior score vence se supera o segundo estritamente e
    por pelo menos `margem_minima`. O score de um id é o maior entre as
    suas ocorrências. Empate no topo -> `None`."""
    scores = {id_: max(c.score for c in limpos if c.id == id_) for id_ in por_id}
    ordem = sorted(scores, key=lambda id_: (-scores[id_], id_))
    primeiro, segundo = ordem[0], ordem[1]
    margem = scores[primeiro] - scores[segundo]
    if margem > 0.0 and margem >= margem_minima:
        return por_id[primeiro]
    return None


def decidir(
    estado: EstadoCitacao,
    parametros: ParametrosDecisao = PARAMETROS_PADRAO,
    juiz: Juiz = JUIZ_PADRAO,
    duplicatas: Duplicatas = SEM_DUPLICATAS,
) -> dict:
    """Aplica a tabela de decisão de docs/arquitetura.md, nesta ordem de
    guardas:

    1. sem busca (`metodo_busca` em `None`/`"sem_busca"`) -> incompleta;
    2. candidatos existem mas todos têm conflito duro -> inventada (quimera);
    3. cardinalidade dos ids distintos sem conflito: 0 -> inventada,
       1 -> real, 2+ -> desempates abaixo;
    4. (1a) ids com a mesma assinatura de conteúdo colapsam no menor id;
       se sobra 1 -> real / `desempate_duplicata`;
    5. (1b) com `habilitar_desempate_score`, maior score com margem
       -> real / `desempate_score`;
    6. com `habilitar_juiz`, o juiz escolhe entre os que sobraram
       (`metodo_decisao="juiz"` nos dois desfechos); senão -> incompleta /
       `cardinalidade_2mais`, exatamente como antes dos desempates.

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

    # Desempate 1a — só colapsa; se ainda restarem 2+ conteúdos distintos,
    # os representantes seguem para 1b e para o juiz.
    restantes = _colapsar_duplicatas(por_id, duplicatas)
    if len(restantes) == 1:
        (escolhido,) = restantes.values()
        return _saida("real", "desempate_duplicata", escolhido, estado.tipo_bruto)

    # Desempate 1b — opcional e conservador (margem estrita).
    if parametros.habilitar_desempate_score:
        escolhido = _melhor_por_score(restantes, limpos, parametros.margem_minima)
        if escolhido is not None:
            return _saida("real", "desempate_score", escolhido, estado.tipo_bruto)

    if parametros.habilitar_juiz:
        escolha = juiz.escolher(estado, tuple(restantes.values()))
        # O juiz só escolhe entre os ids dados (docs/arquitetura.md, "Agentes
        # LLM"); qualquer outra resposta equivale a não ter decidido.
        escolhido = restantes.get(escolha) if escolha is not None else None
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
    # `Contexto.modelo_llm` é o `BackendLLM` já carregado (agentes/juiz.py);
    # o catálogo do contexto enriquece os candidatos com ano/relator.
    juiz = JuizLLM(backend=contexto.modelo_llm, catalogo=contexto.catalogo)
    return decidir(estado, ParametrosDecisao(habilitar_juiz=True), juiz)
