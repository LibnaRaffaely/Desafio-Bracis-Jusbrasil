"""Nó `decidir` (Módulo 4) — um caso por ramo da tabela de decisão de
docs/arquitetura.md, mais as invariantes de docs/contratos.md como
propriedades. Tudo sintético: nenhum teste abre o catálogo nem a base."""

from __future__ import annotations

import builtins
import copy
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from hypothesis import given
from hypothesis import strategies as st

from citacoes.agentes.juiz import BackendFalso
from citacoes.catalogo.esquema import Candidato
from citacoes.dominio.campos import CamposIdentificador
from citacoes.grafo.estados import Contexto, EstadoCitacao
from citacoes.nos.decidir import (
    DuplicatasPorAssinatura,
    JuizDesligado,
    JuizFalso,
    JuizLLM,
    ParametrosDecisao,
    SemDuplicatas,
    decidir,
    decidir_classe,
)

CHAVES = {"classificacao", "id_canonico", "tipo", "metodo_decisao"}


def _candidato(
    id_: int,
    natureza: str = "acordao",
    score: float = 1.0,
    conflitos: tuple[str, ...] = (),
    brandas: tuple[str, ...] = (),
) -> Candidato:
    return Candidato(
        id=id_,
        tribunal="STJ",
        natureza=natureza,
        score=score,
        conflitos_duros=conflitos,
        divergencias_brandas=brandas,
    )


def _estado(
    candidatos: list[Candidato] | None = None,
    metodo_busca: str | None = "catalogo",
    tipo_bruto: str = "jurisprudencia",
    tem_identificador: bool = True,
    trecho: str = "REsp 1.234.567/PR",
) -> EstadoCitacao:
    return EstadoCitacao(
        inicio=0,
        fim=len(trecho),
        trecho=trecho,
        tipo_bruto=tipo_bruto,
        tem_identificador=tem_identificador,
        origem="regex_camada1",
        campos=CamposIdentificador(),
        candidatos=list(candidatos or []),
        metodo_busca=metodo_busca,
    )


# ── um caso por ramo ────────────────────────────────────────────────────────


def test_sem_busca_vira_incompleta_sem_identificador():
    saida = decidir(_estado([], metodo_busca="sem_busca", tem_identificador=False))
    assert saida["classificacao"] == "incompleta"
    assert saida["metodo_decisao"] == "sem_identificador"
    assert saida["id_canonico"] is None


def test_zero_candidatos_com_busca_no_catalogo_vira_inventada_cardinalidade_0():
    saida = decidir(_estado([], metodo_busca="catalogo"))
    assert saida["classificacao"] == "inventada"
    assert saida["metodo_decisao"] == "cardinalidade_0"
    assert saida["id_canonico"] is None


def test_zero_candidatos_com_busca_lei_sumula_vira_inventada_cardinalidade_0():
    saida = decidir(_estado([], metodo_busca="lei_sumula", tipo_bruto="lei"))
    assert saida["classificacao"] == "inventada"
    assert saida["metodo_decisao"] == "cardinalidade_0"
    assert saida["tipo"] == "lei"


def test_um_candidato_limpo_vira_real_cardinalidade_1():
    saida = decidir(_estado([_candidato(42)]))
    assert saida["classificacao"] == "real"
    assert saida["metodo_decisao"] == "cardinalidade_1"
    assert saida["id_canonico"] == 42


def test_dois_candidatos_limpos_viram_incompleta_cardinalidade_2mais():
    saida = decidir(_estado([_candidato(1), _candidato(2)]))
    assert saida["classificacao"] == "incompleta"
    assert saida["metodo_decisao"] == "cardinalidade_2mais"
    assert saida["id_canonico"] is None


def test_todos_conflitados_vira_inventada_veto_quimera():
    saida = decidir(_estado([_candidato(1, conflitos=("uf",))]))
    assert saida["classificacao"] == "inventada"
    assert saida["metodo_decisao"] == "veto_quimera"
    assert saida["id_canonico"] is None


# ── ordem das guardas e casos de borda ─────────────────────────────────────


