# Avaliação

## A métrica em uma página

- Casamento de spans por IoU ≥ 0,5, um para um. Sem par: erro de recall
  (gabarito) ou falso positivo (predição).
- Macro-F1 das três classes. `real` só conta com o `id_canonico` certo.
- Penalidade: τ = fração das inventadas preditas como real;
  `s = macroF1 × (1 − 0,5 τ)`.
- Bônus: `score = s × (1 + 0,1 × (1 − Brier))`, só nos pares casados e só
  se houver confiança. Com confiança 1,0 em tudo, o bônus fica perto de
  10% × acurácia, então sempre enviem confiança.
- Final: `(1 × Nível1 + 2 × Nível2) / 3`. Perfeito com confiança 1,0 = 1,1.

Consequências práticas:

- inventada→real custa cerca de 3× o erro inverso;
- na dúvida só entre real e inventada, "incompleta" erra nos dois cenários;
- a fronteira do span pesa mais nas incompletas descritivas, que são longas.

## Três modos

| Modo | Entrada | Mede | Serve para |
|---|---|---|---|
| spans | .txt | P/R/F1 de span por nível | extração |
| resolucao | trechos do gabarito | classe + id + τ | subgrafo da citação, sem depender da extração |
| e2e | .txt | score completo, métrica local e oficial | todos |

Cada modo deve gerar um `erros.csv` com uma linha por citação e uma
categoria: `span_perdido`, `falso_positivo`, `classe_trocada`, `id_errado`,
`erro_tau`, `acerto`. Esse arquivo é o quadro de erros do trio.

## Sanidade da métrica

1. Converter o gabarito em submissão com confiança 1,0 e passar no
   `kaggle_metric.py`: tem que dar 1,1.
2. Se houver métrica local, ela precisa bater com a oficial nesse caso e
   numa submissão com erros conhecidos. Pontos a confirmar no script oficial:
   algoritmo de casamento, como conta real com id errado, F1 de classe
   vazia, Brier com confiança parcial.

## Portão de regressão

- `baseline/scores.json` guarda o melhor resultado aceito (por nível).
- Antes de cada merge: nenhum nível pode cair e τ não pode subir.
- Melhorou: o novo `scores.json` vai junto no PR.

## Testes de hipótese (reunião de sexta, 18/09)

| Hipótese | Como testar | Decide |
|---|---|---|
| H1: são 65 incompletas | `make check-data`; separar as incompletas com e sem identificador | se ambiguidade (2+ candidatos) é caso comum |
| H2: existem quimeras | inventadas cujo número existe no catálogo | quais atributos viram conflito duro |
| H3: incompleta por template | consultar tribunal/ano/relator das incompletas descritivas e contar | se a regra é "sem número → incompleta" |
| H4: atributos confiáveis | reais do gabarito cujo registro diverge em UF, classe, ano | nenhum atributo com divergência aqui pode ser duro |

Resultados vão em `docs/decisoes.md`.
