"""Coleta os empenhos, liquidações e pagamentos de Mostardas publicados pelo TCE-RS e resume em dados/pagamentos/.

Por que assim: o TCE-RS publica um arquivo único por ano com todos os municípios do RS
(centenas de MB a mais de 1 GB). O coletor só baixa de novo quando o arquivo mudou
(Last-Modified), lê em fluxo, guarda em bruto/ apenas as linhas de Mostardas e grava um
resumo pequeno para a página. O município envia esses dados ao Tribunal a cada dois meses,
então o resumo sempre informa até que data vai.

Privacidade (ARQUITETURA.md, decisão 10): pagamentos a pessoas físicas aparecem só somados
por tipo de despesa, sem nome nem CPF, para não expor quem recebe auxílio social.

Uso: python3 scripts/coletar_empenhos.py 2026 [--filtrado ARQUIVO.csv.gz]
"""
import argparse
import collections
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import pathlib
import re
import urllib.request
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from privacidade import mascarar_cpf_em_nome

RAIZ = pathlib.Path(__file__).resolve().parent.parent
BRUTO = RAIZ / "bruto" / "tce-rs" / "empenhos"
SAIDA = RAIZ / "dados" / "pagamentos"
URL = "https://dados.tce.rs.gov.br/dados/municipal/empenhos/{ano}.csv.zip"
ORGAOS = {"52400": "prefeitura", "52401": "camara"}
LETRAS_SEPARADAS = re.compile(r"\b(?:[A-ZÀ-Ú] ){2,}[A-ZÀ-Ú]\b")
# A folha não tem um credor de verdade: o sistema do município usa estes nomes soletrados.
FOLHA = {"FUNCIONARIOS": "Folha dos servidores ativos", "INATIVOS": "Folha dos aposentados", "PENSIONISTAS": "Folha dos pensionistas",
         "IPE": "Contribuição ao IPE", "INSS": "Contribuição ao INSS", "FGTS": "Depósitos de FGTS"}


def baixar_e_filtrar(ano):
    """Baixa o arquivo estadual em fluxo e grava só as linhas de Mostardas."""
    url = URL.format(ano=ano)
    destino = BRUTO / f"mostardas-{ano}.csv.gz"
    manifesto_p = BRUTO / f"manifesto-{ano}.json"
    anterior = json.loads(manifesto_p.read_text(encoding="utf-8")) if manifesto_p.exists() else {}
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        modificado = r.headers.get("Last-Modified")
    # O extrato com nomes de pessoas físicas não vai para o Git; o que fica versionado é o
    # manifesto. Se o arquivo estadual não mudou desde a última coleta, não há o que refazer.
    if anterior.get("last_modified") == modificado and (SAIDA / f"resumo-{ano}.json").exists():
        return None, anterior
    BRUTO.mkdir(parents=True, exist_ok=True)
    temp = BRUTO / f"{ano}.csv.zip.parcial"
    h = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=600) as r, open(temp, "wb") as f:
        while bloco := r.read(1 << 20):
            h.update(bloco)
            f.write(bloco)
    n = 0
    with zipfile.ZipFile(temp) as z, z.open(z.infolist()[0]) as bruto, gzip.open(destino, "wt", encoding="utf-8", newline="") as out:
        rd = csv.reader(io.TextIOWrapper(bruto, encoding="utf-8-sig", errors="replace", newline=""))
        wr = csv.writer(out)
        cab = next(rd)
        wr.writerow(cab)
        i = cab.index("cd_orgao")
        for row in rd:
            if row[i] in ORGAOS:
                wr.writerow(row)
                n += 1
    temp.unlink()
    manifesto = {"url": url, "last_modified": modificado, "sha256_arquivo_estadual": h.hexdigest(), "linhas_mostardas": n,
                 "arquivo": str(destino.relative_to(RAIZ)), "coletado_em": dt.date.today().isoformat()}
    manifesto_p.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destino, manifesto


def rotulo_credor(nome):
    """Junta nomes soletrados ('C E E E' vira 'CEEE') e separa o que é folha de pagamento."""
    limpo = mascarar_cpf_em_nome(" ".join(LETRAS_SEPARADAS.sub(lambda m: m.group(0).replace(" ", ""), nome.strip()).split()))
    if limpo in FOLHA:
        return FOLHA[limpo], True
    return limpo, False


