"""Módulo 1 — fronteiras dos spans. Os trechos reproduzem as formas do
gabarito (Níveis 1 e 2), em frases escritas à mão."""

from __future__ import annotations

import pytest

from citacoes.nos.extrair_spans import extrair


def _trechos(texto: str) -> list[str]:
    return [s.trecho for s in sorted(extrair(texto), key=lambda s: s.inicio)]


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Vide o art.\n290 do Código Penal Militar, que", "art.\n290 do Código Penal Militar"),
        ("conforme AgInt no Recurso\nEspecial nº 1.620.021/PR, e", None),
        ("no Recurso Especial Eleitoral nº 2137-73.2014.6.21.0000, que", None),
        ("o Terceiro AG.REG na Rcl nº 62.425/SP, que", "Terceiro AG.REG na Rcl nº 62.425/SP"),
        ("Não se pode ignorar o RR-1835-06.2010.5.15.0042, que", "RR-1835-06.2010.5.15.0042"),
        ("ver processo nº TST-E-RR-173000-49.2008.5.15.0024. Ainda", None),
        ("R-Rp nº 986-96.2010.6.00.0000, rel.", "R-Rp nº 986-96.2010.6.00.0000"),
        ("Agravo Interno na Suspensão\nde Liminar e de Sentença nº 2.883/MA", None),
        ("AgR-AI\xa00603026-6920186090000 e", "AgR-AI\xa00603026-6920186090000"),
        ("AgRg no H.C. Nº 891369 (RS).", "AgRg no H.C. Nº 891369 (RS)"),
        ("R.Esp. n°  1.45g.779-MA, e", "R.Esp. n°  1.45g.779-MA"),
        ("a 5úmula 211 do STJ, e", "5úmula 211 do STJ"),
        ("o Temã 2.680 da repercussão geral.", "Temã 2.680 da repercussão geral"),
    ],
)
def test_span_com_identificador(texto, esperado):
    alvo = esperado or texto.split(", ")[0].split(". ")[0].removeprefix("conforme ")
    alvo = alvo.removeprefix("no ").removeprefix("ver ")
    assert _trechos(texto) == [alvo]


def test_numero_nao_atravessa_linha_em_branco():
    assert _trechos("Ag. Int. No 7001184-1520197000000.\n\nI - Relatório") == [
        "Ag. Int. No 7001184-1520197000000"
    ]


def test_uf_so_vale_sigla_de_estado():
    assert _trechos("o REsp 1.234.567/do que se") == ["REsp 1.234.567"]


@pytest.mark.parametrize(
    "incompleta",
    [
        "julgado do STF proferido em 2024 pela relatoria de Dias Toffoli",
        "precedente do STM de 2023, da relatoria de Marco Antonio",
        "Reclamação\ndo STF, de 2025, Rel. Min. CRISTIANO ZANIN",
        "Agravo em Recurso Especial do STJ,\nde 2023, Rel. Min. Assusete Magalhães",
        "Rcl de 2021, Rel.\nMin. Rosa Weber",
        "APL de 2023, Rel. Min.\nLEONARDO PUNTEL",
        "acórdão do STM julgado em 2021 sob relatoria de ARTUR VIDIGAL\nDE OLIVEIRA",
    ],
)
def test_incompleta_termina_no_nome_do_relator(incompleta):
    texto = f"Conforme o {incompleta}, no ponto em que e Referência: autos"
    spans = extrair(texto)
    assert [s.trecho for s in spans] == [incompleta]
    assert spans[0].tem_identificador is False


def test_autos_do_proprio_documento_sao_distrator():
    assert _trechos("Referência: autos nº 1163463-72.2016.8.03.1749\nElaborado por") == []


def test_cnj_dentro_de_span_maior_nao_duplica():
    assert len(extrair("no Recurso Especial Eleitoral nº 2137-73.2014.6.21.0000.")) == 1
