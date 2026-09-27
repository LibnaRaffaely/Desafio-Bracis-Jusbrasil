"""Número próprio dos acórdãos no catálogo e as regras de casamento que
protegem contra o erro caro (inventada marcada como real). Cabeçalhos
sintéticos no formato de cada tribunal da base; nenhum dado real."""

from __future__ import annotations

import pytest

from citacoes.catalogo.construir import indexar, numeros_proprios_acordao
from citacoes.catalogo.esquema import CatalogoCanonico, RegistroCatalogo
from citacoes.dominio.campos import CamposIdentificador, extrair_campos

TST = (
    "A C Ó R D Ã O SbDI-1 GMJRP EMBARGOS DE DECLARAÇÃO. RECURSO REGIDO PELA LEI Nº "
    "13.015/2014. " + "Ementa longa do acórdão. " * 60 + "Vistos, relatados e discutidos "
    "estes autos de Embargos de Declaração em Recurso de Revista nº "
    "TST-ED-E-ED-RR-3400-05.2011.5.21.0009, em que é Embargante FULANO."
)


@pytest.mark.parametrize(
    ("texto", "tribunal", "esperado"),
    [
        # TST: número só na fórmula dos autos, depois do teto do cabeçalho;
        # a "LEI Nº 13.015/2014" do cabeçalho não é o número do processo.
        (TST, "TST", ("34000520115210009",)),
        # TSE: a súmula citada no cabeçalho não apaga o número.
        (
            "TRIBUNAL SUPERIOR ELEITORAL ACÓRDÃO AGRAVO REGIMENTAL NO AGRAVO DE "
            "INSTRUMENTO Nº 0606252-11.2018.6.26.0000 - SÃO PAULO Relator: Ministro X. "
            "Incide a Súmula nº 72 do TSE.",
            "TSE",
            ("06062521120186260000",),
        ),
        # STJ: número de 4 dígitos no rótulo; o registro entre parênteses e a
        # OAB colada a letras não servem.
        (
            "Superior Tribunal de Justiça AgInt na SUSPENSÃO DE LIMINAR E DE SENTENÇA "
            "Nº 2.883 - MA (2021/0030002-4) RELATOR : MINISTRO X ADVOGADO : Y - DF011498",
            "STJ",
            ("2883",),
        ),
        # STF: sem rótulo; a data não é número, e o CNJ do processo de origem
        # que vem depois não é o da reclamação.
        (
            "22/04/2026 PRIMEIRA TURMA AG.REG. NA RECLAMAÇÃO 76.532 RIO DE JANEIRO "
            "RELATOR : MIN. X. Processo nº 5097324-27.2023.4.02.5101",
            "STF",
            ("76532",),
        ),
        # TSE com número curto e CNJ entre parênteses: os dois identificam.
        (
            "TRIBUNAL SUPERIOR ELEITORAL ACÓRDÃO RECURSO ORDINÁRIO Nº 1.662 "
            "( 47142-16.2008.6.00.0000) - CLASSE 37 -GOIÂNIA",
            "TSE",
            ("1662", "471421620086000000"),
        ),
        # STM: datas da ata antes do rótulo; CNJ com espaço solto.
        (
            "Poder Judiciário STM EXTRATO DE ATA DA SESSÃO VIRTUAL DE 18/09/2023 A "
            "21/09/2023 EMBARGOS INFRINGENTES E DE NULIDADE Nº 7000380- "
            "08.2023.7.00.0000/DF RELATOR: MINISTRO X",
            "STM",
            ("70003800820237000000",),
        ),
        # Ano solto não é número de processo.
        (
            "EXTRATO DA ATA DA 52a SESSÃO DE JULGAMENTO. EM 29 DE AGOSTO DE 2017",
            "STM",
            (),
        ),
    ],
    ids=["tst_autos", "tse_sumula", "stj_4_digitos", "stf_rcl", "tse_alias", "stm_ata", "ano"],
)
def test_numeros_proprios_por_tribunal(texto, tribunal, esperado):
    assert numeros_proprios_acordao(texto, tribunal) == esperado


def test_numero_do_catalogo_bate_com_o_da_citacao():
    """As duas pontas precisam chegar à mesma chave."""
    (numero,) = numeros_proprios_acordao(TST, "TST")
    campos, _ = extrair_campos("TST-ED-E-ED-RR-3400-05.2011.5.21.0009", "jurisprudencia")
    assert campos.numero_normalizado == numero


def _registro(id_: int, numero: str, alternativos: tuple[str, ...] = ()) -> RegistroCatalogo:
    return RegistroCatalogo(
        id=id_,
        documento_id=f"doc_{id_}",
        natureza="acordao",
        tipo="jurisprudencia",
        tribunal="TSE",
        ano=None,
        relator=None,
        campos=CamposIdentificador(numero_normalizado=numero),
        numeros_alternativos=alternativos,
    )


def test_indice_inclui_numeros_alternativos():
    catalogo = indexar([_registro(1, "1662", ("471421620086000000",))])
    assert [r.id for r in catalogo.buscar_jurisprudencia("1662")] == [1]
    assert [r.id for r in catalogo.buscar_jurisprudencia("471421620086000000")] == [1]


def _lei_sumula(**campos) -> RegistroCatalogo:
    natureza = "sumula" if "sumula" in campos else "dispositivo"
    return RegistroCatalogo(
        id=7,
        documento_id="d7",
        natureza=natureza,
        tipo="jurisprudencia" if natureza == "sumula" else "lei",
        tribunal=campos.get("tribunal"),
        ano=None,
        relator=None,
        campos=CamposIdentificador(**campos),
    )


@pytest.mark.parametrize(
    ("citacao", "registro", "casa"),
    [
        ("Súmula 83 do STJ", {"sumula": "83", "tribunal": "STJ"}, True),
        ("Súmula 83 do TSE", {"sumula": "83", "tribunal": "STJ"}, False),
        ("Súm. 331 do TST", {"sumula": "331", "tribunal": "TST"}, True),
        ("art. 818 da CLT", {"artigo": "818", "diploma": "CLT"}, True),
        # Lei fora da base: sem diploma reconhecido, o número do artigo não basta.
        ("art. 1 da Lei nº 9.504/1997", {"artigo": "1", "diploma": "LC64"}, False),
        # Ruído de letra no nome do diploma ainda é reconhecido.
        ("art. 7º da Constituição Fedcral", {"artigo": "7", "diploma": "CF"}, True),
    ],
    ids=["sumula", "sumula_outro_tribunal", "sum_abreviada", "artigo", "lei_fora", "cf_ruido"],
)
def test_casamento_de_lei_e_sumula(citacao, registro, casa):
    tipo = "lei" if citacao.startswith("art") else "jurisprudencia"
    campos, _ = extrair_campos(citacao, tipo)
    catalogo = CatalogoCanonico(leis_sumulas=[_lei_sumula(**registro)])
    assert bool(catalogo.buscar_lei_sumula(campos)) is casa