def test_metodo_busca_none_vence_mesmo_com_candidatos_populados():
    # O roteamento pula `buscar` para spans sem identificador
    # (docs/arquitetura.md); a guarda 1 tem de vencer o que estiver na lista.
    saida = decidir(_estado([_candidato(1)], metodo_busca=None))
    assert saida["classificacao"] == "incompleta"
    assert saida["metodo_decisao"] == "sem_identificador"
    assert saida["id_canonico"] is None


def test_sem_busca_com_tem_identificador_verdadeiro_continua_sem_identificador():
    # "AR n. 2785 (SP)": tem_identificador=True, mas menos de 5 dígitos, então
    # o Módulo 3 emite "sem_busca" — a regra documentada manda incompleta.
    saida = decidir(
        _estado([], metodo_busca="sem_busca", tem_identificador=True, trecho="AR\nn. 2785 (SP)")
    )
    assert saida["classificacao"] == "incompleta"
    assert saida["metodo_decisao"] == "sem_identificador"


def test_ids_repetidos_entre_candidatos_contam_como_um_so():
    saida = decidir(_estado([_candidato(7), _candidato(7), _candidato(7)]))
    assert saida["classificacao"] == "real"
    assert saida["metodo_decisao"] == "cardinalidade_1"
    assert saida["id_canonico"] == 7


def test_um_limpo_e_dois_conflitados_vira_real_pelo_limpo():
    candidatos = [
        _candidato(1, conflitos=("uf",)),
        _candidato(2),
        _candidato(3, conflitos=("uf",)),
    ]
    saida = decidir(_estado(candidatos))
    assert saida["classificacao"] == "real"
    assert saida["metodo_decisao"] == "cardinalidade_1"
    assert saida["id_canonico"] == 2


def test_todos_conflitados_nunca_vira_cardinalidade_2mais():
    candidatos = [_candidato(1, conflitos=("uf",)), _candidato(2, conflitos=("uf",))]
    saida = decidir(_estado(candidatos))
    assert saida["metodo_decisao"] == "veto_quimera"
    assert saida["classificacao"] == "inventada"


def test_divergencias_brandas_nao_afetam_a_decisao():
    saida = decidir(_estado([_candidato(9, brandas=("tribunal", "classe"))]))
    assert saida["classificacao"] == "real"
    assert saida["id_canonico"] == 9


def test_score_nao_desempata_lei_sumula():
    # Score só discrimina em lei/súmula (1.0 / 0.7 / 0.5), mas a v1 decide
    # por cardinalidade: dois ids distintos é empate, seja qual for o score.
    candidatos = [
        _candidato(1, natureza="dispositivo", score=1.0),
        _candidato(2, natureza="dispositivo", score=0.7),
    ]
    saida = decidir(_estado(candidatos, metodo_busca="lei_sumula", tipo_bruto="lei"))
    assert saida["classificacao"] == "incompleta"
    assert saida["metodo_decisao"] == "cardinalidade_2mais"


def test_trecho_com_quebra_de_linha_no_meio_nao_quebra_nada():
    saida = decidir(_estado([_candidato(5)], trecho="APL nº\n7000449-40.2023.7.00.0000/RS"))
    assert saida["classificacao"] == "real"
    assert saida["id_canonico"] == 5


# ── tipo ────────────────────────────────────────────────────────────────────


def test_tipo_de_dispositivo_escolhido_e_lei():
    saida = decidir(
        _estado(
            [_candidato(1, natureza="dispositivo")], metodo_busca="lei_sumula", tipo_bruto="lei"
        )
    )
    assert saida["tipo"] == "lei"


def test_tipo_de_sumula_escolhida_e_jurisprudencia():
    saida = decidir(
        _estado([_candidato(1, natureza="sumula")], metodo_busca="lei_sumula", tipo_bruto="lei")
    )
    assert saida["tipo"] == "jurisprudencia"


def test_tipo_de_acordao_escolhido_e_jurisprudencia():
    saida = decidir(_estado([_candidato(1, natureza="acordao")]))
    assert saida["tipo"] == "jurisprudencia"


def test_tipo_sem_candidato_repassa_tipo_bruto():
    saida = decidir(_estado([], metodo_busca="catalogo", tipo_bruto="lei"))
    assert saida["tipo"] == "lei"


