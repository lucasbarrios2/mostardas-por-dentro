"""Confere se cada fonte foi coletada dentro do prazo. É o alarme da automação.

Por que um alarme por frescor, e não por falha de coleta: uma oscilação de uma noite não deve
pintar a automação de vermelho, mas uma fonte parada por dias precisa. De 27/10 a 12/11/2026,
a coleta inteira caiu por causa de uma fonte só. Agora cada coletor roda isolado, o site
continua publicando com o último dado bom, e este script falha quando uma fonte passa do prazo.

Uso: python3 scripts/conferir_frescor.py [--hoje AAAA-MM-DD]
"""
import argparse
import datetime as dt
import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# (nome, arquivo relativo à raiz, campo de data, prazo em dias, obrigatória)
FONTES = [
    ("Licitações e contratos (LicitaCon, TCE-RS)", "dados/compras/fonte.json", "consultado_em", 3, True),
    ("Empresas e sócios (Receita Federal)", "dados/empresas/fonte.json", "consultado_em", 7, True),
    ("Pagamentos do ano anterior (TCE-RS)", "bruto/tce-rs/empenhos/manifesto-{ano_anterior}.json", "verificado_em", 7, True),
    # O arquivo do ano novo só aparece no TCE-RS alguns meses depois de janeiro.
    ("Pagamentos do ano atual (TCE-RS)", "bruto/tce-rs/empenhos/manifesto-{ano}.json", "verificado_em", 7, False),
]


def avaliar(hoje, raiz=RAIZ):
    """Devolve uma lista de (nome, idade em dias ou None, prazo, nível: ok | aviso | erro)."""
    linhas = []
    for nome, padrao, campo, prazo, obrigatoria in FONTES:
        caminho = raiz / padrao.format(ano=hoje.year, ano_anterior=hoje.year - 1)
        data = json.loads(caminho.read_text(encoding="utf-8")).get(campo) if caminho.exists() else None
        if not data:
            linhas.append((nome, None, prazo, "erro" if obrigatoria else "aviso"))
            continue
        idade = (hoje - dt.date.fromisoformat(data[:10])).days
        linhas.append((nome, idade, prazo, "ok" if idade <= prazo else "erro"))
    return linhas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hoje", default=dt.date.today().isoformat())
    hoje = dt.date.fromisoformat(ap.parse_args().hoje)
    linhas = avaliar(hoje)
    for nome, idade, prazo, nivel in linhas:
        quando = "nunca coletada" if idade is None else f"coletada há {idade} dia(s)"
        print(f"{nivel:5s} {nome}: {quando} (prazo: {prazo} dias)")
        if nivel != "ok":
            print(f"::{'error' if nivel == 'erro' else 'warning'}::{nome}: {quando}; o prazo é {prazo} dias.")
    sys.exit(1 if any(n == "erro" for *_, n in linhas) else 0)


if __name__ == "__main__":
    main()
