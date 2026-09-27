"""Módulo 5 — `nos/calibrar.py` e o ajuste em `avaliacao/calibracao.py`.
Tudo sintético: nenhum teste abre os dados do desafio."""

from __future__ import annotations

import json

import pytest

from citacoes.avaliacao.calibracao import (
    Rotulo,
    ajustar_tabela,
    bonus,
    brier,
    brier_deixando_um_documento_fora,
    casar,
    ler_gabarito,
    rotular,
)
from citacoes.grafo.estados import Contexto, EstadoCitacao
from citacoes.nos.calibrar import calibrar, chave_faixa, confianca_da_tabela
from citacoes.rodar import rodar_subgrafo_em_spans

TABELA = {
    "faixas": {"cardinalidade_1|catalogo": {"confianca": 0.98}},
    "por_metodo_decisao": {"cardinalidade_0": {"confianca": 0.7}},
    "padrao": 0.5,
}


def _estado(metodo_decisao: str | None, metodo_busca: str | None) -> EstadoCitacao:
    return EstadoCitacao(
        inicio=0,
        fim=4,
        trecho="REsp",
        tipo_bruto="jurisprudencia",
        tem_identificador=True,
        origem="regex_camada1",
        metodo_decisao=metodo_decisao,
        metodo_busca=metodo_busca,
    )


# ── nó ──────────────────────────────────────────────────────────────────────


def test_sem_tabela_confianca_fica_vazia():
    assert calibrar(_estado("cardinalidade_1", "catalogo"), None) == {"confianca": None}
    assert calibrar(_estado("cardinalidade_1", "catalogo"), {}) == {"confianca": None}


@pytest.mark.parametrize(
    ("decisao", "busca", "esperado"),
    [
        ("cardinalidade_1", "catalogo", 0.98),  # faixa fina
        ("cardinalidade_0", "lei_sumula", 0.7),  # recua para metodo_decisao
        ("juiz", "catalogo", 0.5),  # recua para padrao
    ],
    ids=["fina", "grossa", "padrao"],
)
def test_recuo_da_faixa_mais_especifica_para_a_geral(decisao, busca, esperado):
    assert calibrar(_estado(decisao, busca), TABELA)["confianca"] == esperado


def test_confianca_sempre_em_zero_um():
    tabela = {"faixas": {"a|b": {"confianca": 1.7}}, "padrao": -0.2}
    assert confianca_da_tabela(tabela, "a", "b") == 1.0
    assert confianca_da_tabela(tabela, "x", "y") == 0.0


def test_chave_trata_sinal_ausente():
    assert chave_faixa("sem_identificador", None) == "sem_identificador|-"


def test_subgrafo_preenche_confianca_com_tabela():
    """Com tabela no contexto, `calibrar` roda depois de `decidir`; span sem
    identificador vira `sem_identificador|-`."""
    span = EstadoCitacao(
        inicio=0,
        fim=20,
        trecho="precedente do STJ",
        tipo_bruto="jurisprudencia",
        tem_identificador=False,
        origem="heuristica_camada2",
    )
    tabela = {"faixas": {"sem_identificador|-": {"confianca": 0.9}}, "padrao": 0.5}
    (saida,) = rodar_subgrafo_em_spans([span], Contexto(tabela_confianca=tabela))
    assert saida.classificacao == "incompleta"
    assert saida.confianca == 0.9
    (sem_tabela,) = rodar_subgrafo_em_spans([span], Contexto())
    assert sem_tabela.confianca is None


# ── ajuste ──────────────────────────────────────────────────────────────────


def test_casar_segue_iou_minimo_e_um_para_um():
    golds = [{"inicio": 0, "fim": 10}, {"inicio": 50, "fim": 60}]
    preds = [{"inicio": 0, "fim": 9}, {"inicio": 0, "fim": 10}, {"inicio": 50, "fim": 52}]
    # O gold 0 fica com a predição de IoU 1,0; a de IoU 0,2 não casa.
    assert casar(golds, preds) == [(0, 1)]


def test_rotular_exige_id_certo_para_real():
    gabarito = {
        "d1": [
            {"inicio": 0, "fim": 10, "classificacao": "real", "ids": {"7", "8"}},
            {"inicio": 20, "fim": 30, "classificacao": "real", "ids": {"9"}},
            {"inicio": 40, "fim": 50, "classificacao": "inventada", "ids": set()},
        ]
    }
    base = {"metodo_decisao": "cardinalidade_1", "metodo_busca": "catalogo"}
    rastro = {
        "d1": [
            {"inicio": 0, "fim": 10, "classificacao": "real", "id_canonico": 8, **base},
            {"inicio": 20, "fim": 30, "classificacao": "real", "id_canonico": 1, **base},
            {"inicio": 40, "fim": 50, "classificacao": "real", "id_canonico": 2, **base},
            {"inicio": 90, "fim": 99, "classificacao": "inventada", **base},  # sem par
        ]
    }
    assert [r.acerto for r in rotular(rastro, gabarito)] == [1, 0, 0]


def test_ajuste_suaviza_com_laplace():
    rotulos = [Rotulo("d1", "cardinalidade_1", "catalogo", 1)] * 8 + [
        Rotulo("d1", "cardinalidade_0", "catalogo", 0)
    ] * 2
    tabela = ajustar_tabela(rotulos)
    assert tabela["faixas"]["cardinalidade_1|catalogo"] == {
        "confianca": 0.9,
        "acertos": 8,
        "total": 8,
    }
    assert tabela["faixas"]["cardinalidade_0|catalogo"]["confianca"] == 0.25
    assert tabela["padrao"] == round(9 / 12, 4)
    json.dumps(tabela)  # vai para params/ como JSON


def test_tabela_calibrada_bate_confianca_constante():
    """O objetivo do Módulo 5: Brier menor que o de confiança 1,0 em tudo."""
    rotulos = [Rotulo(f"d{i}", "cardinalidade_1", "catalogo", 1) for i in range(20)] + [
        Rotulo(f"d{i}", "cardinalidade_0", "catalogo", i % 4 != 0) for i in range(20)
    ]
    tabela = ajustar_tabela(rotulos)
    constante = {"padrao": 1.0}
    assert brier(rotulos, tabela) < brier(rotulos, constante)
    assert bonus(brier_deixando_um_documento_fora(rotulos)) > bonus(brier(rotulos, constante))


def test_ler_gabarito_aceita_bom_e_varios_ids(tmp_path):
    caminho = tmp_path / "gold.csv"
    caminho.write_text(
        "﻿nivel,documento_id,citacao_id,inicio,fim,trecho,tipo,classificacao,id_canonico\n"
        "1,d1,g1,0,4,REsp,jurisprudencia,real,7:8\n"
        "1,d1,g2,9,12,Lei,lei,inventada,\n",
        encoding="utf-8",
    )
    gold = ler_gabarito(caminho)["d1"]
    assert gold[0]["ids"] == {"7", "8"}
    assert gold[1]["ids"] == set()
