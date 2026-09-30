"""Roda o pipeline de ponta a ponta e gera a submissão — docs/arquitetura.md
e docs/avaliacao.md. Só ligação: carrega catálogo/parâmetros/modelo, roda o
grafo em lote, grava um JSON 1.2 por documento, chama os scripts oficiais
(`json_to_submission.py`, `kaggle_metric.py`) e confere as invariantes de
docs/contratos.md antes de sair.

    python -m citacoes.rodar --txt data/txt --saida out/ \\
        [--avaliar] [--gabarito data/goldenset_offsets.csv]
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from types import ModuleType

import pandas as pd

from citacoes.catalogo.construir import carregar, construir_catalogo_de_arquivo, salvar
from citacoes.catalogo.esquema import CatalogoCanonico
from citacoes.grafo.estados import Contexto, EstadoCitacao
from citacoes.grafo.montagem import como_citacao, montar_grafo_documento, montar_subgrafo_citacao

NOME_CATALOGO = "catalogo_canonico.json"
NOME_TABELA_CONFIANCA = "tabela_confianca.json"
IOU_MAXIMO = 0.5


class InvarianteQuebrada(RuntimeError):
    pass


# ── carga ───────────────────────────────────────────────────────────────────


def carregar_catalogo(pasta_artifacts: Path, db: Path, construir: bool) -> CatalogoCanonico:
    """A construção é a etapa offline (docs/arquitetura.md); só acontece
    aqui se pedida explicitamente."""
    caminho = pasta_artifacts / NOME_CATALOGO
    if construir:
        catalogo = construir_catalogo_de_arquivo(db)
        pasta_artifacts.mkdir(parents=True, exist_ok=True)
        salvar(catalogo, caminho)
        return catalogo
    if not caminho.exists():
        sys.exit(
            f"catálogo não encontrado em {caminho}. Construa-o antes (etapa offline): "
            f"rode de novo com --construir-catalogo --db {db}"
        )
    catalogo = carregar(caminho)
    if any(r.hash_texto is None for r in catalogo.registros):
        print(
            f"AVISO: {caminho} não tem `hash_texto`; foi gerado antes da versão atual de "
            "catalogo/construir.py e pode estar desatualizado. Use --construir-catalogo.",
            file=sys.stderr,
        )
    return catalogo


def carregar_tabela_confianca(pasta_params: Path) -> dict | None:
    """Tabela do Módulo 5 (`nos/calibrar.py`). Sem ela a confiança sai `-`
    e a submissão perde o bônus de calibração inteiro."""
    caminho = pasta_params / NOME_TABELA_CONFIANCA
    if not caminho.exists():
        print(
            f"AVISO: {caminho} não existe; confiança vai como '-' e o bônus de Brier fica 0. "
            "Gere a tabela com scripts/ajustar_confianca.py (make calibrar).",
            file=sys.stderr,
        )
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


def carregar_modelo(args: argparse.Namespace) -> object | None:
    """Só importa `agentes/` com algum agente ligado. O único agente
    implementado é o juiz, cujo backend é `BackendTransformers`
    (agentes/juiz.py: greedy, seed fixa, pesos locais com revisão fixada)."""
    if not args.juiz:
        return None
    if args.modelo is None:
        sys.exit("--juiz exige --modelo (caminho local dos pesos ou id do HF com --revisao)")
    from citacoes.agentes.juiz import BackendTransformers

    return BackendTransformers(repositorio=args.modelo, revisao=args.revisao, seed=args.seed)


# ── execução ────────────────────────────────────────────────────────────────


def _usa_llm(contexto: Contexto) -> bool:
    return contexto.usar_extrator_llm or contexto.usar_parser_llm or contexto.usar_juiz


def _config_lote(contexto: Contexto) -> dict | None:
    # Com agente LLM ligado, concorrência 1 (docs/arquitetura.md, "Lote").
    return {"max_concurrency": 1} if _usa_llm(contexto) else None


def rodar_subgrafo_em_spans(
    spans: Sequence[EstadoCitacao], contexto: Contexto
) -> list[EstadoCitacao]:
    """Modo `resolucao` da avaliação (docs/avaliacao.md): spans prontos (por
    exemplo, do gabarito, com `origem="gabarito"`) entram direto no
    subgrafo da citação. Devolve na mesma ordem da entrada."""
    subgrafo = montar_subgrafo_citacao(usar_parser_llm=contexto.usar_parser_llm)
    resultados = subgrafo.batch(list(spans), _config_lote(contexto), context=contexto)
    return [como_citacao(r) for r in resultados]


def rodar_documentos(caminhos: Sequence[Path], contexto: Contexto) -> list[dict]:
    """Um resultado (estado final do grafo do documento) por caminho, na
    ordem dos caminhos."""
    grafo = montar_grafo_documento(
        usar_extrator_llm=contexto.usar_extrator_llm, usar_parser_llm=contexto.usar_parser_llm
    )
    entradas = [{"caminho": str(c)} for c in caminhos]
    return grafo.batch(entradas, _config_lote(contexto), context=contexto)


# ── saída ───────────────────────────────────────────────────────────────────


def gravar_jsons(resultados: Iterable[dict], pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    # JSON antigo de outro documento entraria na submissão.
    for antigo in pasta.glob("*.json"):
        antigo.unlink()
    for r in resultados:
        saida = r["saida"]
        destino = pasta / f"{saida['documento_id']}.json"
        destino.write_text(json.dumps(saida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def gerar_submissao(pasta_json: Path, destino: Path, script: Path) -> None:
    subprocess.run([sys.executable, str(script), str(pasta_json), str(destino)], check=True)


def gravar_rastro(resultados: Iterable[dict], destino: Path) -> None:
    with destino.open("w", encoding="utf-8") as f:
        for r in resultados:
            for c in sorted(r["citacoes"], key=lambda c: (c.inicio, c.fim)):
                linha = {
                    "documento_id": r["documento_id"],
                    "inicio": c.inicio,
                    "fim": c.fim,
                    "trecho": c.trecho,
                    "origem": c.origem,
                    "metodo_busca": c.metodo_busca,
                    "metodo_decisao": c.metodo_decisao,
                    "classificacao": c.classificacao,
                    "id_canonico": c.id_canonico,
                    "confianca": c.confianca,
                }
                f.write(json.dumps(linha, ensure_ascii=False) + "\n")


# ── invariantes (docs/contratos.md) ─────────────────────────────────────────


def _iou(a: dict, b: dict) -> float:
    intersecao = max(0, min(a["fim"], b["fim"]) - max(a["inicio"], b["inicio"]))
    uniao = max(a["fim"], b["fim"]) - min(a["inicio"], b["inicio"])
    return intersecao / uniao if uniao > 0 else 0.0


def validar(resultados: Sequence[dict], ids_esperados: Iterable[str], submissao: Path) -> None:
    erros: list[str] = []
    for r in resultados:
        doc, texto = r["saida"]["documento_id"], r["texto"]
        citacoes = r["saida"]["citacoes"]
        for c in citacoes:
            onde = f"{doc} [{c['inicio']}:{c['fim']}]"
            if not 0 <= c["inicio"] < c["fim"] or texto[c["inicio"] : c["fim"]] != c["trecho"]:
                erros.append(f"{onde}: offsets/trecho não batem com o texto")
            tem_id = (c.get("resolucao") or {}).get("id_canonico") is not None
            if (c["classificacao"] == "real") != tem_id:
                erros.append(f"{onde}: classificacao={c['classificacao']} com id={tem_id}")
            conf = c.get("confianca")
            if conf is not None and not 0.0 <= conf <= 1.0:
                erros.append(f"{onde}: confianca={conf} fora de [0, 1]")
        for i, a in enumerate(citacoes):
            for b in citacoes[i + 1 :]:
                if _iou(a, b) >= IOU_MAXIMO:
                    erros.append(
                        f"{doc}: spans [{a['inicio']}:{a['fim']}] e [{b['inicio']}:{b['fim']}] "
                        f"com IoU >= {IOU_MAXIMO}"
                    )

    with submissao.open(encoding="utf-8", newline="") as f:
        linhas = {row["documento_id"]: row["citacoes"] for row in csv.DictReader(f)}
    faltando = sorted(set(ids_esperados) - set(linhas))
    if faltando:
        erros.append(f"documentos ausentes da submissão: {faltando}")
    for r in resultados:
        doc = r["saida"]["documento_id"]
        if not r["saida"]["citacoes"] and linhas.get(doc) != "-":
            erros.append(f"{doc}: sem citação deveria sair como '-', saiu {linhas.get(doc)!r}")

    if erros:
        raise InvarianteQuebrada("\n".join(["invariantes quebradas:", *erros]))


# ── avaliação ───────────────────────────────────────────────────────────────


def _importar_script(caminho: Path, nome: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(nome, caminho)
    if spec is None or spec.loader is None:
        raise ImportError(f"não consegui importar {caminho}")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def solucao_do_gabarito(gabarito: Path) -> pd.DataFrame:
    """`goldenset_offsets.csv` (uma linha por citação) -> formato `solution.csv` do
    `kaggle_metric.py` (uma linha por documento: `inicio,fim,classe,doc_ids`)."""
    gold = pd.read_csv(gabarito, dtype=str, keep_default_na=False)
    gold = gold.assign(_inicio=gold["inicio"].astype(int)).sort_values(["documento_id", "_inicio"])
    linhas = []
    for (documento_id, nivel), grupo in gold.groupby(["documento_id", "nivel"], sort=True):
        citacoes = "|".join(
            f"{r.inicio},{r.fim},{r.classificacao},{r.id_canonico or '-'}"
            for r in grupo.itertuples()
        )
        linhas.append({"documento_id": documento_id, "nivel": int(nivel), "citacoes": citacoes})
    return pd.DataFrame(linhas)


def avaliar(
    submissao: Path, gabarito: Path, script_metrica: Path, baseline: Path, destino: Path
) -> dict:
    metrica = _importar_script(script_metrica, "kaggle_metric")
    solucao = solucao_do_gabarito(gabarito)
    sub = pd.read_csv(submissao, dtype=str, keep_default_na=False)
    detalhes = metrica.avaliar(solucao, sub, row_id="documento_id")

    scores = {
        "final": detalhes["score_final"],
        "niveis": {
            str(n): {
                "score": r["score"],
                "macro_f1": r["macro_f1"],
                "tau": r["tau"],
                "bonus": r["b"],
                "f1_por_classe": r["f1_por_classe"],
            }
            for n, r in detalhes["niveis"].items()
        },
    }
    for n, r in scores["niveis"].items():
        f1s = ", ".join(f"{c}={v:.4f}" for c, v in r["f1_por_classe"].items())
        print(
            f"nível {n}: score={r['score']:.4f}  macroF1={r['macro_f1']:.4f}  "
            f"τ={r['tau']:.4f}  bônus={r['bonus']:.4f}  ({f1s})"
        )
    print(f"final: {scores['final']:.4f}")
    destino.write_text(json.dumps(scores, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "erros.csv: src/citacoes/avaliacao/ ainda não tem gerador (docs/avaliacao.md); pulado.",
        file=sys.stderr,
    )
    _comparar_baseline(scores, baseline)
    return scores


def _comparar_baseline(scores: dict, baseline: Path) -> None:
    """Portão de regressão (docs/avaliacao.md): só avisa."""
    if not baseline.exists():
        print(f"sem baseline em {baseline}; nada a comparar.", file=sys.stderr)
        return
    base = json.loads(baseline.read_text(encoding="utf-8"))
    for n, r in scores["niveis"].items():
        b = base.get("niveis", {}).get(n)
        if b is None:
            continue
        if r["score"] < b["score"]:
            print(f"AVISO: nível {n} caiu: {b['score']:.4f} -> {r['score']:.4f}", file=sys.stderr)
        if r["tau"] > b["tau"]:
            print(f"AVISO: τ do nível {n} subiu: {b['tau']:.4f} -> {r['tau']:.4f}", file=sys.stderr)


# ── CLI ─────────────────────────────────────────────────────────────────────


def _argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m citacoes.rodar",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--txt", type=Path, default=None, help="pasta com os .txt (padrão: data/txt)")
    p.add_argument("--saida", type=Path, default=Path("out"), help="pasta de saída")
    p.add_argument("--artifacts", type=Path, default=Path("artifacts"), help="catálogo pronto")
    p.add_argument("--params", type=Path, default=Path("params"), help="tabela de confiança")
    p.add_argument(
        "--oficiais",
        type=Path,
        default=Path("oficiais"),
        help="pasta com json_to_submission.py e kaggle_metric.py oficiais",
    )
    p.add_argument("--construir-catalogo", action="store_true", help="reconstrói artifacts/")
    p.add_argument("--db", type=Path, default=None, help="base SQLite (padrão: data/desafio1_bracis.db)")

    ## ---------- Comentei o uso dos modelos, para não correr o risco em um fluxo não testado
    #p.add_argument("--extrator-llm", action="store_true")
    #p.add_argument("--parser-llm", action="store_true")
    #p.add_argument("--juiz", action="store_true")
    #p.add_argument("--modelo", help="pesos do juiz: caminho local ou id do HF")
    #p.add_argument("--revisao", help="commit fixo dos pesos (obrigatório para id do HF)")
    #p.add_argument("--seed", type=int, default=42) 

    p.add_argument("--avaliar", action="store_true")
    p.add_argument("--gabarito", type=Path, default=None, help="gabarito para avaliação (padrão: data/goldenset_offsets.csv)")
    p.add_argument("--baseline", type=Path, default=Path("baseline/scores.json"))

    args = p.parse_args(argv)

    # fallback para data/ se não passado explicitamente
    if args.txt is None:
        args.txt = Path("data/txt")
    if args.db is None:
        args.db = Path("data/desafio1_bracis.db")
    if args.gabarito is None:
        args.gabarito = Path("data/goldenset_offsets.csv")

    if not args.txt.exists():
        sys.exit(
            f"Pasta de .txt não encontrada: {args.txt}\n"
            f"Passe o caminho com --txt ou coloque os dados em data/txt"
        )
    if not args.db.exists():
        sys.exit(
            f"Base não encontrada: {args.db}\n"
            f"Passe o caminho com --db ou coloque os dados em data/desafio1_bracis.db"
        )

    if args.avaliar and not args.gabarito.exists():
        sys.exit(
            f"Gabarito não encontrado: {args.gabarito}\n"
            f"Passe o caminho com --gabarito ou coloque o arquivo em data/goldenset_offsets.csv"
        )

    return args


def _saida_tolerante() -> None:
    """No Windows, com a saída redirecionada, o console usa cp1252 e o `τ`
    do relatório derrubava a execução depois da submissão já gravada."""
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    _saida_tolerante()
    args = _argumentos(argv)
    #for flag, ligada in (("--extrator-llm", args.extrator_llm), ("--parser-llm", args.parser_llm)):
    #   if ligada:
    #      sys.exit(f"{flag}: o agente não existe em citacoes/agentes/ ainda.")

    caminhos = sorted(args.txt.glob("*.txt"))
    if not caminhos:
        sys.exit(f"nenhum .txt em {args.txt}")

    contexto = Contexto(
        catalogo=carregar_catalogo(args.artifacts, args.db, args.construir_catalogo),
        tabela_confianca=carregar_tabela_confianca(args.params),
        modelo_llm=None,
        usar_extrator_llm=False,
        usar_parser_llm=False,
        usar_juiz=False,
    )
    resultados = rodar_documentos(caminhos, contexto)

    args.saida.mkdir(parents=True, exist_ok=True)
    pasta_json = args.saida / "json"
    submissao = args.saida / "submission.csv"
    gravar_jsons(resultados, pasta_json)
    gerar_submissao(pasta_json, submissao, args.oficiais / "json_to_submission.py")
    gravar_rastro(resultados, args.saida / "rastro.jsonl")
    validar(resultados, [c.stem for c in caminhos], submissao)
    n = sum(len(r["saida"]["citacoes"]) for r in resultados)
    print(f"{len(resultados)} documentos, {n} citações -> {submissao}")

    if args.avaliar:
        avaliar(
            submissao,
            args.gabarito,
            args.oficiais / "kaggle_metric.py",
            args.baseline,
            args.saida / "scores.json",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
