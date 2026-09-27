"""Orquestração (grafo/ e rodar.py) — roteamento com agentes desligados,
contexto chegando ao subgrafo, saída de todo documento e invariantes da
submissão. Os testes sintéticos não abrem a base nem os .txt reais; os dois
últimos (determinismo e e2e) rodam sobre os dados do desafio e só executam
com `CITACOES_DADOS=/caminho/da/pasta_do_desafio`."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from langgraph.types import Send

from citacoes.catalogo.esquema import CatalogoCanonico, RegistroCatalogo
from citacoes.dominio.campos import extrair_campos
from citacoes.grafo import montagem
from citacoes.grafo.estados import Contexto, EstadoCitacao, EstadoDocumento
from citacoes.grafo.roteamento import distribuir, rota_apos_extrair, rota_apos_normalizar
from citacoes.rodar import InvarianteQuebrada, rodar_subgrafo_em_spans, validar

TRECHO_REAL = "REsp 1.234.567/PR"
ID_REAL = 4242


def _span(
    inicio: int, trecho: str, tem_identificador: bool = True, tipo_bruto: str = "jurisprudencia"
) -> EstadoCitacao:
    return EstadoCitacao(
        inicio=inicio,
        fim=inicio + len(trecho),
        trecho=trecho,
        tipo_bruto=tipo_bruto,
        tem_identificador=tem_identificador,
        origem="regex_camada1",
    )


def _catalogo_com(trecho: str, id_: int) -> CatalogoCanonico:
    campos, _ = extrair_campos(trecho, "jurisprudencia")
    registro = RegistroCatalogo(
        id=id_,
        documento_id=f"doc_{id_}",
        natureza="acordao",
        tipo="jurisprudencia",
        tribunal="STJ",
        ano=2020,
        relator="Fulano",
        campos=campos,
    )
    return CatalogoCanonico(registros=[registro], por_chave={campos.numero_normalizado: [registro]})


def _texto_com(spans_em: dict[int, str], tamanho: int = 400) -> str:
    texto = [" "] * tamanho
    for inicio, trecho in spans_em.items():
        texto[inicio : inicio + len(trecho)] = trecho
    return "".join(texto)


def _grafo_com_spans(monkeypatch, spans: list[EstadoCitacao]):
    """Grafo do documento com `extrair_spans` trocado por uma lista fixa —
    isola a orquestração das regex do Módulo 1."""

    def extrair_fixo(estado: EstadoDocumento) -> dict:
        return {"spans": list(spans)}

    monkeypatch.setattr(montagem, "extrair_spans", extrair_fixo)
    return montagem.montar_grafo_documento()


# ── roteamento ──────────────────────────────────────────────────────────────


class _RuntimeFalso:
    def __init__(self, context: Contexto) -> None:
        self.context = context


def test_distribuir_sem_spans_vai_direto_para_reunir():
    assert distribuir(EstadoDocumento(documento_id="d", spans=[])) == "reunir_e_formatar"


def test_distribuir_um_send_por_span():
    spans = [_span(0, "a" * 10), _span(20, "b" * 10)]
    envios = distribuir(EstadoDocumento(spans=spans))
    assert [e.node for e in envios] == ["processar_citacao"] * 2
    assert all(isinstance(e, Send) for e in envios)
    assert [e.arg for e in envios] == spans


def test_rota_apos_extrair_respeita_a_flag():
    estado = EstadoDocumento(spans=[])
    assert rota_apos_extrair(estado, _RuntimeFalso(Contexto())) == "reunir_e_formatar"
    ligado = _RuntimeFalso(Contexto(usar_extrator_llm=True))
    assert rota_apos_extrair(estado, ligado) == "agente_extrator"


def test_rota_apos_normalizar():
    assert rota_apos_normalizar(_span(0, "julgado do STF", tem_identificador=False)) == "decidir"
    assert rota_apos_normalizar(_span(0, TRECHO_REAL)) == "buscar_no_catalogo"


def test_agentes_inexistentes_sao_recusados_na_montagem():
    with pytest.raises(NotImplementedError):
        montagem.montar_grafo_documento(usar_extrator_llm=True)
    with pytest.raises(NotImplementedError):
        montagem.montar_subgrafo_citacao(usar_parser_llm=True)


# ── subgrafo ────────────────────────────────────────────────────────────────


def test_sem_identificador_vai_direto_para_decidir():
    # catalogo=None: se `buscar_no_catalogo` rodasse, levantaria RuntimeError.
    (saida,) = rodar_subgrafo_em_spans(
        [_span(0, "julgado do STF de 2021", tem_identificador=False)], Contexto(catalogo=None)
    )
    assert saida.metodo_busca is None
    assert saida.candidatos == []
    assert saida.classificacao == "incompleta"
    assert saida.metodo_decisao == "sem_identificador"
    assert saida.id_canonico is None


def test_subgrafo_resolve_pelo_catalogo_do_contexto():
    (saida,) = rodar_subgrafo_em_spans(
        [_span(0, TRECHO_REAL)], Contexto(catalogo=_catalogo_com(TRECHO_REAL, ID_REAL))
    )
    assert saida.metodo_busca == "catalogo"
    assert (saida.classificacao, saida.id_canonico) == ("real", ID_REAL)


# ── grafo do documento ──────────────────────────────────────────────────────


def test_contexto_chega_aos_nos_do_subgrafo(tmp_path, monkeypatch):
    """O único caminho para `real` com este id é `buscar_no_catalogo` ler
    `runtime.context.catalogo` dentro do subgrafo chamado por
    `processar_citacao`."""
    texto = _texto_com({100: TRECHO_REAL})
    caminho = tmp_path / "doc_ctx.txt"
    caminho.write_text(texto, encoding="utf-8")
    grafo = _grafo_com_spans(monkeypatch, [_span(100, TRECHO_REAL)])

    resultado = grafo.invoke(
        {"caminho": str(caminho)}, context=Contexto(catalogo=_catalogo_com(TRECHO_REAL, ID_REAL))
    )
    (citacao,) = resultado["saida"]["citacoes"]
    assert citacao["classificacao"] == "real"
    assert citacao["resolucao"] == {"id_canonico": ID_REAL}


def test_documento_sem_citacao_aparece_com_lista_vazia(tmp_path):
    caminho = tmp_path / "doc_vazio.txt"
    caminho.write_text("Relatório.\n\nNada a citar neste despacho.\n", encoding="utf-8")
    grafo = montagem.montar_grafo_documento()
    resultado = grafo.invoke(
        {"caminho": str(caminho)}, context=Contexto(catalogo=CatalogoCanonico())
    )
    assert resultado["spans"] == []
    assert resultado["saida"] == {"documento_id": "doc_vazio", "citacoes": []}


def test_saida_ordenada_por_inicio_com_spans_fora_de_ordem(tmp_path, monkeypatch):
    trechos = {300: "Súmula 999 do STJ", 20: "julgado do STF de 2021", 150: TRECHO_REAL}
    caminho = tmp_path / "doc_ordem.txt"
    caminho.write_text(_texto_com(trechos), encoding="utf-8")
    spans = [
        _span(300, trechos[300]),
        _span(20, trechos[20], tem_identificador=False),
        _span(150, trechos[150]),
    ]
    grafo = _grafo_com_spans(monkeypatch, spans)

    resultado = grafo.invoke(
        {"caminho": str(caminho)}, context=Contexto(catalogo=_catalogo_com(TRECHO_REAL, ID_REAL))
    )
    assert [c["inicio"] for c in resultado["saida"]["citacoes"]] == [20, 150, 300]


def test_flags_desligadas_nao_carregam_llm(tmp_path):
    """Com tudo desligado, `modelo_llm` é None e nenhuma biblioteca de LLM é
    importada. De `agentes/`, só `agentes.juiz` entra, e só porque
    `nos/decidir.py` o importa no topo do módulo (não carrega modelo)."""
    caminho = tmp_path / "doc.txt"
    caminho.write_text("Relatório.\n\nNada a citar.\n", encoding="utf-8")
    codigo = f"""
