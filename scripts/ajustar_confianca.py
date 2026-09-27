"""Ajusta `params/tabela_confianca.json` a partir de uma rodada no dev set.

Uso (depois de `make rodar`):
    python scripts/ajustar_confianca.py
    python scripts/ajustar_confianca.py --rastro out/rastro.jsonl \\
        --gabarito data/goldenset_offsets.csv --destino params/tabela_confianca.json

Refaça o ajuste sempre que a extração, a busca ou a decisão mudarem: a
tabela descreve a taxa de acerto do pipeline atual, não de um anterior.
Detalhes em `src/citacoes/avaliacao/calibracao.py` e params/README.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from citacoes.avaliacao.calibracao import (
    ajustar_tabela,
    bonus,
    brier,
    brier_deixando_um_documento_fora,
    ler_gabarito,
    ler_rastro,
    rotular,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--rastro", type=Path, default=Path("out/rastro.jsonl"))
    p.add_argument("--gabarito", type=Path, default=Path("data/goldenset_offsets.csv"))
    p.add_argument("--destino", type=Path, default=Path("params/tabela_confianca.json"))
    p.add_argument("--alfa", type=float, default=1.0, help="acertos a priori por faixa")
    p.add_argument("--beta", type=float, default=1.0, help="erros a priori por faixa")
    args = p.parse_args(argv)

    for caminho in (args.rastro, args.gabarito):
        if not caminho.exists():
            sys.exit(f"não encontrado: {caminho}")

    rotulos = rotular(ler_rastro(args.rastro), ler_gabarito(args.gabarito))
    if not rotulos:
        sys.exit("nenhuma predição casou com o gabarito; confira os caminhos.")
    tabela = ajustar_tabela(rotulos, args.alfa, args.beta)

    args.destino.parent.mkdir(parents=True, exist_ok=True)
    args.destino.write_text(
        json.dumps(tabela, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"{len(rotulos)} pares casados -> {args.destino}")
    for chave, faixa in tabela["faixas"].items():
        print(
            f"  {chave:40s} {faixa['acertos']:>3}/{faixa['total']:<3} -> {faixa['confianca']:.4f}"
        )
    b_dentro = brier(rotulos, tabela)
    b_fora = brier_deixando_um_documento_fora(rotulos, args.alfa, args.beta)
    print(f"Brier no dev set:           {b_dentro:.4f}  (bônus {bonus(b_dentro):.4f})")
    print(f"Brier deixando um doc fora: {b_fora:.4f}  (bônus {bonus(b_fora):.4f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
