# nos/

Um arquivo por nó determinístico: `ler_documento`, `extrair_spans`,
`normalizar`, `buscar_no_catalogo`, `decidir`, `calibrar`,
`reunir_e_formatar`.

Cada nó é uma função pura: recebe o estado (e o `runtime` quando precisa do
contexto) e devolve só os campos que alterou. Assim ele é testável sem
montar o grafo.
