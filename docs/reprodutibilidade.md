# Reprodutibilidade (bundle dos finalistas)

Envelope oficial: 1 GPU de 24 GB, ~8 vCPUs, 32 GB de RAM, sem chaves de API.

## Checklist

- [ ] Um comando reproduz a submissão do zero: construir o catálogo e rodar
      o grafo em todos os .txt.
- [ ] `uv.lock` versionado; instalação com `uv sync --frozen`.
- [ ] `params/` versionado (nada é reajustado no conjunto final, que é cego).
- [ ] Pesos do modelo (se houver) com link e revisão fixada no Hugging
      Face, baixados por script com conferência de hash.
- [ ] Agentes LLM com `temperature=0`, seed explícita, lote fixo.
- [ ] Execução sem rede, inclusive sem rastreamento em nuvem.
- [ ] Dockerfile testado numa máquina limpa com os limites do envelope:
      `docker run --network none --cpus 8 --memory 32g ...`
      (e `--gpus` se houver LLM).
- [ ] README com o comando exato, o modelo e o hardware usados.

## Docker

- Imagem base e versão do uv fixadas.
- Pesos como volume montado, não dentro da imagem.
- Sem LLM: imagem só CPU. Com LLM: variante CUDA com llama.cpp compilado
  em build de dois estágios; exige NVIDIA Container Toolkit na máquina.
- Plano B no README: instalação sem Docker.
