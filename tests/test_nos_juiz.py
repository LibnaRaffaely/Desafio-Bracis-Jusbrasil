"""Agente-Juiz (`agentes/juiz.py`) com `BackendFalso`: prompt, parsing
defensivo, validação por pertinência e integração com `decidir`. Tudo
sintético, em CPU; nenhum teste carrega modelo nem abre arquivo."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from hypothesis import given
from hypothesis import strategies as st

from citacoes.agentes.juiz import (
    CONTEXTO_INDISPONIVEL,
    PROMPT_JUIZ,
    BackendFalso,
    BackendTransformers,
    ContextoDecisao,
    JuizLLM,
)
from citacoes.catalogo.esquema import Candidato, CatalogoCanonico, RegistroCatalogo
from citacoes.dominio.campos import CamposIdentificador
from citacoes.grafo.estados import EstadoCitacao
from citacoes.nos.decidir import ParametrosDecisao, decidir

COM_JUIZ = ParametrosDecisao(habilitar_juiz=True)


def _candidato(id_: int, tribunal: str | None = "TSE", brandas: tuple[str, ...] = ()) -> Candidato:
    return Candidato(
        id=id_, tribunal=tribunal, natureza="acordao", score=1.0, divergencias_brandas=brandas
    )


def _estado(candidatos: list[Candidato], trecho: str = "REsp 1.234.567/PR") -> EstadoCitacao:
    return EstadoCitacao(
        inicio=0,
        fim=len(trecho),
        trecho=trecho,
        tipo_bruto="jurisprudencia",
        tem_identificador=True,
        origem="regex_camada1",
        campos=CamposIdentificador(classe="REsp", tribunal="STJ", uf="PR"),
        candidatos=candidatos,
        metodo_busca="catalogo",
    )


def _decidir_com(
    resposta: str, candidatos: list[Candidato] | None = None
) -> tuple[dict, BackendFalso]:
    backend = BackendFalso(resposta)
    candidatos = candidatos if candidatos is not None else [_candidato(1), _candidato(2)]
    return decidir(_estado(candidatos), COM_JUIZ, JuizLLM(backend)), backend


# ── desfechos do juiz via decidir ──────────────────────────────────────────


def test_resposta_valida_com_id_da_lista_vira_real_com_metodo_juiz():
    saida, backend = _decidir_com('{"id_canonico": 2, "justificativa": "relator bate"}')
    assert saida["classificacao"] == "real"
    assert saida["id_canonico"] == 2
    assert saida["metodo_decisao"] == "juiz"
    assert len(backend.chamadas) == 1


def test_resposta_com_id_fora_da_lista_vira_incompleta_com_metodo_juiz():
    saida, _ = _decidir_com('{"id_canonico": 3, "justificativa": "plausível, mas inventado"}')
    assert saida["classificacao"] == "incompleta"
    assert saida["id_canonico"] is None
    assert saida["metodo_decisao"] == "juiz"


def test_resposta_declarando_indecisao_vira_incompleta():
    saida, _ = _decidir_com('{"id_canonico": null, "justificativa": "sem sinal decisivo"}')
    assert saida["classificacao"] == "incompleta"
    assert saida["metodo_decisao"] == "juiz"


@pytest.mark.parametrize(
    "resposta",
    [
        "",
        "   \n",
        "{",
        '{"id_canonico": 1, "justificativa": }',
        "não consigo decidir",
        "[1, 2]",
        '"1"',
        '{"id_canonico": 1.0}',
        '{"id_canonico": true}',
        '{"id_canonico": [1]}',
        '{"id_canonico": "um"}',
        '{"justificativa": "sem id"}',
        "```json\n{\n",
    ],
)
def test_saida_malformada_vira_incompleta_sem_excecao(resposta):
    saida, _ = _decidir_com(resposta)
    assert saida["classificacao"] == "incompleta"
    assert saida["id_canonico"] is None
    assert saida["metodo_decisao"] == "juiz"


@pytest.mark.parametrize(
    "resposta",
    [
        '```json\n{"id_canonico": 2, "justificativa": "x"}\n```',
        '```\n{"id_canonico": 2}\n```',
        'Claro! Aqui está a resposta:\n{"id_canonico": 2, "justificativa": "x"}\nEspero ter ajudado.',
        '{"id_canonico": "2", "justificativa": "x"}',
        '{"justificativa": "x", "id_canonico": 2}',
    ],
)
def test_cerca_de_markdown_texto_extra_e_string_numerica_sao_aceitos(resposta):
    saida, _ = _decidir_com(resposta)
    assert saida["classificacao"] == "real"
    assert saida["id_canonico"] == 2


def test_juiz_desligado_com_dois_candidatos_nao_chama_o_backend():
    backend = BackendFalso('{"id_canonico": 1}')
    saida = decidir(_estado([_candidato(1), _candidato(2)]), ParametrosDecisao(), JuizLLM(backend))
    assert saida["metodo_decisao"] == "cardinalidade_2mais"
    assert backend.chamadas == []


def test_juiz_nao_e_chamado_com_menos_de_dois_candidatos():
    backend = BackendFalso('{"id_canonico": 1}')
    juiz = JuizLLM(backend)
    assert juiz.julgar(_estado([]), []) == ContextoDecisao(
        None, "juiz não consultado: menos de 2 candidatos"
    )
    assert juiz.escolher(_estado([_candidato(1)]), [_candidato(1)]) is None
    assert backend.chamadas == []


# ── prompt ──────────────────────────────────────────────────────────────────


def test_prompt_e_identico_entre_duas_execucoes_com_a_mesma_entrada():
    juiz = JuizLLM(BackendFalso())
    candidatos = [_candidato(2), _candidato(1)]
    a = juiz.montar_prompt(_estado(candidatos), candidatos)
    b = juiz.montar_prompt(_estado(list(candidatos)), list(candidatos))
    assert a == b


def test_prompt_nao_depende_da_ordem_dos_candidatos():
    juiz = JuizLLM(BackendFalso())
    a = juiz.montar_prompt(_estado([]), [_candidato(1), _candidato(2), _candidato(3)])
    b = juiz.montar_prompt(_estado([]), [_candidato(3), _candidato(1), _candidato(2)])
    assert a == b
    assert a.index("id=1") < a.index("id=2") < a.index("id=3")


def test_prompt_traz_trecho_campos_ids_validos_e_declara_a_lacuna_do_contexto():
    juiz = JuizLLM(BackendFalso())
    prompt = juiz.montar_prompt(
        _estado([], trecho="REsp\n1.234.567/PR"), [_candidato(10), _candidato(20)]
    )
    assert "REsp 1.234.567/PR" in prompt  # quebra de linha colapsada
    assert "classe=REsp" in prompt and "uf=PR" in prompt
    assert "ids válidos: 10, 20" in prompt
    assert CONTEXTO_INDISPONIVEL in prompt
    assert "null" in prompt and "preferível a chutar" in prompt
    assert set(PROMPT_JUIZ.get_identifiers()) == {
        "trecho",
        "campos",
        "contexto",
        "ids",
        "candidatos",
    }


def test_prompt_enriquece_ano_e_relator_pelo_catalogo_quando_disponivel():
    registro = RegistroCatalogo(
        id=10,
        documento_id="doc_0001",
        natureza="acordao",
        tipo="jurisprudencia",
        tribunal="TSE",
        ano=2016,
        relator="Gilmar Mendes",
        campos=CamposIdentificador(),
    )
    catalogo = CatalogoCanonico(registros=[registro])
    prompt = JuizLLM(BackendFalso(), catalogo).montar_prompt(
        _estado([]), [_candidato(10), _candidato(20, tribunal=None, brandas=("classe",))]
    )
    assert "id=10 | tribunal=TSE | natureza=acordao | ano=2016 | relator=Gilmar Mendes" in prompt
    assert (
        "id=20 | tribunal=? | natureza=acordao | ano=? | relator=? | divergencias_brandas=classe"
        in prompt
    )


def test_backend_recebe_exatamente_o_prompt_montado():
    backend = BackendFalso('{"id_canonico": null}')
    juiz = JuizLLM(backend)
    candidatos = [_candidato(1), _candidato(2)]
    juiz.julgar(_estado(candidatos), candidatos)
    assert backend.chamadas == [juiz.montar_prompt(_estado(candidatos), candidatos)]


# ── justificativa ───────────────────────────────────────────────────────────


def test_justificativa_e_devolvida_por_julgar_e_nunca_entra_na_saida_de_decidir():
    backend = BackendFalso('{"id_canonico": 1, "justificativa": "relator e ano batem"}')
    juiz = JuizLLM(backend)
    candidatos = [_candidato(1), _candidato(2)]
    assert juiz.julgar(_estado(candidatos), candidatos) == ContextoDecisao(1, "relator e ano batem")
    saida = decidir(_estado(candidatos), COM_JUIZ, juiz)
    assert set(saida) == {"classificacao", "id_canonico", "tipo", "metodo_decisao"}


def test_id_fora_da_lista_registra_o_motivo_na_justificativa():
    juiz = JuizLLM(BackendFalso('{"id_canonico": 99, "justificativa": "x"}'))
    candidatos = [_candidato(1), _candidato(2)]
    resultado = juiz.julgar(_estado(candidatos), candidatos)
    assert resultado.id_canonico is None
    assert "fora dos candidatos" in resultado.justificativa and "99" in resultado.justificativa


# ── backend real: só o envelope, sem carregar nada ─────────────────────────


def test_backend_transformers_exige_revisao_fixa_para_repositorio_remoto():
    with pytest.raises(ValueError, match="revisão"):
        BackendTransformers(repositorio="org/modelo")
    assert BackendTransformers(repositorio="org/modelo", revisao="abc123").revisao == "abc123"


def test_backend_transformers_aceita_caminho_local_sem_revisao(tmp_path):
    backend = BackendTransformers(repositorio=str(tmp_path))
    assert backend.revisao is None
    assert backend.seed == 42


# ── propriedades ────────────────────────────────────────────────────────────

_ids = st.integers(min_value=1, max_value=10**10)
_candidatos = st.lists(
    st.builds(_candidato, id_=_ids), min_size=2, max_size=5, unique_by=lambda c: c.id
)
_lixo = st.text(max_size=40)
_respostas = st.one_of(
    _lixo,
    _ids.map(lambda i: f'{{"id_canonico": {i}, "justificativa": "x"}}'),
    _lixo.map(lambda t: f'```json\n{{"id_canonico": null, "justificativa": {t!r}}}\n```'),
    st.builds(lambda i, t: f'{t}{{"id_canonico": {i}}}{t}', _ids, _lixo),
)


@given(candidatos=_candidatos, resposta=_respostas)
def test_propriedade_id_devolvido_pertence_aos_candidatos_ou_e_none(candidatos, resposta):
    resultado = JuizLLM(BackendFalso(resposta)).julgar(_estado(candidatos), candidatos)
    assert resultado.id_canonico is None or resultado.id_canonico in {c.id for c in candidatos}
    assert isinstance(resultado.justificativa, str)


@given(candidatos=_candidatos, resposta=_respostas)
def test_propriedade_parsing_nunca_levanta_excecao(candidatos, resposta):
    JuizLLM.parsear(resposta)
    saida = decidir(_estado(candidatos), COM_JUIZ, JuizLLM(BackendFalso(resposta)))
    assert saida["metodo_decisao"] == "juiz"
    assert (saida["classificacao"] == "real") == (saida["id_canonico"] is not None)


@dataclass(frozen=True)
class _BackendContador:
    chamadas: list[str] = field(default_factory=list)

    def gerar(self, prompt: str) -> str:
        self.chamadas.append(prompt)
        return '{"id_canonico": null}'


@given(candidatos=_candidatos)
def test_propriedade_mesma_entrada_mesmo_prompt(candidatos):
    backend = _BackendContador()
    juiz = JuizLLM(backend)
    juiz.julgar(_estado(candidatos), candidatos)
    juiz.julgar(_estado(list(reversed(candidatos))), list(reversed(candidatos)))
    assert len(backend.chamadas) == 2 and backend.chamadas[0] == backend.chamadas[1]
