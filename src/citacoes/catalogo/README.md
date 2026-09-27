# catalogo/

Construção offline do catálogo canônico a partir de `desafio1_bracis.db`
e carga para o contexto do grafo.

- Indexar só os identificadores **próprios** de cada registro, para que
  acórdãos que apenas citam outros não virem candidatos. Para acórdãos, a
  regra está em `numeros_proprios_acordao` (construir.py): no TST, a fórmula
  "discutidos estes autos de ... nº TST-<CNJ>"; nos demais, o rótulo "Nº" do
  cabeçalho ou a primeira cadeia válida. Um acórdão pode ter número
  alternativo (CNJ entre parênteses), indexado junto.
- Guardar, por registro: `id` (o valor de `id_canonico`), tribunal, ano,
  relator, natureza, classe, número, CNJ, UF, órgão; tupla para leis e
  súmulas.
- Gerar o relatório de colisões (chaves que apontam para 2+ registros).
- Saída em `artifacts/`, fora do git.
