# dominio/

Conhecimento compartilhado entre extração e resolução:

- léxico: classes processuais, tribunais, diplomas, UFs e seus aliases;
- chave-esqueleto: canonicalização aplicada igualmente à citação e ao
  catálogo, desfazendo só o ruído declarado no edital;
- injetor de ruído do Nível 2, para testes de propriedade e dados sintéticos.

Propriedade a garantir em teste: esqueleto(ruído(x)) == esqueleto(x), e
trocar um dígito nunca leva à mesma chave.
