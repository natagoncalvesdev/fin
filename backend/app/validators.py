"""Validadores reutilizáveis para campos de texto livre.

Nomes (de usuário, grupo, cofrinho) são exibidos no frontend em contextos HTML.
O frontend já escapa na renderização, mas rejeitar `<` e `>` aqui é a segunda
camada: impede que conteúdo com cara de tag seja gravado no banco.
"""

from __future__ import annotations


def nome_sem_html(valor: str | None) -> str | None:
    """Remove espaços nas pontas e recusa `<` ou `>`. Passa `None` adiante
    (campos opcionais em requisições de atualização parcial)."""
    if valor is None:
        return None
    valor = valor.strip()
    if "<" in valor or ">" in valor:
        raise ValueError("O nome não pode conter os caracteres < ou >.")
    return valor