def test_tipo_sem_candidato_e_indefinido_cai_em_jurisprudencia():
    saida = decidir(_estado([], metodo_busca="sem_busca", tipo_bruto="indefinido"))
    assert saida["tipo"] == "jurisprudencia"


# ── juiz ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _JuizFixo:
    resposta: int | None

    def escolher(self, estado: EstadoCitacao, candidatos: Sequence[Candidato]) -> int | None:
        return self.resposta


def test_juiz_desligado_por_padrao_nao_e_consultado():
    saida = decidir(_estado([_candidato(1), _candidato(2)]), juiz=_JuizFixo(1))
    assert saida["metodo_decisao"] == "cardinalidade_2mais"
    assert saida["classificacao"] == "incompleta"


def test_juiz_habilitado_devolvendo_none_vira_incompleta_com_metodo_juiz():
    parametros = ParametrosDecisao(habilitar_juiz=True)
    saida = decidir(_estado([_candidato(1), _candidato(2)]), parametros, JuizDesligado())
    assert saida["classificacao"] == "incompleta"
    assert saida["metodo_decisao"] == "juiz"
    assert saida["id_canonico"] is None


def test_juiz_habilitado_escolhendo_um_id_dado_vira_real_com_metodo_juiz():
    parametros = ParametrosDecisao(habilitar_juiz=True)
    saida = decidir(_estado([_candidato(1), _candidato(2)]), parametros, _JuizFixo(2))
    assert saida["classificacao"] == "real"
    assert saida["metodo_decisao"] == "juiz"
    assert saida["id_canonico"] == 2


def test_juiz_escolhendo_id_fora_dos_candidatos_equivale_a_nao_decidir():
    parametros = ParametrosDecisao(habilitar_juiz=True)
    saida = decidir(_estado([_candidato(1), _candidato(2)]), parametros, _JuizFixo(99))
    assert saida["classificacao"] == "incompleta"
    assert saida["metodo_decisao"] == "juiz"
    assert saida["id_canonico"] is None


def test_juiz_nao_e_consultado_com_um_candidato_so():
    parametros = ParametrosDecisao(habilitar_juiz=True)
    saida = decidir(_estado([_candidato(1)]), parametros, _JuizFixo(None))
    assert saida["metodo_decisao"] == "cardinalidade_1"


def test_juiz_falso_responde_pelo_conjunto_de_ids_oferecido():
    juiz = JuizFalso({frozenset({1, 2}): 2, frozenset({3, 4}): 99})
    parametros = ParametrosDecisao(habilitar_juiz=True)
    assert decidir(_estado([_candidato(1), _candidato(2)]), parametros, juiz)["id_canonico"] == 2
    # 99 não está na lista: o juiz "chutou" e decidir descarta
    saida = decidir(_estado([_candidato(3), _candidato(4)]), parametros, juiz)
    assert saida["classificacao"] == "incompleta"
    # conjunto não programado cai no padrão (None)
    saida = decidir(_estado([_candidato(5), _candidato(6)]), parametros, juiz)
    assert saida["classificacao"] == "incompleta"
    assert saida["metodo_decisao"] == "juiz"


# ── desempate determinístico (antes do juiz) ───────────────────────────────


def test_duplicata_de_conteudo_resolve_pelo_menor_id_sem_chamar_o_juiz():
    duplicatas = DuplicatasPorAssinatura({20: "sha-a", 10: "sha-a"})
    backend = BackendFalso(resposta='{"id_canonico": 20, "justificativa": "x"}')
    parametros = ParametrosDecisao(habilitar_juiz=True)
    saida = decidir(
        _estado([_candidato(20), _candidato(10)]), parametros, JuizLLM(backend), duplicatas
    )
    assert saida["classificacao"] == "real"
    assert saida["metodo_decisao"] == "desempate_duplicata"
    assert saida["id_canonico"] == 10
    assert backend.chamadas == []


def test_duplicata_com_juiz_desligado_tambem_resolve():
    duplicatas = DuplicatasPorAssinatura({1: "sha-a", 2: "sha-a"})
    saida = decidir(_estado([_candidato(1), _candidato(2)]), duplicatas=duplicatas)
    assert saida["classificacao"] == "real"
    assert saida["metodo_decisao"] == "desempate_duplicata"
    assert saida["id_canonico"] == 1


