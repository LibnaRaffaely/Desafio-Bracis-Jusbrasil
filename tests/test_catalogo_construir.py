"""Módulo 3 — construção offline do catálogo canônico."""

from __future__ import annotations

import sqlite3

from src.citacoes.catalogo.construir import carregar, construir_catalogo, salvar
from src.citacoes.catalogo.esquema import CatalogoCanonico, RegistroCatalogo


def test_construir_catalogo_indexa_jurisprudencia_por_chave(conexao_documentos):
    catalogo = construir_catalogo(conexao_documentos)
    assert len(catalogo.registros) == 5
    assert set(catalogo.por_chave.keys()) == {"70004494020237000000", "1307026"}
    assert catalogo.por_chave["70004494020237000000"][0].id == 5665364632


def test_sumulas_e_dispositivos_vao_para_leis_sumulas_nao_por_chave(conexao_documentos):
    catalogo = construir_catalogo(conexao_documentos)
    ids = {r.id for r in catalogo.leis_sumulas}
    assert ids == {900045, 900331, 800927}
    naturezas_indexadas = {r.natureza for regs in catalogo.por_chave.values() for r in regs}
    assert naturezas_indexadas == {"acordao"}


def test_registro_leis_sumulas_tem_campos_certos(conexao_documentos):
    catalogo = construir_catalogo(conexao_documentos)
    por_id = {r.id: r for r in catalogo.leis_sumulas}
    assert por_id[900045].campos.sumula == "45"
    assert por_id[900045].campos.vinculante is True
    assert por_id[900331].campos.sumula == "331"
    assert por_id[900331].campos.vinculante is False
    assert por_id[800927].campos.diploma == "CPC"
    assert por_id[800927].campos.artigo == "927"


def test_relatorio_colisoes_vazio_sem_duplicata(conexao_documentos):
    catalogo = construir_catalogo(conexao_documentos)
    assert catalogo.relatorio_colisoes() == {}


def test_relatorio_colisoes_detecta_chave_repetida():
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE documentos (documento_id TEXT, id INTEGER, tribunal TEXT, "
        "ano INTEGER, relator TEXT, natureza TEXT, tipo TEXT, texto TEXT)"
    )
    con.executemany(
        "INSERT INTO documentos VALUES (?,?,?,?,?,?,?,?)",
        [
            (
                "doc_a",
                1,
                "STJ",
                2020,
                "X",
                "acordao",
                "jurisprudencia",
                "REsp 1.234.567/PR\n\ncorpo",
            ),
            (
                "doc_b",
                2,
                "STF",
                2021,
                "Y",
                "acordao",
                "jurisprudencia",
                "REsp 1.234.567/PR\n\noutro corpo",
            ),
        ],
    )
    con.commit()
    catalogo = construir_catalogo(con)
    colisoes = catalogo.relatorio_colisoes()
    assert colisoes == {"1234567": [1, 2]}


def test_buscar_jurisprudencia_chave_ausente_devolve_vazio(conexao_documentos):
    catalogo = construir_catalogo(conexao_documentos)
    assert catalogo.buscar_jurisprudencia("99999999999") == []
    assert catalogo.buscar_jurisprudencia(None) == []


def test_salvar_e_carregar_preserva_indices(conexao_documentos, tmp_path):
    catalogo = construir_catalogo(conexao_documentos)
    caminho = tmp_path / "catalogo.json"
    salvar(catalogo, caminho)
    recarregado = carregar(caminho)

    assert isinstance(recarregado, CatalogoCanonico)
    assert len(recarregado.registros) == len(catalogo.registros)
    assert recarregado.por_chave.keys() == catalogo.por_chave.keys()
    assert {r.id for r in recarregado.leis_sumulas} == {r.id for r in catalogo.leis_sumulas}
    exemplo: RegistroCatalogo = recarregado.por_chave["70004494020237000000"][0]
    assert exemplo.tribunal == "STM"
    assert exemplo.campos.classe == "APL"
