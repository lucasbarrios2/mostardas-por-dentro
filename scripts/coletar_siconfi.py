"""Coleta a Declaração de Contas Anuais (DCA) de Mostardas no SICONFI, do Tesouro Nacional.

Por que um coletor separado: gastos mudam por período (o Tesouro recebe a DCA uma vez por ano
e o RREO a cada bimestre), têm API pública e formato estável, então a coleta pode ser
automática e repetível. A cópia fiel vai para bruto/ com SHA-256; os números curados vão
para dados/financas/; a fonte é registrada em dados/fontes.json.

Uso: python3 scripts/coletar_siconfi.py 2025
"""
import datetime
import hashlib
import json
import pathlib
import sys
import urllib.parse
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
IBGE = "4312500"
API = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca"
COLUNAS = {"Despesas Empenhadas": "empenhado", "Despesas Liquidadas": "liquidado", "Despesas Pagas": "pago"}


def baixar(ano, anexo):
    url = API + "?" + urllib.parse.urlencode({"an_exercicio": ano, "no_anexo": anexo, "id_ente": IBGE})
    with urllib.request.urlopen(url, timeout=60) as r:
        corpo = r.read()
    destino = RAIZ / "bruto" / "siconfi" / f"dca-{ano}-{anexo.replace(' ', '-').lower()}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(corpo)
    itens = json.loads(corpo)["items"]
    if not itens:
        sys.exit(f"SICONFI não retornou dados para {anexo} de {ano}. Nada foi alterado.")
    return url, destino, hashlib.sha256(corpo).hexdigest(), itens


def registrar_fonte(fonte):
    caminho = RAIZ / "dados" / "fontes.json"
    fontes = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else []
    fontes = [f for f in fontes if f["id"] != fonte["id"]] + [fonte]
    caminho.write_text(json.dumps(sorted(fontes, key=lambda f: f["id"]), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(ano):
    hoje = datetime.date.today().isoformat()
    url_e, bruto_e, sha_e, itens_e = baixar(ano, "DCA-Anexo I-E")
    url_d, bruto_d, sha_d, itens_d = baixar(ano, "DCA-Anexo I-D")
    id_e, id_d = f"f-siconfi-dca-{ano}-ie", f"f-siconfi-dca-{ano}-id"

    funcoes, totais = {}, {}
    for x in itens_e:
        coluna = COLUNAS.get(x["coluna"])
        if not coluna:
            continue
        conta = x["conta"]
        if conta[:2].isdigit() and conta[2:5] == " - ":
            codigo, nome = conta.split(" - ", 1)
            funcoes.setdefault(codigo, {"funcao_codigo": codigo, "funcao": nome})[coluna] = round(x["valor"], 2)
        elif conta in ("Despesas Exceto Intraorçamentárias", "Despesas Intraorçamentárias"):
            chave = "total_sem_intra" if conta.startswith("Despesas Exceto") else "intraorcamentarias"
            totais.setdefault(chave, {})[coluna] = round(x["valor"], 2)

    # Contas por natureza que explicam a linha "Encargos especiais" (aposentadorias e dívida).
    natureza_alvo = {
        "3.1.90.01.00": "Aposentadorias do regime próprio dos servidores",
        "3.2.00.00.00": "Juros e encargos da dívida",
        "4.6.00.00.00": "Amortização da dívida",
    }
    natureza = []
    for x in itens_d:
        codigo = x["conta"].split(" - ", 1)[0]
        if x["coluna"] == "Despesas Liquidadas" and codigo in natureza_alvo:
            natureza.append({"conta": codigo, "descricao": natureza_alvo[codigo], "liquidado": round(x["valor"], 2)})

    serie = {
        "id": f"despesa-funcao-{ano}",
        "ente": {"ibge": IBGE, "nome": "Mostardas", "uf": "RS"},
        "exercicio": ano,
        "medida_principal": "liquidado",
        "fonte": id_e,
        "conferido_em": hoje,
        "linhas": sorted(funcoes.values(), key=lambda l: -l.get("liquidado", 0)),
        "total_sem_intra": totais.get("total_sem_intra"),
        "intraorcamentarias": totais.get("intraorcamentarias"),
        "natureza_destaques": {"fonte": id_d, "contas": natureza},
    }
    saida = RAIZ / "dados" / "financas" / f"despesa-funcao-{ano}.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(serie, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for fid, anexo, url, bruto, sha in ((id_e, "Anexo I-E (despesa por função)", url_e, bruto_e, sha_e),
                                        (id_d, "Anexo I-D (despesa por natureza)", url_d, bruto_d, sha_d)):
        registrar_fonte({
            "id": fid,
            "titulo": f"Declaração de Contas Anuais {ano} de Mostardas, {anexo}",
            "emissor": "Tesouro Nacional (SICONFI)",
            "tipo": "dados-oficiais",
            "url": url,
            "consultado_em": hoje,
            "copia": {"arquivo": str(bruto.relative_to(RAIZ)), "sha256": sha},
        })
    print(f"ok: {saida.relative_to(RAIZ)} com {len(funcoes)} funções; total liquidado sem intra = {totais.get('total_sem_intra', {}).get('liquidado')}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else datetime.date.today().year - 1)