def test_duplicata_parcial_colapsa_o_par_e_deixa_o_restante_para_o_juiz():
    # 1 e 2 são o mesmo texto; 3 é outro documento: ainda há 2 conteúdos.
    duplicatas = DuplicatasPorAssinatura({1: "sha-a", 2: "sha-a", 3: "sha-b"})
    candidatos = [_candidato(1), _candidato(2), _candidato(3)]
    saida = decidir(_estado(candidatos), duplicatas=duplicatas)
    assert saida["metodo_decisao"] == "cardinalidade_2mais"
    vistos: list[frozenset[int]] = []

    @dataclass(frozen=True)
    class _Espiao:
        def escolher(self, estado, candidatos):
            vistos.append(frozenset(c.id for c in candidatos))
            return None

    decidir(_estado(candidatos), ParametrosDecisao(habilitar_juiz=True), _Espiao(), duplicatas)
    assert vistos == [frozenset({1, 3})]


def test_ids_sem_assinatura_nunca_colapsam():
    duplicatas = DuplicatasPorAssinatura({1: "sha-a"})  # 2 sem assinatura
    saida = decidir(_estado([_candidato(1), _candidato(2)]), duplicatas=duplicatas)
    assert saida["metodo_decisao"] == "cardinalidade_2mais"
    assert (
        decidir(_estado([_candidato(1), _candidato(2)]), duplicatas=SemDuplicatas())[
            "metodo_decisao"
        ]
        == "cardinalidade_2mais"
    )


def _empate_lei():
    return _estado(
        [
            _candidato(1, natureza="dispositivo", score=0.7),
            _candidato(2, natureza="dispositivo", score=1.0),
        ],
        metodo_busca="lei_sumula",
        tipo_bruto="lei",
    )


def test_scores_distintos_com_desempate_desligado_continua_cardinalidade_2mais():
    saida = decidir(_empate_lei())
    assert saida["classificacao"] == "incompleta"
    assert saida["metodo_decisao"] == "cardinalidade_2mais"


def test_scores_distintos_com_desempate_ligado_resolve_pelo_maior_score():
    saida = decidir(_empate_lei(), ParametrosDecisao(habilitar_desempate_score=True))
    assert saida["classificacao"] == "real"
    assert saida["metodo_decisao"] == "desempate_score"
    assert saida["id_canonico"] == 2
    assert saida["tipo"] == "lei"


def test_margem_abaixo_da_minima_nao_resolve_e_cai_para_o_juiz_ou_incompleta():
    parametros = ParametrosDecisao(habilitar_desempate_score=True, margem_minima=0.5)
    saida = decidir(_empate_lei(), parametros)  # margem 0.3 < 0.5
    assert saida["metodo_decisao"] == "cardinalidade_2mais"
    parametros = ParametrosDecisao(
        habilitar_juiz=True, habilitar_desempate_score=True, margem_minima=0.5
    )
    saida = decidir(_empate_lei(), parametros, JuizFalso(padrao=1))
    assert saida["metodo_decisao"] == "juiz"
    assert saida["id_canonico"] == 1


def test_empate_no_topo_do_score_nao_resolve():
    candidatos = [
        _candidato(1, score=1.0),
        _candidato(2, score=1.0),
        _candidato(3, score=0.5),
    ]
    saida = decidir(_estado(candidatos), ParametrosDecisao(habilitar_desempate_score=True))
    assert saida["metodo_decisao"] == "cardinalidade_2mais"


def test_score_constante_de_jurisprudencia_nunca_desempata():
    saida = decidir(
        _estado([_candidato(1), _candidato(2)]),
        ParametrosDecisao(habilitar_desempate_score=True),
    )
    assert saida["metodo_decisao"] == "cardinalidade_2mais"


def test_desempate_por_score_usa_o_maior_score_de_cada_id():
    candidatos = [_candidato(1, score=0.5), _candidato(1, score=1.0), _candidato(2, score=0.7)]
    saida = decidir(_estado(candidatos), ParametrosDecisao(habilitar_desempate_score=True))
    assert saida["id_canonico"] == 1


