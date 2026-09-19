"""Módulo 2 — extração de campos estruturados (dominio/campos.py)."""

from __future__ import annotations

from citacoes.dominio.campos import extrair_campos


def test_jurisprudencia_numero_classe_uf():
    campos, ocr = extrair_campos("APL nº 7000449-40.2023.7.00.0000/RS", "jurisprudencia")
    assert campos.numero_normalizado == "70004494020237000000"
    assert campos.classe == "APL"
    assert campos.uf == "RS"
    assert ocr is False


def test_lei_artigo_paragrafo_inciso_alinea():
    campos, _ = extrair_campos("art. 5º, § 3º, inciso IV, alínea a, da CF", "lei")
    assert campos.diploma == "CF"
    assert campos.artigo == "5"
    assert campos.paragrafo == "3"
    assert campos.inciso == "IV"
    assert campos.alinea == "a"


def test_lei_paragrafo_unico():
    campos, _ = extrair_campos("art. 927, parágrafo único, do CPC", "lei")
    assert campos.artigo == "927"
    assert campos.paragrafo == "único"


def test_sumula_vinculante():
    campos, _ = extrair_campos("Súmula Vinculante nº 45 do STF", "jurisprudencia")
    assert campos.sumula == "45"
    assert campos.vinculante is True
    assert campos.tribunal == "STF"


def test_sumula_nao_vinculante():
    campos, _ = extrair_campos("Súmula 331 do TST", "jurisprudencia")
    assert campos.sumula == "331"
    assert campos.vinculante is False


def test_mencao_vaga_sem_identificador_fica_vazia():
    # Extração (Módulo 1) já marcaria tem_identificador=False aqui; se
    # ainda assim passar por normalizar(), os campos numéricos ficam None.
    campos, ocr = extrair_campos(
        "julgado do STF proferido em 2024 pela relatoria de Dias Toffoli",
        "jurisprudencia",
    )
    assert campos.numero_normalizado is None
    assert campos.sumula is None
    assert ocr is False


def test_ocr_corrigido_propaga_do_trecho_inteiro():
    _, ocr = extrair_campos("REsp 1.234.S67/PR", "jurisprudencia")
    assert ocr is True
