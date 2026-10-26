"""Coleta licitações e contratos de Mostardas no LicitaCon, do TCE-RS, e normaliza para dados/compras/.

Por que este coletor: licitações e contratos são milhares de registros que mudam todo dia.
Não cabem na curadoria à mão de dados/*.json (ARQUITETURA.md, decisão 11). A fonte é o
LicitaCon: o município é obrigado a informar ali cada processo, e o TCE-RS publica os
arquivos em dados abertos. Atenção: os dados são informados pelo próprio órgão e não são
analisados pelo Tribunal antes de publicados. A página precisa dizer isso.

Privacidade (decisão 10): CPF de pessoa física nunca sai daqui sem máscara.

Uso: python3 scripts/coletar_licitacon.py [--local PASTA_COM_ZIPS]
"""
import argparse
import collections
import csv
import datetime as dt
import hashlib
import io
import json
import pathlib
import urllib.request
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from privacidade import mascarar_cpf_em_nome, mascarar_cpf_rotulado, mascarar_documento

RAIZ = pathlib.Path(__file__).resolve().parent.parent
BRUTO = RAIZ / "bruto" / "tce-rs" / "licitacon"
SAIDA = RAIZ / "dados" / "compras"
URL = "https://dados.tce.rs.gov.br/dados/licitacon/{tipo}/orgao/{orgao}.csv.zip"
ORGAOS = {"52400": "prefeitura", "52401": "camara"}

# Nomes conferidos nas páginas do LicitaCon Cidadão (TCE-RS) em 26/10/2026.
MODALIDADES = {
    "PRD": ("Dispensa", "direta"), "PRI": ("Inexigibilidade", "direta"),
    "RPO": ("Adesão a ata de registro de preços (carona)", "direta"),
    "PCE": ("Pregão eletrônico", "competitiva"), "PRE": ("Pregão eletrônico (lei antiga)", "competitiva"),
    "PRP": ("Pregão presencial", "competitiva"), "CCE": ("Concorrência eletrônica", "competitiva"),
    "CNC": ("Concorrência (lei antiga)", "competitiva"), "TMP": ("Tomada de preços", "competitiva"),
    "CNV": ("Convite", "competitiva"), "CPP": ("Chamada pública da merenda (PNAE)", "chamamento"),
    "CHP": ("Chamamento público", "chamamento"), "CPC": ("Chamamento público ou credenciamento", "chamamento"),
    "LEI": ("Leilão presencial", "alienacao"), "LEE": ("Leilão eletrônico", "alienacao"),
}
INSTRUMENTOS = {"C": "Contrato", "ARP": "Ata de registro de preços"}


def baixar(tipo, orgao, local):
    destino = BRUTO / f"{tipo}-{orgao}.csv.zip"
    destino.parent.mkdir(parents=True, exist_ok=True)
    url = URL.format(tipo=tipo, orgao=orgao)
    modificado = None
    if local:
        corpo = (pathlib.Path(local) / f"{tipo}-{orgao}.zip").read_bytes()
    else:
        with urllib.request.urlopen(url, timeout=180) as r:
            corpo = r.read()
            modificado = r.headers.get("Last-Modified")
    destino.write_bytes(corpo)
    return {"url": url, "arquivo": str(destino.relative_to(RAIZ)), "sha256": hashlib.sha256(corpo).hexdigest(),
            "bytes": len(corpo), "last_modified": modificado}, zipfile.ZipFile(io.BytesIO(corpo))


def tabela(z, nome):
    """Lê um CSV do zip. Usa leitor por posição porque alguns arquivos repetem nomes de coluna."""
    rd = csv.reader(io.StringIO(z.read(nome).decode("utf-8-sig", errors="replace")))
    cab = next(rd)
    return cab, list(rd)


def dicts(z, nome):
    cab, linhas = tabela(z, nome)
    return [dict(zip(cab, l)) for l in linhas]