import sys
from citacoes.catalogo.esquema import CatalogoCanonico
from citacoes.grafo.estados import Contexto
from citacoes.rodar import _argumentos, carregar_modelo, rodar_documentos
modelo = carregar_modelo(_argumentos([]))
rodar_documentos([{str(caminho)!r}], Contexto(catalogo=CatalogoCanonico(), modelo_llm=modelo))
llm = sorted(m for m in sys.modules
             if m.split('.')[0] in {{'langchain_community', 'llama_cpp', 'torch', 'transformers'}})
agentes = sorted(m for m in sys.modules if m.startswith('citacoes.agentes'))
print(modelo, llm, agentes)
"""
    saida = subprocess.run(
        [sys.executable, "-c", codigo], capture_output=True, text=True, check=True
    ).stdout.split(maxsplit=1)
    assert saida[0] == "None"
    assert saida[1].strip() == "[] ['citacoes.agentes', 'citacoes.agentes.juiz']"


# ── invariantes da submissão ────────────────────────────────────────────────


def _resultado(texto: str, citacoes: list[dict]) -> dict:
    return {"texto": texto, "saida": {"documento_id": "d1", "citacoes": citacoes}}


def _citacao(texto: str, inicio: int, fim: int, **extra) -> dict:
    base = {"inicio": inicio, "fim": fim, "trecho": texto[inicio:fim], "tipo": "lei"}
    base.update({"classificacao": "inventada"} | extra)
    return base


def _submissao(tmp_path: Path, celula: str) -> Path:
    caminho = tmp_path / "submission.csv"
    caminho.write_text(f"documento_id,citacoes\nd1,{celula}\n", encoding="utf-8")
    return caminho


def test_validar_aceita_saida_coerente(tmp_path):
    texto = "x" * 100
    citacoes = [_citacao(texto, 0, 10), _citacao(texto, 50, 60, confianca=0.5)]
    validar([_resultado(texto, citacoes)], ["d1"], _submissao(tmp_path, '"0,10,..."'))


@pytest.mark.parametrize(
    "citacoes",
    [
        [{"classificacao": "real"}],
        [{"classificacao": "inventada", "resolucao": {"id_canonico": 1}}],
        [{"confianca": 1.5}],
        [{}, {"inicio": 2, "fim": 11}],
    ],
    ids=["real_sem_id", "id_sem_real", "confianca_fora", "iou_alto"],
)
def test_validar_falha_alto(tmp_path, citacoes):
    texto = "x" * 100
    copias = [dict(c) for c in citacoes]
    montadas = [_citacao(texto, c.pop("inicio", 0), c.pop("fim", 10), **c) for c in copias]
    with pytest.raises(InvarianteQuebrada):
        validar([_resultado(texto, montadas)], ["d1"], _submissao(tmp_path, "-"))


def test_validar_exige_todo_documento_na_submissao(tmp_path):
    with pytest.raises(InvarianteQuebrada, match="ausentes"):
        validar([_resultado("abc", [])], ["d1", "d2"], _submissao(tmp_path, "-"))


# ── dados reais (opcional) ──────────────────────────────────────────────────

DADOS = Path(os.environ.get("CITACOES_DADOS", "data"))
_TEM_DADOS = all(
    (DADOS / nome).exists()
    for nome in ("txt", "desafio1_bracis.db", "goldenset_offsets.csv", "json_to_submission.py")
)
com_dados = pytest.mark.skipif(
    not _TEM_DADOS, reason="defina CITACOES_DADOS com os dados do desafio"
)


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory) -> Path:
    from citacoes.catalogo.construir import construir_catalogo_de_arquivo, salvar

    pasta = tmp_path_factory.mktemp("artifacts")
    salvar(
        construir_catalogo_de_arquivo(DADOS / "desafio1_bracis.db"),
        pasta / "catalogo_canonico.json",
    )
    return pasta


def _rodar(saida: Path, artifacts: Path, *extra: str) -> None:
    from citacoes.rodar import main

    argumentos = ["--txt", str(DADOS / "txt"), "--saida", str(saida), "--oficiais", str(DADOS)]
    assert main([*argumentos, "--artifacts", str(artifacts), *extra]) == 0


@com_dados
def test_determinismo_submissao_byte_a_byte(tmp_path, artifacts):
    _rodar(tmp_path / "a", artifacts)
    _rodar(tmp_path / "b", artifacts)
    a = (tmp_path / "a" / "submission.csv").read_bytes()
    assert a == (tmp_path / "b" / "submission.csv").read_bytes()
    assert len(a.decode("utf-8").splitlines()) == 1 + len(list((DADOS / "txt").glob("*.txt")))


@com_dados
def test_e2e_com_avaliacao(tmp_path, artifacts, capsys):
    _rodar(tmp_path, artifacts, "--avaliar", "--gabarito", str(DADOS / "goldenset_offsets.csv"))
    scores = json.loads((tmp_path / "scores.json").read_text(encoding="utf-8"))
    with capsys.disabled():
        print(f"\n[e2e] final={scores['final']:.4f} niveis={scores['niveis']}")
    assert set(scores["niveis"]) == {"1", "2"}
    assert all(0.0 <= n["tau"] <= 1.0 for n in scores["niveis"].values())
