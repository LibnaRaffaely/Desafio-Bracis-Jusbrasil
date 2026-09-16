"""Checagem dos dados da competição. Só usa a biblioteca padrão.

Uso:
    python scripts/check_data.py            # usa ./data
    python scripts/check_data.py caminho/   # outra pasta

Sai com código 1 se faltar algo essencial ou se os offsets do gabarito não
baterem com a leitura dos .txt.
"""

from __future__ import annotations

import csv
import sqlite3
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ESPERADO = {
    "documentos": 26,
    "citacoes": 225,
    "registros_base": 1016,
    "nivel_classe": {
        1: {"real": 52, "inventada": 32, "incompleta": 32},
        2: {"real": 44, "inventada": 32, "incompleta": 33},
    },
}


def ler_texto(caminho: Path) -> str:
    # newline="" preserva \r\n: sem isso os offsets deslocam
    with open(caminho, encoding="utf-8", newline="") as f:
        return f.read()


def desescapar(trecho: str) -> str:
    return trecho.replace("\\r", "\r").replace("\\n", "\n").replace("\\t", "\t")


def secao(titulo: str) -> None:
    print(f"\n== {titulo} ==")


def main(pasta: Path) -> int:
    criticos: list[str] = []
    txt_dir = pasta / "txt"
    db = pasta / "desafio1_bracis.db"
    gold_csv = pasta / "goldenset.csv"
    sample = pasta / "sample_submission.csv"

    secao("Arquivos")
    for arq in (
        txt_dir,
        db,
        gold_csv,
        sample,
        pasta / "kaggle_metric.py",
        pasta / "json_to_submission.py",
    ):
        print(f"[{'ok' if arq.exists() else 'FALTA'}] {arq}")
    if not txt_dir.exists() or not db.exists():
        print("\nCRÍTICO: faltam txt/ ou a base.")
        return 1

    secao("Documentos")
    textos = {p.stem: ler_texto(p) for p in sorted(txt_dir.glob("*.txt"))}
    print(f"{len(textos)} .txt (esperado {ESPERADO['documentos']})")
    crlf = [d for d, t in textos.items() if "\r\n" in t]
    bom = [d for d, t in textos.items() if t.startswith("\ufeff")]
    nfc = [d for d, t in textos.items() if unicodedata.normalize("NFC", t) != t]
    print(f"com CRLF: {len(crlf)} | com BOM: {len(bom)} | fora de NFC: {len(nfc)}")
    if crlf or bom or nfc:
        print("  atenção: qualquer normalização do texto antes de medir offsets quebra os spans")
    tamanhos = sorted(len(t) for t in textos.values())
    if tamanhos:
        print(
            f"tamanho: min {tamanhos[0]}, mediana {tamanhos[len(tamanhos) // 2]}, max {tamanhos[-1]}"
        )

    if gold_csv.exists():
        secao("Gabarito")
        with open(gold_csv, encoding="utf-8", newline="") as f:
            gold = list(csv.DictReader(f))
        print(f"{len(gold)} citações (esperado {ESPERADO['citacoes']})")
        cont = Counter((int(r["nivel"]), r["classificacao"]) for r in gold)
        for nivel, esperado in ESPERADO["nivel_classe"].items():
            achado = {c: cont.get((nivel, c), 0) for c in esperado}
            marca = "ok" if achado == esperado else "DIFERENTE do edital"
            print(f"nível {nivel}: {achado}  [{marca}]")

        ruins = []
        for r in gold:
            texto = textos.get(r["documento_id"])
            fatia = None if texto is None else texto[int(r["inicio"]) : int(r["fim"])]
            if fatia != desescapar(r["trecho"]):
                ruins.append(r)
        print(f"trechos que não batem com texto[inicio:fim]: {len(ruins)}")
        for r in ruins[:5]:
            print(f"  {r['documento_id']} {r['citacao_id']}: {r['trecho']!r}")
        if ruins:
            criticos.append("offsets do gabarito não batem")

        reais_sem_id = sum(
            1 for r in gold if r["classificacao"] == "real" and not r["id_canonico"].strip()
        )
        outros_com_id = sum(
            1 for r in gold if r["classificacao"] != "real" and r["id_canonico"].strip()
        )
        print(f"reais sem id_canonico: {reais_sem_id} | não-reais com id: {outros_com_id}")
        print(f"por tipo: {dict(Counter(r['tipo'] for r in gold))}")
        docs_sem_citacao = sorted(set(textos) - {r["documento_id"] for r in gold})
        print(f"documentos sem citação no gabarito: {docs_sem_citacao or 'nenhum'}")
        ids_gold = {r["id_canonico"].strip() for r in gold if r["id_canonico"].strip()}
    else:
        ids_gold = set()

    secao("Base canônica")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        tabelas = [
            r[0]
            for r in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
        ]
        print(f"tabelas: {tabelas}")
        total, distintos = con.execute(
            "SELECT COUNT(*), COUNT(DISTINCT id) FROM documentos"
        ).fetchone()
        print(
            f"registros: {total} (esperado {ESPERADO['registros_base']}) | ids distintos: {distintos}"
        )
        print(
            f"por natureza: {dict(con.execute('SELECT natureza, COUNT(*) FROM documentos GROUP BY natureza'))}"
        )
        print(
            f"por tribunal: {dict(con.execute('SELECT tribunal, COUNT(*) FROM documentos GROUP BY tribunal'))}"
        )
        if ids_gold:
            ids_base = {str(r[0]) for r in con.execute("SELECT id FROM documentos")}
            docids_base = {r[0] for r in con.execute("SELECT documento_id FROM documentos")}
            fora = ids_gold - ids_base
            print(f"id_canonico do gabarito ausentes na coluna id: {len(fora)}")
            if fora & docids_base:
                print("  atenção: há id_canonico que parece documento_id (confusão clássica)")
            if fora:
                criticos.append("gabarito referencia ids fora da base")
        print("amostra de cabeçalhos (primeiros 120 caracteres):")
        for nat in ("acordao", "sumula", "dispositivo"):
            linha = con.execute(
                "SELECT id, substr(texto, 1, 120) FROM documentos WHERE natureza = ? LIMIT 1",
                (nat,),
            ).fetchone()
            if linha:
                print(f"  [{nat}] {linha[0]}: {linha[1]!r}")
    finally:
        con.close()

    if sample.exists():
        secao("sample_submission")
        with open(sample, encoding="utf-8", newline="") as f:
            ids = [r["documento_id"] for r in csv.DictReader(f)]
        diff = set(ids) ^ set(textos)
        print("ids batem com os .txt" if not diff else f"diferença: {sorted(diff)}")
        with open(sample, "rb") as f:
            quebra = "CRLF" if b"\r\n" in f.read() else "LF"
        print(f"quebra de linha do arquivo: {quebra}")

    secao("Resultado")
    if criticos:
        for c in criticos:
            print(f"CRÍTICO: {c}")
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")))