def num(v):
    try:
        return round(float(v), 2) if v not in ("", None) else None
    except ValueError:
        return None


def chave_lic(orgao, mod, nr, ano):
    return f"{orgao}-{mod}-{nr}-{ano}"


def situacao(lic, eventos, lotes):
    tipos = {e["CD_TIPO_EVENTO"] for e in eventos}
    res = lic["TP_RESULTADO_GLOBAL"]
    resultados_lote = {l["res"] for l in lotes}
    if "REO" in tipos or res == "R":
        return "Revogada"
    if res == "D" or (resultados_lote and resultados_lote <= {"D"}):
        return "Deserta"
    if res == "F" or (resultados_lote and resultados_lote <= {"D", "F"}):
        return "Fracassada"
    if lic["DT_HOMOLOGACAO"]:
        return "Concluída"
    if MODALIDADES.get(lic["CD_TIPO_MODALIDADE"], ("", ""))[1] == "direta":
        return "Contratação direta publicada"
    return {"HAP": "Em julgamento", "EPU": "Edital publicado"}.get(lic["CD_TIPO_FASE_ATUAL"], "Em andamento")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", help="pasta com os zips já baixados (para testes)")
    a = ap.parse_args()
    hoje = dt.date.today().isoformat()
    manifesto, lics, conts = [], [], []
    pessoas = {}
    for orgao, apelido in ORGAOS.items():
        m_l, zl = baixar("licitacao", orgao, a.local)
        m_c, zc = baixar("contrato", orgao, a.local)
        manifesto += [m_l, m_c]
        for z in (zl, zc):
            for p in dicts(z, "pessoas.csv"):
                pessoas[(p["TP_DOCUMENTO"], p["NR_DOCUMENTO"])] = mascarar_cpf_em_nome(p["NM_PESSOA"].strip())

        def quem(tp, nr):
            if not nr:
                return None
            return {"nome": pessoas.get((tp, nr), "Nome não informado"), "doc": mascarar_documento(tp, nr), "tipo": tp, "_chave": f"{tp}{nr}"}

        eventos = collections.defaultdict(list)
        for e in dicts(zl, "evento_lic.csv"):
            eventos[chave_lic(orgao, e["CD_TIPO_MODALIDADE"], e["NR_LICITACAO"], e["ANO_LICITACAO"])].append(e)
        participantes = collections.Counter()
        for l in dicts(zl, "licitante.csv"):
            participantes[chave_lic(orgao, l["CD_TIPO_MODALIDADE"], l["NR_LICITACAO"], l["ANO_LICITACAO"])] += 1
        documentos = collections.Counter()
        for d in dicts(zl, "documento_lic.csv"):
            documentos[chave_lic(orgao, d["CD_TIPO_MODALIDADE"], d["NR_LICITACAO"], d["ANO_LICITACAO"])] += 1
        # lote.csv repete TP_DOCUMENTO/NR_DOCUMENTO; o primeiro par é o vencedor do lote.
        cab, linhas = tabela(zl, "lote.csv")
        i = {c: cab.index(c) for c in ("CD_TIPO_MODALIDADE", "NR_LICITACAO", "ANO_LICITACAO", "VL_HOMOLOGADO", "TP_RESULTADO_LOTE", "TP_DOCUMENTO", "NR_DOCUMENTO")}
        lotes = collections.defaultdict(list)
        for l in linhas:
            lotes[chave_lic(orgao, l[i["CD_TIPO_MODALIDADE"]], l[i["NR_LICITACAO"]], l[i["ANO_LICITACAO"]])].append(
                {"res": l[i["TP_RESULTADO_LOTE"]], "vl": num(l[i["VL_HOMOLOGADO"]]) or 0, "tp": l[i["TP_DOCUMENTO"]], "nr": l[i["NR_DOCUMENTO"]]})

        for lic in dicts(zl, "licitacao.csv"):
            k = chave_lic(orgao, lic["CD_TIPO_MODALIDADE"], lic["NR_LICITACAO"], lic["ANO_LICITACAO"])
            mod = lic["CD_TIPO_MODALIDADE"]
            nome_mod, grupo = MODALIDADES.get(mod, (mod, "outra"))
            vencedores = {}
            for lt in lotes[k]:
                if lt["res"] == "A" and lt["nr"]:
                    v = quem(lt["tp"], lt["nr"])
                    vencedores.setdefault(v["_chave"], {**v, "valor": 0})["valor"] += lt["vl"]
            for tp, nr in ((lic["TP_DOCUMENTO_VENCEDOR"], lic["NR_DOCUMENTO_VENCEDOR"]), (lic["TP_DOCUMENTO_FORNECEDOR"], lic["NR_DOCUMENTO_FORNECEDOR"])):
                if nr and f"{tp}{nr}" not in vencedores:
                    vencedores[f"{tp}{nr}"] = {**quem(tp, nr), "valor": None}
            homologado = max(num(lic["VL_HOMOLOGADO"]) or 0, sum(lt["vl"] for lt in lotes[k] if lt["res"] == "A"))
            fundamento = None
            if lic["DS_LEI"] and lic["NR_ARTIGO"] and lic["NR_ARTIGO"] != "0":
                fundamento = f"Lei {lic['DS_LEI']}, art. {lic['NR_ARTIGO']}" + (f", {lic['DS_INCISO']}" if lic["DS_INCISO"] else "")
            lics.append({
                "id": k, "orgao": apelido, "mod": mod, "modalidade": nome_mod, "grupo": grupo,
                "numero": f"{lic['NR_LICITACAO']}/{lic['ANO_LICITACAO']}", "ano": int(lic["ANO_LICITACAO"]),
                "objeto": mascarar_cpf_rotulado(" ".join(lic["DS_OBJETO"].split())), "valor_estimado": num(lic["VL_LICITACAO"]),
                "valor_homologado": homologado or None, "abertura": lic["DT_ABERTURA"] or None,
                "homologacao": lic["DT_HOMOLOGACAO"] or None, "situacao": situacao(lic, eventos[k], lotes[k]),
                "fundamento": fundamento, "participantes": participantes[k], "documentos": documentos[k],
                "vencedores": list(vencedores.values()), "link": lic["LINK_LICITACON_CIDADAO"] or None,
            })

        alter = collections.defaultdict(list)
        for al in dicts(zc, "alteracao.csv"):
            alter[(al["NR_CONTRATO"], al["ANO_CONTRATO"], al["TP_INSTRUMENTO"])].append(al)
        for c in dicts(zc, "contrato.csv"):
            ads = alter[(c["NR_CONTRATO"], c["ANO_CONTRATO"], c["TP_INSTRUMENTO"])]
            inicial = num(c["VL_CONTRATO"]) or 0
            acres = round(sum(num(x["VL_ACRESCIMO"]) or 0 for x in ads), 2)
            # Só o acréscimo de quantidade (ACA) conta no limite de 25% do art. 125 da Lei 14.133.
            # Renovação (REN), reajuste (RJP) e reequilíbrio (REF) aumentam o valor, mas são outra coisa.
            por_tipo = collections.Counter()
            for x in ads:
                por_tipo[x["CD_TIPO_OPERACAO"]] += num(x["VL_ACRESCIMO"]) or 0
            reduc = round(sum(num(x["VL_REDUCAO"]) or 0 for x in ads), 2)
            nome_mod, grupo_mod = MODALIDADES.get(c["CD_TIPO_MODALIDADE"], (c["CD_TIPO_MODALIDADE"], "outra"))
            conts.append({
                "id": f"{orgao}-{c['TP_INSTRUMENTO']}-{c['NR_CONTRATO']}-{c['ANO_CONTRATO']}", "orgao": apelido,
                "numero": f"{c['NR_CONTRATO']}/{c['ANO_CONTRATO']}", "ano": int(c["ANO_CONTRATO"]),
                "instrumento": INSTRUMENTOS.get(c["TP_INSTRUMENTO"], "Outro instrumento"),
                "licitacao": chave_lic(orgao, c["CD_TIPO_MODALIDADE"], c["NR_LICITACAO"], c["ANO_LICITACAO"]) if c["NR_LICITACAO"] else None,
                "mod": c["CD_TIPO_MODALIDADE"], "modalidade": nome_mod, "grupo": grupo_mod,
                "fornecedor": quem(c["TP_DOCUMENTO"], c["NR_DOCUMENTO"]),
                "objeto": mascarar_cpf_rotulado(" ".join(c["DS_OBJETO"].split())), "valor_inicial": inicial,
                "acrescimos": acres, "reducoes": reduc, "valor_atual": round(inicial + acres - reduc, 2),
                "aditivos": len(ads), "aditivos_prazo": sum(1 for x in ads if (num(x["NR_DIAS_NOVO_PRAZO"]) or 0) > 0),
                "acrescimo_quantidade": round(por_tipo["ACA"], 2), "renovacoes": sum(1 for x in ads if x["CD_TIPO_OPERACAO"] == "REN"),
                "valor_renovacoes": round(por_tipo["REN"], 2), "reajustes": round(por_tipo["RJP"] + por_tipo["REF"], 2),
                "assinatura": c["DT_ASSINATURA"] or None, "inicio": c["DT_INICIO_VIGENCIA"] or None, "fim": c["DT_FINAL_VIGENCIA"] or None,
                "link": c["LINK_LICITACON_CIDADAO"] or None,
            })

    # Fornecedores: soma por documento, mas o documento completo nunca vai para a saída.
    forn = {}
    for c in conts:
        f = c["fornecedor"]
        if not f:
            continue
        r = forn.setdefault(f["_chave"], {"nome": f["nome"], "doc": f["doc"], "tipo": f["tipo"], "contratos": 0, "valor_contratado": 0.0, "vitorias": 0})
        r["contratos"] += 1
        r["valor_contratado"] = round(r["valor_contratado"] + c["valor_atual"], 2)
    for l in lics:
        for v in l["vencedores"]:
            r = forn.setdefault(v["_chave"], {"nome": v["nome"], "doc": v["doc"], "tipo": v["tipo"], "contratos": 0, "valor_contratado": 0.0, "vitorias": 0})
            r["vitorias"] += 1
    for registro in lics:
        for v in registro["vencedores"]:
            v.pop("_chave", None)
    for c in conts:
        if c["fornecedor"]:
            c["fornecedor"].pop("_chave", None)

    SAIDA.mkdir(parents=True, exist_ok=True)
    lics.sort(key=lambda x: (x["abertura"] or f"{x['ano']}-00-00", x["id"]), reverse=True)
    conts.sort(key=lambda x: (x["assinatura"] or f"{x['ano']}-00-00", x["id"]), reverse=True)
    for nome, dados in (("licitacoes.json", lics), ("contratos.json", conts),
                        ("fornecedores.json", sorted(forn.values(), key=lambda f: -f["valor_contratado"]))):
        # Um registro por linha: o histórico do Git mostra exatamente qual licitação ou contrato mudou.
        (SAIDA / nome).write_text("[\n" + ",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in dados) + "\n]\n", encoding="utf-8")
    fonte = {"id": "f-tce-licitacon", "titulo": "LicitaCon: licitações e contratos da Prefeitura e da Câmara de Mostardas", "emissor": "TCE-RS (dados informados pelo próprio órgão)",
             "tipo": "dados-oficiais", "url": "https://dados.tce.rs.gov.br/dataset/licitacoes-pm-de-mostardas", "consultado_em": hoje,
             "copia": {"arquivos": manifesto}}
    (SAIDA / "fonte.json").write_text(json.dumps(fonte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ok: {len(lics)} licitações, {len(conts)} contratos, {len(forn)} fornecedores")


if __name__ == "__main__":
    main()
