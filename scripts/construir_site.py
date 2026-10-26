"""Monta o site estático completo em site/, que é o que vai para o Cloudflare Pages.

Por que um passo só: a automação diária (GitHub Actions) precisa de um comando que valide os
dados, gere as páginas e publique os dados abertos juntos. Se qualquer etapa falhar, nada
é publicado e o erro aparece na execução.

Uso: python3 scripts/construir_site.py [--saida site] [--hoje AAAA-MM-DD]
"""
import argparse
import csv
import datetime as dt
import json
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import construir  # noqa: E402
import construir_compras  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"

CABECALHOS = """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
/compras-dados.json
  Cache-Control: public, max-age=3600
/dados/*
  Access-Control-Allow-Origin: *
  Cache-Control: public, max-age=3600
"""


def csv_de(caminho, linhas, campos):
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(campos)
        for l in linhas:
            w.writerow(l)


def dados_abertos(destino):
    """Copia os dados curados e gera CSVs das tabelas grandes, para qualquer pessoa reutilizar."""
    shutil.copytree(DADOS, destino, dirs_exist_ok=True)
    L = json.loads((DADOS / "compras" / "licitacoes.json").read_text(encoding="utf-8"))
    C = json.loads((DADOS / "compras" / "contratos.json").read_text(encoding="utf-8"))
    csv_de(destino / "compras" / "licitacoes.csv",
           ([l["orgao"], l["modalidade"], l["numero"], l["objeto"], l["valor_estimado"], l["valor_homologado"], l["situacao"], l["abertura"],
             l["homologacao"], l["participantes"], "; ".join(v["nome"] for v in l["vencedores"]), l["link"]] for l in L),
           ["orgao", "modalidade", "numero", "objeto", "valor_estimado", "valor_homologado", "situacao", "abertura", "homologacao",
            "participantes", "vencedores", "link_tce"])
    csv_de(destino / "compras" / "contratos.csv",
           ([c["orgao"], c["instrumento"], c["numero"], c["modalidade"], (c["fornecedor"] or {}).get("nome"), (c["fornecedor"] or {}).get("doc"),
             c["objeto"], c["valor_inicial"], c["valor_atual"], c["acrescimo_quantidade"], c["aditivos"], c["assinatura"], c["inicio"], c["fim"], c["link"]] for c in C),
           ["orgao", "instrumento", "numero", "modalidade", "fornecedor", "documento", "objeto", "valor_inicial", "valor_com_aditivos",
            "acrescimo_quantidade", "aditivos", "assinatura", "inicio_vigencia", "fim_vigencia", "link_tce"])
    emp = DADOS / "empresas" / "empresas.json"
    if emp.exists():
        E = json.loads(emp.read_text(encoding="utf-8"))
        csv_de(destino / "empresas" / "socios.csv",
               ([cnpj, e.get("razao_social"), s["nome"], s["tipo"], s.get("qualificacao"), s.get("entrada"), s.get("doc"),
                 (s.get("representante") or {}).get("nome")] for cnpj, e in sorted(E.items()) for s in e.get("socios", [])),
               ["cnpj", "razao_social", "socio", "tipo", "qualificacao", "entrada", "documento_mascarado", "representante_legal"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default=str(RAIZ / "site"))
    ap.add_argument("--hoje", default=dt.date.today().isoformat())
    a = ap.parse_args()
    hoje = dt.date.fromisoformat(a.hoje)
    saida = pathlib.Path(a.saida)
    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True)
    construir.gerar(saida / "index.html", hoje, documento=True)
    c = construir_compras.Compras(hoje)
    (saida / "compras.html").write_text(c.montar(), encoding="utf-8")
    (saida / "compras-dados.json").write_text(json.dumps(c.base(), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    dados_abertos(saida / "dados")
    (saida / "_headers").write_text(CABECALHOS, encoding="utf-8")
    (saida / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
    arquivos = sum(1 for p in saida.rglob("*") if p.is_file())
    tamanho = sum(p.stat().st_size for p in saida.rglob("*") if p.is_file())
    print(f"ok: site em {saida} com {arquivos} arquivos ({tamanho // 1024} KB)")


if __name__ == "__main__":
    main()