def test_duplicata_vem_antes_do_score():
    duplicatas = DuplicatasPorAssinatura({1: "sha-a", 2: "sha-a"})
    candidatos = [_candidato(1, score=0.7), _candidato(2, score=1.0)]
    saida = decidir(
        _estado(candidatos),
        ParametrosDecisao(habilitar_desempate_score=True),
        duplicatas=duplicatas,
    )
    assert saida["metodo_decisao"] == "desempate_duplicata"
    assert saida["id_canonico"] == 1


# ── wrapper de nó ───────────────────────────────────────────────────────────


@dataclass
class _RuntimeFalso:
    context: Contexto


def test_no_decidir_classe_com_juiz_desligado_no_contexto():
    runtime = _RuntimeFalso(context=Contexto())
    saida = decidir_classe(_estado([_candidato(1), _candidato(2)]), runtime)
    assert saida["metodo_decisao"] == "cardinalidade_2mais"


def test_no_decidir_classe_exige_modelo_quando_usar_juiz_ligado():
    runtime = _RuntimeFalso(context=Contexto(usar_juiz=True, modelo_llm=None))
    try:
        decidir_classe(_estado([_candidato(1), _candidato(2)]), runtime)
    except RuntimeError as erro:
        assert "modelo_llm" in str(erro)
    else:
        raise AssertionError("usar_juiz sem modelo_llm deveria ser pré-condição de contexto")


def test_decidir_nao_abre_banco_nem_arquivo(monkeypatch):
    def _proibido(*args, **kwargs):
        raise AssertionError("decidir não pode fazer I/O")

    monkeypatch.setattr(sqlite3, "connect", _proibido)
    monkeypatch.setattr(builtins, "open", _proibido)
    for estado in (
        _estado([], metodo_busca=None),
        _estado([], metodo_busca="catalogo"),
        _estado([_candidato(1)]),
        _estado([_candidato(1), _candidato(2)]),
        _estado([_candidato(1, conflitos=("uf",))]),
    ):
        assert set(decidir(estado)) == CHAVES
        parametros = ParametrosDecisao(habilitar_desempate_score=True)
        duplicatas = DuplicatasPorAssinatura({1: "a", 2: "a"})
        assert set(decidir(estado, parametros, duplicatas=duplicatas)) == CHAVES


# ── propriedades ────────────────────────────────────────────────────────────

_ids = st.integers(min_value=1, max_value=10**10)
_conflitos = st.sampled_from([(), ("uf",)])
_naturezas = st.sampled_from(["acordao", "sumula", "dispositivo"])
_candidatos = st.lists(
    st.builds(
        _candidato,
        id_=_ids,
        natureza=_naturezas,
        score=st.sampled_from([1.0, 0.7, 0.5]),
        conflitos=_conflitos,
    ),
    max_size=6,
)
_metodos_busca = st.sampled_from([None, "sem_busca", "catalogo", "lei_sumula"])
_tipos_brutos = st.sampled_from(["jurisprudencia", "lei", "indefinido"])
_parametros = st.builds(
    ParametrosDecisao,
    habilitar_juiz=st.booleans(),
    habilitar_desempate_score=st.booleans(),
    margem_minima=st.sampled_from([0.0, 0.2, 0.5]),
)


def _juiz_llm_falso(resposta: str) -> JuizLLM:
    return JuizLLM(BackendFalso(resposta))


_respostas_llm = st.one_of(
    st.just(""),
    st.just("não sei"),
    st.just('{"id_canonico": null, "justificativa": "sem sinal"}'),
    _ids.map(lambda i: f'{{"id_canonico": {i}, "justificativa": "x"}}'),
    _ids.map(lambda i: f'```json\n{{"id_canonico": {i}}}\n```'),
)
_juizes = st.one_of(
    st.just(JuizDesligado()),
    st.builds(_JuizFixo, resposta=st.one_of(st.none(), _ids)),
    st.builds(JuizFalso, padrao=st.one_of(st.none(), _ids)),
    _respostas_llm.map(_juiz_llm_falso),
)
_duplicatas = st.builds(
    DuplicatasPorAssinatura,
    assinaturas=st.dictionaries(_ids, st.sampled_from(["a", "b"]), max_size=4),
)


