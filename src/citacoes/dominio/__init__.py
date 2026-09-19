from citacoes.dominio.campos import CamposIdentificador, extrair_campos
from citacoes.dominio.chave import (
    classes_processuais,
    corrigir_ocr_numerico,
    diploma_legal,
    extrair_digitos,
    extrair_uf,
    reagrupar,
    tribunal_citado,
)

__all__ = [
    "CamposIdentificador",
    "extrair_campos",
    "classes_processuais",
    "corrigir_ocr_numerico",
    "diploma_legal",
    "extrair_digitos",
    "extrair_uf",
    "reagrupar",
    "tribunal_citado",
]
