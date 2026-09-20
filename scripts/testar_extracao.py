from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from citacoes.dominio.cabecalho import extrair_cabecalho
from citacoes.grafo.estados import EstadoCitacao, EstadoDocumento
from citacoes.nos.extrair_spans import (
    _deduplicar,
    _e_distrator,
    _extrair_heuristica,
    _extrair_regex,
    _filtrar_curtos,
)

# ── Caminhos ────────────────────────────────────────────────────────────────

DATA_DIR = Path("data")
TXT_DIR = DATA_DIR / "txt"
GOLDENSET = DATA_DIR / "goldenset_offsets.csv"
OUTPUT = Path("resultados_extracao.csv")


# ── IoU ─────────────────────────────────────────────────────────────────────

def _iou(inicio_a: int, fim_a: int, inicio_b: int, fim_b: int) -> float:
    overlap = max(0, min(fim_a, fim_b) - max(inicio_a, inicio_b))
    union = max(fim_a, fim_b) - min(inicio_a, inicio_b)
    return overlap / union if union > 0 else 0.0


# ── Extração sem grafo ───────────────────────────────────────────────────────

def extrair_documento(texto: str) -> list[EstadoCitacao]:
    cabecalho_fim = len(extrair_cabecalho(texto))
    spans = _extrair_regex(texto) + _extrair_heuristica(texto)
    spans = _filtrar_curtos(spans)
    spans = [s for s in spans if not _e_distrator(s, cabecalho_fim)]
    return _deduplicar(spans)

# ── Resultado por citação ────────────────────────────────────────────────────

@dataclass
class ResultadoCitacao:
    documento_id: str
    citacao_id: str
    nivel: int
    inicio_gold: int
    fim_gold: int
    trecho_gold: str
    tipo_gold: str
    classificacao_gold: str
    status: str          # acerto, span_perdido, falso_positivo
    inicio_pred: int | None
    fim_pred: int | None
    trecho_pred: str | None
    origem_pred: str | None
    iou: float | None


def main() -> None:
    goldenset = pd.read_csv(GOLDENSET)

    resultados: list[ResultadoCitacao] = []
    spans_por_doc: dict[str, list[EstadoCitacao]] = {}

    #extrai todos os documentos uma vez
    for txt_path in sorted(TXT_DIR.glob("*.txt")):
        texto = txt_path.read_text(encoding="utf-8")
        spans_por_doc[txt_path.stem] = extrair_documento(texto)

    #cruza com goldenset
    for _, row in goldenset.iterrows():
        doc_id = row["documento_id"]
        spans = spans_por_doc.get(doc_id, [])

        melhor_iou = 0.0
        melhor_span = None
        for span in spans:
            iou = _iou(span.inicio, span.fim, row["inicio"], row["fim"])
            if iou > melhor_iou:
                melhor_iou = iou
                melhor_span = span

        if melhor_iou >= 0.5:
            status = "acerto"
        else:
            status = "span_perdido"
            melhor_span = None
            melhor_iou = None

        resultados.append(ResultadoCitacao(
            documento_id=doc_id,
            citacao_id=row["citacao_id"],
            nivel=row["nivel"],
            inicio_gold=row["inicio"],
            fim_gold=row["fim"],
            trecho_gold=row["trecho"],
            tipo_gold=row["tipo"],
            classificacao_gold=row["classificacao"],
            status=status,
            inicio_pred=melhor_span.inicio if melhor_span else None,
            fim_pred=melhor_span.fim if melhor_span else None,
            trecho_pred=melhor_span.trecho if melhor_span else None,
            origem_pred=melhor_span.origem if melhor_span else None,
            iou=melhor_iou,
        ))

    #falsos positivos: spans sem par no goldenset
    for doc_id, spans in spans_por_doc.items():
        gold_doc = goldenset[goldenset["documento_id"] == doc_id]
        for span in spans:
            tem_par = any(
                _iou(span.inicio, span.fim, r["inicio"], r["fim"]) >= 0.5
                for _, r in gold_doc.iterrows()
            )
            if not tem_par:
                resultados.append(ResultadoCitacao(
                    documento_id=doc_id,
                    citacao_id=None,
                    nivel=None,
                    inicio_gold=None,
                    fim_gold=None,
                    trecho_gold=None,
                    tipo_gold=None,
                    classificacao_gold=None,
                    status="falso_positivo",
                    inicio_pred=span.inicio,
                    fim_pred=span.fim,
                    trecho_pred=span.trecho,
                    origem_pred=span.origem,
                    iou=None,
                ))

    #salva resultado
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "documento_id", "citacao_id", "nivel",
            "inicio_gold", "fim_gold", "trecho_gold",
            "tipo_gold", "classificacao_gold",
            "status", "inicio_pred", "fim_pred",
            "trecho_pred", "origem_pred", "iou"
        ])
        for r in resultados:
            writer.writerow([
                r.documento_id, r.citacao_id, r.nivel,
                r.inicio_gold, r.fim_gold, r.trecho_gold,
                r.tipo_gold, r.classificacao_gold,
                r.status, r.inicio_pred, r.fim_pred,
                r.trecho_pred, r.origem_pred, r.iou
            ])

    #resumo no terminal
    total = len([r for r in resultados if r.status != "falso_positivo"])
    acertos = len([r for r in resultados if r.status == "acerto"])
    perdidos = len([r for r in resultados if r.status == "span_perdido"])
    fps = len([r for r in resultados if r.status == "falso_positivo"])

    print(f"\nTotal goldenset : {total}")
    print(f"Acertos         : {acertos} ({acertos/total:.1%})")
    print(f"Perdidos        : {perdidos} ({perdidos/total:.1%})")
    print(f"Falsos positivos: {fps}")

    n1 = [r for r in resultados if r.nivel == 1 and r.status != "falso_positivo"]
    n2 = [r for r in resultados if r.nivel == 2 and r.status != "falso_positivo"]
    print(f"\nNível 1: {sum(1 for r in n1 if r.status=='acerto')}/{len(n1)}")
    print(f"Nível 2: {sum(1 for r in n2 if r.status=='acerto')}/{len(n2)}")
    print(f"\nResultado salvo em {OUTPUT}")


if __name__ == "__main__":
    main()