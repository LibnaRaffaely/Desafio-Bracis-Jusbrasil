# Contratos

Versão do contrato do trio adaptada ao grafo. Os tipos exatos ficam a
critério de quem implementar; o que não pode mudar sem acordo dos três são os
**nomes dos campos** e as **invariantes**.

## Contexto (compartilhado, somente leitura)

| Campo | Descrição |
|---|---|
| `catalogo` | catálogo canônico carregado de `artifacts/` |
| `tabela_confianca` | faixas de confiança carregadas de `params/` |
| `modelo_llm` | instância do modelo, ou nada se os agentes estiverem desligados |
| `usar_extrator_llm`, `usar_parser_llm`, `usar_juiz` | flags, padrão desligado |

## EstadoDocumento

| Campo | Descrição |
|---|---|
| `documento_id` | nome do .txt sem extensão |
| `texto` | conteúdo exato do arquivo |
| `spans` | spans candidatos após extração e filtro de distratores |
| `citacoes` | acumulado das citações classificadas (reducer de soma) |
| `saida` | JSON 1.2 do documento |

## Span candidato (saída da extração)

| Campo | Descrição |
|---|---|
| `inicio`, `fim` | offsets em codepoints no texto cru, fim exclusivo |
| `trecho` | cópia literal de `texto[inicio:fim]` |
| `tipo_bruto` | jurisprudencia, lei ou indefinido |
| `tem_identificador` | se há número, artigo ou súmula buscável |
| `origem` | regex, heurística, tagger, llm ou gabarito |

## EstadoCitacao

Tudo do span candidato, mais:

| Campo | Preenchido por | Descrição |
|---|---|---|
| `campos` | normalizar / agente_parser | chaves numéricas, classe, UF, tribunal, relator, ano, órgão, diploma, artigo, parágrafo, inciso, alínea, súmula, vinculante |
| `ocr_corrigido` | normalizar | se alguma confusão letra→dígito foi desfeita |
| `candidatos` | buscar_no_catalogo | id, tribunal, natureza, conflitos duros, divergências brandas |
| `metodo_busca` | buscar_no_catalogo | catalogo, lei_sumula, sem_busca |
| `escolha_juiz` | agente_juiz | id escolhido ou nada, e justificativa (só log) |
| `classificacao`, `id_canonico`, `tipo` | decidir | resultado |
| `metodo_decisao` | decidir | sem_identificador, cardinalidade_0, cardinalidade_1, cardinalidade_2mais, veto_quimera, juiz |
| `confianca` | calibrar | valor entre 0 e 1 |

## Invariantes

| Invariante | Onde garantir |
|---|---|
| `0 <= inicio < fim` e `trecho == texto[inicio:fim]` | extração |
| nenhum par de spans do mesmo documento com IoU ≥ 0,5 | extração |
| nenhum distrator (autos próprios, protocolo, OAB, fls., valor da causa) | extração |
| `tem_identificador` falso ⇒ sem busca e sem candidatos | normalizar / buscar |
| `classificacao == real` ⇔ `id_canonico` preenchido | decidir |
| `id_canonico` é a coluna `id`, nunca `documento_id` | catálogo |
| agentes LLM não definem classe nem confiança | agentes |
| `confianca` em [0, 1] | calibrar |
| todo documento aparece na submissão, mesmo sem citação (`-`) | saída |

## Saída (JSON 1.2)

Confirmar os campos exatos na aba Data do Kaggle. O que sabemos:

```json
{
  "documento_id": "gen_n1_004",
  "citacoes": [
    {
      "inicio": 1571,
      "fim": 1603,
      "trecho": "APL 7000136-79.2023.7.00.0000/RS",
      "tipo": "jurisprudencia",
      "classificacao": "real",
      "resolucao": {"id_canonico": 2161632985},
      "confianca": 0.94
    }
  ]
}
```

O `submission.csv` sai do `json_to_submission.py` oficial. Nenhum nó
escreve CSV.