@given(
    candidatos=_candidatos,
    metodo=_metodos_busca,
    tipo=_tipos_brutos,
    parametros=_parametros,
    juiz=_juizes,
    duplicatas=_duplicatas,
)
def test_propriedade_real_se_e_somente_se_id_canonico_preenchido(
    candidatos, metodo, tipo, parametros, juiz, duplicatas
):
    saida = decidir(
        _estado(candidatos, metodo_busca=metodo, tipo_bruto=tipo), parametros, juiz, duplicatas
    )
    assert (saida["classificacao"] == "real") == (saida["id_canonico"] is not None)


@given(
    candidatos=_candidatos,
    metodo=_metodos_busca,
    tipo=_tipos_brutos,
    parametros=_parametros,
    juiz=_juizes,
    duplicatas=_duplicatas,
)
def test_propriedade_id_canonico_e_int_vindo_de_candidato_id(
    candidatos, metodo, tipo, parametros, juiz, duplicatas
):
    # Vale em todos os caminhos, inclusive juiz e desempates: `real` ⟹ id
    # é de um candidato limpo da lista.
    saida = decidir(
        _estado(candidatos, metodo_busca=metodo, tipo_bruto=tipo), parametros, juiz, duplicatas
    )
    if saida["id_canonico"] is not None:
        assert type(saida["id_canonico"]) is int
        assert saida["id_canonico"] in {c.id for c in candidatos if not c.conflitos_duros}


@given(
    metodo=_metodos_busca,
    tipo=_tipos_brutos,
    parametros=_parametros,
    juiz=_juizes,
    duplicatas=_duplicatas,
)
def test_propriedade_juiz_nunca_converte_zero_candidatos_em_real(
    metodo, tipo, parametros, juiz, duplicatas
):
    saida = decidir(_estado([], metodo_busca=metodo, tipo_bruto=tipo), parametros, juiz, duplicatas)
    assert saida["classificacao"] != "real"
    assert saida["metodo_decisao"] in {"sem_identificador", "cardinalidade_0"}


@given(
    candidatos=_candidatos,
    metodo=_metodos_busca,
    tipo=_tipos_brutos,
    duplicatas=_duplicatas,
)
def test_propriedade_juiz_desligado_nunca_chama_o_backend(candidatos, metodo, tipo, duplicatas):
    backend = BackendFalso('{"id_canonico": 1}')
    parametros = ParametrosDecisao(habilitar_juiz=False, habilitar_desempate_score=True)
    decidir(
        _estado(candidatos, metodo_busca=metodo, tipo_bruto=tipo),
        parametros,
        JuizLLM(backend),
        duplicatas,
    )
    assert backend.chamadas == []


@given(
    candidatos=_candidatos,
    metodo=_metodos_busca,
    tipo=_tipos_brutos,
    parametros=_parametros,
    juiz=_juizes,
    duplicatas=_duplicatas,
)
def test_propriedade_funcao_pura_nao_muta_o_estado(
    candidatos, metodo, tipo, parametros, juiz, duplicatas
):
    estado = _estado(candidatos, metodo_busca=metodo, tipo_bruto=tipo)
    antes = copy.deepcopy(estado)
    decidir(estado, parametros, juiz, duplicatas)
    assert estado == antes


@given(
    candidatos=_candidatos,
    metodo=_metodos_busca,
    tipo=_tipos_brutos,
    parametros=_parametros,
    juiz=_juizes,
    duplicatas=_duplicatas,
)
def test_propriedade_saida_tem_exatamente_as_quatro_chaves(
    candidatos, metodo, tipo, parametros, juiz, duplicatas
):
    saida = decidir(
        _estado(candidatos, metodo_busca=metodo, tipo_bruto=tipo), parametros, juiz, duplicatas
    )
    assert set(saida) == CHAVES
    assert saida["classificacao"] in {"real", "inventada", "incompleta"}
    assert saida["tipo"] in {"jurisprudencia", "lei"}
