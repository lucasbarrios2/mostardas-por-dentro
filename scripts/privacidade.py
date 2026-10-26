"""Regras de privacidade usadas por todos os coletores (ARQUITETURA.md, decisão 10).

Por que um módulo só: a mesma regra precisa valer em licitações, contratos, pagamentos e
empresas. Se cada coletor tivesse a sua, bastaria um esquecimento para um CPF vazar.

- Documento de pessoa física: só os seis dígitos do meio, como no Portal da Transparência federal.
- Nome com CPF dentro (comum em microempreendedor individual, "FULANO 12345678901"): o CPF é mascarado.
- Texto livre (objeto de licitação): só se mascara número precedido da palavra CPF, porque
  sequências de 11 dígitos ali costumam ser RENAVAM de veículo, que não é dado pessoal.
"""
import re

_CPF_SOLTO = re.compile(r"(?<![\d*])(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})(?![\d*])")
_CPF_ROTULADO = re.compile(r"(?i)\b(cpf\s*(?:n[º°o.]?\s*)?:?\s*)(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})(?!\d)")


def mascarar_documento(tipo, doc):
    """Formata CNPJ por inteiro e mascara CPF; devolve None quando não reconhece o documento."""
    d = "".join(ch for ch in (doc or "") if ch.isdigit())
    if tipo == "F" and 0 < len(d) <= 11:
        d = d.zfill(11)
        return f"***.{d[3:6]}.{d[6:9]}-**"
    if tipo == "J" and 0 < len(d) <= 14:
        d = d.zfill(14)
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return None


def mascarar_cpf_em_nome(nome):
    return _CPF_SOLTO.sub(lambda m: f"***.{m.group(2)}.{m.group(3)}-**", nome or "")


def mascarar_cpf_rotulado(texto):
    return _CPF_ROTULADO.sub(lambda m: f"{m.group(1)}***.{m.group(3)}.{m.group(4)}-**", texto or "")


def tem_cpf_exposto(texto):
    """Usado pelos testes: há sequência de CPF sem máscara num campo de nome?"""
    return bool(_CPF_SOLTO.search(texto or ""))
