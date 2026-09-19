"""Nó `buscar_no_catalogo` (Módulo 3) — cardinalidade dos candidatos.

A decisão de classe (Módulo 4) não é testada aqui — só que este nó devolve
os sinais certos para ela: 0 candidatos (inventada), 1 (real), 2+ (empate).
"""

from __future__ import annotations

from citacoes.catalogo.esquema import CatalogoCanonico, RegistroCatalogo
from citacoes.dominio.campos import CamposIdentificador, extrair_campos
from citacoes.grafo.estados import EstadoCitacao
from citacoes.nos.buscar_no_catalogo import resolver


def _registro(
    id_: int, numero: str, tribunal: str | None = None, uf: str | None = None
) -> RegistroCatalogo:
    return RegistroCatalogo(
        id=id_,
        documento_id=f"doc_{id_}",
        natureza="acordao",
        tipo="jurisprudencia",
        tribunal=tribunal,
        ano=2020,
        relator="Fulano",
        campos=CamposIdentificador(numero_normalizado=numero, uf=uf),
    )


def _span_normalizado(trecho: str, tipo_bruto: str = "jurisprudencia") -> EstadoCitacao:
    estado = EstadoCitacao(
        inicio=0,
        fim=len(trecho),
        trecho=trecho,
        tipo_bruto=tipo_bruto,
        tem_identificador=True,
        origem="regex_camada1",
    )
    campos, ocr = extrair_campos(trecho, tipo_bruto)
    estado.campos = campos
    estado.ocr_corrigido = ocr
    return estado


def test_cardinalidade_1_candidato_real():
    catalogo = CatalogoCanonico(por_chave={"1234567": [_registro(1, "1234567", tribunal="STJ")]})
    estado = _span_normalizado("REsp 1.234.567/PR")
    atualizacao = resolver(estado, catalogo)
    assert atualizacao["metodo_busca"] == "catalogo"
    assert len(atualizacao["candidatos"]) == 1
    assert atualizacao["candidatos"][0].id == 1


def test_cardinalidade_0_candidatos_numero_inventado():
    catalogo = CatalogoCanonico(por_chave={})
    estado = _span_normalizado("Reclamação nº 66.516/RO")
    atualizacao = resolver(estado, catalogo)
    assert atualizacao["metodo_busca"] == "catalogo"
    assert atualizacao["candidatos"] == []


def test_cardinalidade_2mais_candidatos_empatados():
    catalogo = CatalogoCanonico(
        por_chave={"1234567": [_registro(1, "1234567"), _registro(2, "1234567")]}
    )
    estado = _span_normalizado("REsp 1.234.567/PR")
    atualizacao = resolver(estado, catalogo)
    assert len(atualizacao["candidatos"]) == 2
    assert {c.id for c in atualizacao["candidatos"]} == {1, 2}


def test_sem_identificador_e_sem_busca_e_lista_vazia():
    catalogo = CatalogoCanonico(por_chave={"1234567": [_registro(1, "1234567")]})
    estado = EstadoCitacao(
        inicio=0,
        fim=5,
        trecho="julgado do STF em 2024",
        tipo_bruto="jurisprudencia",
        tem_identificador=False,
        origem="regex_camada1",
    )
    estado.campos = CamposIdentificador()
    atualizacao = resolver(estado, catalogo)
    assert atualizacao == {"candidatos": [], "metodo_busca": "sem_busca"}


def test_lei_e_sumula_usam_metodo_lei_sumula():
    registro_sumula = RegistroCatalogo(
        id=45,
        documento_id="doc_sv45",
        natureza="sumula",
        tipo="jurisprudencia",
        tribunal="STF",
        ano=None,
        relator=None,
        campos=CamposIdentificador(sumula="45", vinculante=True),
    )
    catalogo = CatalogoCanonico(leis_sumulas=[registro_sumula])
    estado = _span_normalizado("Súmula Vinculante nº 45 do STF")
    atualizacao = resolver(estado, catalogo)
    assert atualizacao["metodo_busca"] == "lei_sumula"
    assert atualizacao["candidatos"][0].id == 45
    assert atualizacao["candidatos"][0].score == 1.0


def test_sumula_vinculante_divergente_penaliza_mas_nao_zera():
    registro_sumula = RegistroCatalogo(
        id=45,
        documento_id="doc_sv45",
        natureza="sumula",
        tipo="jurisprudencia",
        tribunal="STF",
        ano=None,
        relator=None,
        campos=CamposIdentificador(sumula="45", vinculante=False),
    )
    catalogo = CatalogoCanonico(leis_sumulas=[registro_sumula])
    estado = _span_normalizado("Súmula Vinculante nº 45 do STF")
    atualizacao = resolver(estado, catalogo)
    assert atualizacao["candidatos"][0].score == 0.5


def test_conflito_duro_de_uf_e_sinalizado_no_candidato():
    catalogo = CatalogoCanonico(por_chave={"1234567": [_registro(1, "1234567", uf="SP")]})
    estado = _span_normalizado("REsp 1.234.567/PR")  # cita UF diferente (PR != SP)
    atualizacao = resolver(estado, catalogo)
    assert atualizacao["candidatos"][0].conflitos_duros == ("uf",)


def test_metodo_sem_busca_implica_candidatos_vazios_invariante():
    catalogo = CatalogoCanonico()
    estado = EstadoCitacao(
        inicio=0,
        fim=5,
        trecho="precedente do STJ",
        tipo_bruto="jurisprudencia",
        tem_identificador=False,
        origem="heuristica_camada2",
    )
    atualizacao = resolver(estado, catalogo)
    if atualizacao["metodo_busca"] == "sem_busca":
        assert atualizacao["candidatos"] == []