def cnpj(doc):
    d = "".join(ch for ch in doc if ch.isdigit()).zfill(14)
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def resumir(arquivo, ano, manifesto):
    v = lambda x: float(x or 0)
    tot = {o: collections.Counter() for o in ORGAOS.values()}
    funcao, mes = collections.Counter(), collections.Counter()
    credores = {}
    folha = collections.Counter()
    pf = collections.defaultdict(lambda: {"pago": 0.0, "n": 0})
    datas, meses_receb = [], set()
    with gzip.open(arquivo, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            org = ORGAOS[r["cd_orgao"]]
            meses_receb.add(int(r["mes_recebimento"]))
            op = r["tipo_operacao"]
            if op == "P" and r["dt_operacao"][:4] == str(ano):
                datas.append(r["dt_operacao"])
            if op == "E":
                tot[org]["empenhado"] += v(r["vl_empenho"])
                continue
            if op == "L":
                tot[org]["liquidado"] += v(r["vl_liquidacao"])
                continue
            pago = v(r["vl_pagamento"])
            tot[org]["pago"] += pago
            funcao[r["ds_funcao"].strip() or "Não informada"] += pago
            mes[r["dt_operacao"][:7]] += pago
            if r["tp_pessoa"] == "PF":
                cat = r["ds_rubrica"].strip().capitalize() or "Outros"
                pf[cat]["pago"] += pago
                pf[cat]["n"] += 1
                continue
            nome, e_folha = rotulo_credor(r["nm_credor"])
            if e_folha:
                folha[nome] += pago
                continue
            c = credores.setdefault(r["cnpj_cpf"], {"nome": nome, "cnpj": cnpj(r["cnpj_cpf"]), "pago": 0.0, "n": 0, "funcoes": collections.Counter()})
            c["pago"] += pago
            c["n"] += 1
            c["funcoes"][r["ds_funcao"].strip()] += pago
    ranking = sorted(credores.values(), key=lambda c: -c["pago"])
    for c in ranking:
        c["pago"] = round(c["pago"], 2)
        c["funcoes"] = [f for f, _ in c["funcoes"].most_common(2)]
    return {
        "ano": ano,
        "periodo": {"inicio": min(datas) if datas else None, "fim": max(datas) if datas else None},
        "ultimo_mes_enviado": max(meses_receb) if meses_receb else None,
        "totais": {o: {k: round(x, 2) for k, x in c.items()} for o, c in tot.items()},
        "por_funcao": [{"funcao": k, "pago": round(x, 2)} for k, x in funcao.most_common()],
        "por_mes": [{"mes": k, "pago": round(x, 2)} for k, x in sorted(mes.items())],
        "folha": [{"nome": k, "pago": round(x, 2)} for k, x in folha.most_common()],
        "credores": ranking[:40],
        "n_credores": len(ranking),
        "pessoas_fisicas": sorted(({"tipo": k, "pago": round(x["pago"], 2), "n": x["n"]} for k, x in pf.items()), key=lambda x: -x["pago"]),
        "fonte": {"id": f"f-tce-empenhos-{ano}", "titulo": f"Despesa por empenhos {ano}: Prefeitura e Câmara de Mostardas",
                  "emissor": "TCE-RS (dados informados pelo próprio órgão)", "tipo": "dados-oficiais",
                  "url": f"https://dados.tce.rs.gov.br/dataset/despesa-orcamentaria-por-empenhos-{ano}",
                  "consultado_em": manifesto.get("coletado_em") or dt.date.today().isoformat(), "copia": manifesto},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ano", type=int)
    ap.add_argument("--filtrado", help="arquivo .csv.gz já filtrado para Mostardas (pula o download)")
    ap.add_argument("--last-modified", help="data do arquivo estadual, quando se usa --filtrado")
    a = ap.parse_args()
    if a.filtrado:
        BRUTO.mkdir(parents=True, exist_ok=True)
        destino = BRUTO / f"mostardas-{a.ano}.csv.gz"
        destino.write_bytes(pathlib.Path(a.filtrado).read_bytes())
        manifesto = {"url": URL.format(ano=a.ano), "last_modified": a.last_modified, "arquivo": str(destino.relative_to(RAIZ)),
                     "sha256_filtrado": hashlib.sha256(destino.read_bytes()).hexdigest(), "coletado_em": dt.date.today().isoformat()}
        (BRUTO / f"manifesto-{a.ano}.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        destino, manifesto = baixar_e_filtrar(a.ano)
        if destino is None:
            print(f"ok: {a.ano} sem mudança no TCE-RS desde {manifesto.get('last_modified')}; resumo mantido")
            return
    resumo = resumir(destino, a.ano, manifesto)
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / f"resumo-{a.ano}.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    p = resumo["totais"]["prefeitura"]
    print(f"ok: {a.ano} de {resumo['periodo']['inicio']} a {resumo['periodo']['fim']}; Prefeitura pagou R$ {p.get('pago', 0):,.2f}; {resumo['n_credores']} credores PJ")


if __name__ == "__main__":
    main()
