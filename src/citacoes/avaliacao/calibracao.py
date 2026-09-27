"""Ajuste da tabela de confiança (Módulo 5) a partir de uma rodada no dev set.

Entrada: o `rastro.jsonl` que `citacoes.rodar` grava (uma linha por
citação, com `metodo_decisao` e `metodo_busca`) e o gabarito
(`goldenset_offsets.csv`). Saída: o dicionário que vai para
`params/tabela_confianca.json` e que `nos/calibrar.py` consome.

O rótulo segue a métrica oficial (`kaggle_metric.py`): casamento 1-para-1
guloso por maior IoU, com IoU ≥ 0,5; o par conta como acerto (`y = 1`) se a
classe é a mesma e, para `real`, se o id está entre os aceitos. Predição
sem par não entra no Brier, então não entra no ajuste.

A taxa de cada faixa é suavizada com uma priori Beta(`alfa`, `beta`)
(Laplace com 1 e 1), para que uma faixa com poucos exemplos, todos certos,
não vire confiança 1,0 exata.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from citacoes.nos.calibrar import SEM_VALOR, chave_faixa, confianca_da_tabela

IOU_MINIMO = 0.5
VERSAO_TABELA = 1


@dataclass(frozen=True)
class Rotulo:
    documento_id: str
    metodo_decisao: str | None
    metodo_busca: str | None
    acerto: int


# ── leitura ─────────────────────────────────────────────────────────────────


def ler_rastro(caminho: Path) -> dict[str, list[dict]]:
    por_doc: dict[str, list[dict]] = defaultdict(list)
    with caminho.open(encoding="utf-8") as f:
        for linha in f:
            if linha.strip():
                c = json.loads(linha)
                por_doc[c["documento_id"]].append(c)
    return dict(por_doc)


def ler_gabarito(caminho: Path) -> dict[str, list[dict]]:
    # utf-8-sig: o gabarito do Kaggle vem com BOM no cabeçalho.
    por_doc: dict[str, list[dict]] = defaultdict(list)
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            por_doc[r["documento_id"]].append(
                {
                    "inicio": int(r["inicio"]),
                    "fim": int(r["fim"]),
                    "classificacao": r["classificacao"],
                    "ids": {i for i in (r.get("id_canonico") or "").split(":") if i},
                }
            )
    return dict(por_doc)


# ── casamento e rótulo ──────────────────────────────────────────────────────


def _iou(a: Mapping, b: Mapping) -> float:
    inter = max(0, min(a["fim"], b["fim"]) - max(a["inicio"], b["inicio"]))
    if inter == 0:
        return 0.0
    return inter / ((a["fim"] - a["inicio"]) + (b["fim"] - b["inicio"]) - inter)


def casar(golds: Sequence[Mapping], preds: Sequence[Mapping]) -> list[tuple[int, int]]:
    """Pares (índice do gold, índice da predição), mesma regra da métrica."""
    candidatos = sorted(
        (-v, gi, pi)
        for gi, g in enumerate(golds)
        for pi, p in enumerate(preds)
        if (v := _iou(g, p)) >= IOU_MINIMO
    )
    usados_g: set[int] = set()
    usados_p: set[int] = set()
    pares = []
    for _, gi, pi in candidatos:
        if gi in usados_g or pi in usados_p:
            continue
        usados_g.add(gi)
        usados_p.add(pi)
        pares.append((gi, pi))
    return pares


def _acertou(gold: Mapping, pred: Mapping) -> int:
    if gold["classificacao"] != pred["classificacao"]:
        return 0
    if pred["classificacao"] != "real":
        return 1
    return int(str(pred.get("id_canonico")) in gold["ids"])


def rotular(
    rastro: Mapping[str, Sequence[Mapping]], gabarito: Mapping[str, Sequence[Mapping]]
) -> list[Rotulo]:
    """Um rótulo por predição casada. Documentos sem gabarito são ignorados."""
    rotulos = []
    for doc in sorted(rastro):
        golds = gabarito.get(doc)
        if not golds:
            continue
        preds = rastro[doc]
        for gi, pi in casar(golds, preds):
            p = preds[pi]
            rotulos.append(
                Rotulo(doc, p.get("metodo_decisao"), p.get("metodo_busca"), _acertou(golds[gi], p))
            )
    return rotulos


# ── ajuste ──────────────────────────────────────────────────────────────────


def _faixa(acertos: int, total: int, alfa: float, beta: float) -> dict:
    return {
        "confianca": round((acertos + alfa) / (total + alfa + beta), 4),
        "acertos": acertos,
        "total": total,
    }


def ajustar_tabela(rotulos: Iterable[Rotulo], alfa: float = 1.0, beta: float = 1.0) -> dict:
    finas: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    grossas: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    geral = [0, 0]
    for r in rotulos:
        for contador in (
            finas[chave_faixa(r.metodo_decisao, r.metodo_busca)],
            grossas[r.metodo_decisao or SEM_VALOR],
            geral,
        ):
            contador[0] += r.acerto
            contador[1] += 1
    return {
        "versao": VERSAO_TABELA,
        "chave": "metodo_decisao|metodo_busca",
        "priori": {"alfa": alfa, "beta": beta},
        "faixas": {k: _faixa(a, n, alfa, beta) for k, (a, n) in sorted(finas.items())},
        "por_metodo_decisao": {
            k: _faixa(a, n, alfa, beta) for k, (a, n) in sorted(grossas.items())
        },
        "padrao": _faixa(geral[0], geral[1], alfa, beta)["confianca"],
    }


# ── diagnóstico ─────────────────────────────────────────────────────────────


def brier(rotulos: Sequence[Rotulo], tabela: Mapping) -> float:
    if not rotulos:
        return 0.0
    termos = [
        ((confianca_da_tabela(tabela, r.metodo_decisao, r.metodo_busca) or 0.0) - r.acerto) ** 2
        for r in rotulos
    ]
    return sum(termos) / len(termos)


def brier_deixando_um_documento_fora(
    rotulos: Sequence[Rotulo], alfa: float = 1.0, beta: float = 1.0
) -> float:
    """Estimativa honesta: cada documento é pontuado por uma tabela ajustada
    sem ele. O Brier no próprio dev set é otimista."""
    if not rotulos:
        return 0.0
    docs = sorted({r.documento_id for r in rotulos})
    termos = []
    for doc in docs:
        tabela = ajustar_tabela([r for r in rotulos if r.documento_id != doc], alfa, beta)
        for r in rotulos:
            if r.documento_id == doc:
                c = confianca_da_tabela(tabela, r.metodo_decisao, r.metodo_busca) or 0.0
                termos.append((c - r.acerto) ** 2)
    return sum(termos) / len(termos)


def bonus(valor_brier: float) -> float:
    """Bônus multiplicativo da métrica oficial (teto 0,10)."""
    return max(0.0, min(0.10, 0.10 * (1.0 - valor_brier)))
