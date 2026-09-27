# Melhorias de score: de 0,8150 para 1,0998

Registro das mudanças feitas em 27/09/2026 sobre o código do último commit
(`da00f2e`, merge do PR #5), com a evidência de cada uma e o efeito medido no
dev set. As decisões de regra estão resumidas em [decisoes.md](decisoes.md),
nas entradas D2 a D7.

| | Arquivo | Final | Nível 1 | Nível 2 |
|---|---|---|---|---|
| Código do git | `baseline/scores1.json` | 0,8150 | 0,8451 | 0,7999 |
| Código ajustado | `baseline/scores.json` | 1,0998 | 1,0999 | 1,0998 |

O teto da métrica é 1,1: macro-F1 1,0 com bônus de calibração máximo. O
código ajustado chega a macro-F1 1,0 e τ = 0 nos dois níveis.

> **Leia antes de comparar.** Os dois arquivos não foram medidos com os mesmos
> dados. O `scores1.json` usa a versão anterior (`goldenset.csv`, 225
> citações, base de 1016 registros); o `scores.json` usa a versão atual
> (`goldenset_offsets.csv`, 192 citações, base de 1014 registros). A troca de
> dados sozinha explica 0,0157 da diferença; o resto vem do código. A tabela
> da próxima seção separa as duas coisas.

## Como o score evoluiu

Cada linha soma uma mudança à anterior. Da terceira linha em diante, tudo foi
medido com os dados atuais e o catálogo reconstruído a partir da base atual.

| # | Mudança | Final | Nível 1 | Nível 2 |
|---|---|---|---|---|
| 0 | Código do git, dados anteriores | 0,8150 | 0,8451 | 0,7999 |
| 1 | Código do git, gabarito novo, catálogo antigo | 0,8252 | 0,8623 | 0,8066 |
| 2 | Código do git, dados atuais, catálogo reconstruído | 0,8307 | 0,8789 | 0,8066 |
| 3 | Envio da confiança | 0,9089 | 0,9614 | 0,8826 |
| 4 | Número próprio dos acórdãos no catálogo | 0,9474 | 1,0103 | 0,9160 |
| 5 | Correção de OCR sem corromper siglas | 0,9657 | 1,0203 | 0,9384 |
| 6 | Extrator reescrito | 1,0248 | 1,0831 | 0,9956 |
| 7 | Normalização: 4 dígitos, súmula, G/g, novas classes | 1,0887 | 1,0985 | 1,0838 |
| 8 | Desempate pela cadeia de classes | 1,0986 | 1,0985 | 1,0986 |
| 9 | Proteção contra τ e diploma com ruído | 1,0986 | 1,0985 | 1,0986 |
| 10 | Tabela de confiança reajustada | 1,0998 | 1,0999 | 1,0998 |

As linhas 0 a 2 usam o mesmo código. A base nova trouxe o número das súmulas
do STF e do TST no texto, o que resolveu dois erros sem nenhuma mudança de
código. A linha 9 não muda o score do dev set: ela fecha um risco que só
apareceu com ruído sintético (ver [Robustez](#robustez)).

## As mudanças

### 3. Envio da confiança

**Problema.** A arquitetura previa um nó `calibrar`, mas ele nunca foi
ligado ao grafo. A confiança saía `-` no CSV e o bônus de calibração, que
vale até 10% do score de cada nível, era zero.

**Decisão.** O nó `calibrar` roda depois de `decidir` e busca a confiança
numa tabela por `metodo_decisao|metodo_busca`, com recuo para só
`metodo_decisao` e depois para um valor padrão. A tabela guarda a taxa de
acerto de cada grupo no dev set, suavizada por Laplace, porque é esse valor
que minimiza o Brier da métrica. A confiança nunca muda a classe nem o id.

**Evidência.** Medido deixando um documento de fora, o bônus fica em 0,093,
quase igual ao 0,094 medido no próprio dev set. Ou seja, a tabela não está
decorando o dev set.

**Onde.** `nos/calibrar.py`, `avaliacao/calibracao.py`,
`scripts/ajustar_confianca.py`, `params/tabela_confianca.json`, alvo
`make calibrar`.

### 4. Número próprio dos acórdãos no catálogo

**Problema.** O catálogo pegava a primeira cadeia de 5+ dígitos dos primeiros
1000 caracteres de cada registro. Isso falhava de quatro formas:

- **TST.** O número do processo só aparece depois do caractere 1000. Dos 198
  acórdãos, 80 ficavam sem número e cerca de 110 usavam o número de uma lei
  como chave (66 com a chave da Lei 13.015/2014).
- **TSE e STF.** Quando o cabeçalho citava uma súmula, o registro caía no
  ramo de súmula e perdia o número do processo.
- **STJ.** "SUSPENSÃO DE LIMINAR E DE SENTENÇA Nº 2.883" era indexada pelo
  número de registro entre parênteses.
- **STM e TSE.** Um espaço solto no CNJ ("Nº 7000380- 08.2023...") cortava a
  chave no primeiro grupo.

**Decisão.** No TST, o número vem da fórmula "Vistos, relatados e
discutidos estes autos de ... nº TST-<CNJ>", presente em 195 dos 198
acórdãos. Nos demais tribunais, vale o número do rótulo "Nº" se ele vier
antes de qualquer outro número; senão, a primeira cadeia válida. Uma cadeia
não é válida quando é data, número de registro, número de lei, OAB colada a
letras ou ano solto. Um CNJ solto no cabeçalho não conta, porque na
reclamação do STF ele é o número do processo de origem. Um CNJ entre
parênteses logo depois do número ("RECURSO ORDINÁRIO Nº 1.662
(47142-16.2008.6.00.0000)") vira número alternativo e entra no índice.
Acórdão nunca é tratado como súmula.

**Evidência.** Cinco citações reais do Nível 1 passaram a resolver, as de
TST e TSE. A sexta, do TST, dependia também da correção de OCR da linha 5. Comparamos as chaves antigas e novas registro a registro, por
tribunal, antes de aceitar a regra.

**Onde.** `catalogo/construir.py` (`numeros_proprios_acordao`, `indexar`),
`catalogo/esquema.py` (`numeros_alternativos`).

### 5. Correção de OCR sem corromper siglas

**Problema.** A correção letra→dígito tratava a cadeia inteira
"TST-ED-E-ED-RR-3400-05..." como número e trocava o S de "TST" por 5. A
citação ganhava um dígito a mais e não casava com o catálogo. O teste de
propriedade da chave-esqueleto também falhava num caso de borda.

**Decisão.**

- Dentro de uma cadeia, só é corrigido o campo que tem dígito ou que é feito
  só de letras confundíveis. "TST" tem "T" e fica intacto.
- Um token solto só de letras confundíveis ("OO", "l.") vira dígito quando
  o vizinho encosta num dígito. Em "ignorar o RR-1835", o "o" é artigo, não
  zero.
- Um vizinho separado por linha em branco não conta. O "I" que abre o
  parágrafo seguinte é algarismo romano.
- G e g passam a valer 6 e 9, como aparece no Nível 2 ("6G.838",
  "1.45g.779").

**Onde.** `dominio/chave.py`.

### 6. Extrator reescrito

**Problema.** As regex montavam os nomes de classe com espaço literal, então
"AgInt no Recurso\nEspecial" não casava. A regex do TST, sem distinção de
caixa, lia o fim de "ignorar" como a sigla "ar". Faltavam classes, prefixos
ordinais e classes do TSE unidas por hífen. As incompletas vinham de cinco
heurísticas que passavam do nome do relator e geravam falsos positivos.

**Decisão.**

- Espaço entre palavras com no máximo uma quebra de linha. Linha em branco
  nunca fica dentro de um span.
- Classes unidas por hífen ("AgR-REspe", "AgR-AI"), prefixos ordinais
  ("Terceiro AG.REG na Rcl"), abreviações com ponto opcional.
- Números com o ruído do Nível 2: espaço não separável, espaço solto, letra
  no lugar de dígito.
- UF só entre as siglas de estado válidas.
- Pontuação final aparada: o gabarito nunca termina um span em ".", "," ou
  espaço.
- Uma regra única para as incompletas: gatilho ou classe, ano, "relatoria
  de" ou "Rel. Min.", e o nome do relator, que termina na primeira palavra
  que não começa por maiúscula.
- Entre spans sobrepostos, fica o mais longo da camada mais confiável. Um
  span contido em outro é descartado.
- "Referência: autos nº ..." é o número dos autos do próprio documento e
  vira distrator.
- Súmula com "5úmula" e "Súm.", Tema de repercussão geral e "Código Penal
  Militar" completo.

**Evidência.** No Nível 1, as quatro citações reais não extraídas, a
incompleta perdida e os três falsos positivos foram resolvidos.

**Onde.** `nos/extrair_spans.py`, `dominio/lexico.py`.

### 7. Normalização

**Decisão.**

- O menor número buscável num span passa de 5 para 4 dígitos, exceto ano
  solto. O gabarito e a base têm classes com 4 dígitos (SLS 2.883, AR 2785).
- Súmula reconhecida também como "Súm." e "5úmula".
- Novas classes no léxico: REspe, AI, RMS, SLS, SS, AR, Rp, EREsp, e as
  variantes "AG.REG.", "AgR", "H.C.", "A.REsp", "Rec. Esp.".

**Onde.** `dominio/campos.py`, `dominio/lexico.py`.

### 8. Desempate pela cadeia de classes

**Problema.** "AgInt no REsp 1.597.443" tem dois registros com o mesmo
número: o AgInt e o "AgInt nos EREsp". O empate virava incompleta.

**Decisão.** Novo desempate 1c em `decidir`: se só um candidato tem a mesma
cadeia de classes da citação, ele vira real com `metodo_decisao =
desempate_classe`. Com zero ou dois iguais, o caso segue para o juiz, que
está desligado, e vira incompleta. O casamento de classes também passou a
separar palavras que o OCR colou ("nosEMBARGOS").

**Onde.** `nos/decidir.py`, `catalogo/esquema.py` (`Candidato.classes_compostas`),
`nos/buscar_no_catalogo.py`, `dominio/chave.py`.

### 9. Proteção contra τ

**Problema.** Com ruído sintético (ver [Robustez](#robustez)), 11 citações
inventadas viravam reais, o erro mais caro da métrica. Exemplo: "art. 172 da
Lei nº 9.504/1997", com ruído, casava com o art. 1º da LC 64/1990, porque o
diploma não era reconhecido e o artigo casava só pelo número.

**Decisão.**

- Artigo de lei só casa se o diploma for reconhecido e igual dos dois lados.
- Súmula só casa com súmula do mesmo tribunal quando os dois lados o têm.
- O nome do diploma tolera ruído de letra ("Constituição Fedcral"), por
  comparação aproximada com o `rapidfuzz` e similaridade mínima de 90.

**Evidência.** τ com ruído caiu de 11 para 0. A exigência de diploma, sozinha,
derrubava uma citação real do Nível 2 ("Constituição Fedcral"); a tolerância
a ruído no nome recuperou o caso.

**Onde.** `catalogo/esquema.py`, `dominio/chave.py`, `nos/extrair_spans.py`.

## Robustez

O dev set tem 26 documentos, e as regras foram desenhadas olhando para ele.
Para ter uma medida que não dependa disso, aplicamos o injetor de ruído do
próprio projeto (`dominio/ruido.py`) aos trechos do gabarito, com 10
sementes, e rodamos o subgrafo da citação sobre cada versão.

| Com ruído, 10 sementes | Antes da linha 9 | Código ajustado |
|---|---|---|
| Inventadas marcadas como reais (τ) | 11 | 0 |
| Reais perdidas, de 864 | 51 | 26 |

## Outras correções

Nenhuma destas muda o score, mas cada uma bloqueava a execução ou a leitura
do resultado:

- **Windows.** A rodada quebrava ao imprimir o τ com a saída redirecionada
  (console em cp1252). `rodar.py` agora troca o caractere em vez de falhar.
- **Suíte de testes.** Um teste importava o pacote por `src.citacoes` e
  impedia a coleta de toda a suíte.
- **Checagem de dados.** `check_data.py` quebrava com o BOM do gabarito novo
  e esperava os totais da versão anterior.
- **Lint.** Os avisos que já existiam foram corrigidos; `ruff check` e
  `ruff format --check` passam no projeto inteiro.
- **Testes novos.** Depois de corrigir o import, a suíte tinha 150 testes,
  com uma falha. Agora tem 197, todos passando, incluindo o de propriedade
  que falhava.

## O que não mudou

- **Agentes LLM desligados.** Nenhuma citação do dev set chega empatada ao
  Agente-Juiz, então não há como medir se ele ajuda.
- **Pasta `data/` intocada.** Todos os ajustes estão em código, léxico e
  parâmetros.
- **Contrato de saída.** Os campos do JSON e do CSV continuam os mesmos.
  `metodo_decisao` ganhou o valor `desempate_classe`, e o candidato ganhou a
  cadeia de classes do registro (ver [contratos.md](contratos.md)).

## Limites

- **O 1,0998 é otimista.** O conjunto final do Kaggle é cego, e o score lá
  deve ficar abaixo do dev set.
- **Onde ainda erra.** Pelo teste com ruído, cerca de 3% das reais se perdem
  quando há ruído, na maioria números de artigo ou de processo quebrados de
  formas que a normalização ainda não cobre. Formas de citação ausentes do
  dev set também não estão cobertas.
- **O desempate por classe foi visto uma vez só.** Por isso a tabela dá a
  ele confiança 0,67.

## Como reproduzir

Com os dados atuais em `data/`:

```bash
make rodar ARGS="--construir-catalogo"   # catálogo novo e rastro
make calibrar                            # params/tabela_confianca.json
make rodar ARGS="--avaliar"              # out/scores.json
```

No Windows, dentro do OneDrive, exporte antes `UV_LINK_MODE=copy` e
`PYTHONIOENCODING=utf-8`. Sem `make`, os comandos equivalentes estão no
[README](../README.md).
