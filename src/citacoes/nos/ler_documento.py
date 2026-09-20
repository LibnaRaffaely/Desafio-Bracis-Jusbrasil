from pathlib import Path
from citacoes.grafo.estados import EstadoDocumento

def ler_documento(caminho: str) -> dict:
    path = Path(caminho)
    return {
        "documento_id": path.stem,
        "texto": path.read_text(encoding="utf-8")
    }