"""Coleta o cadastro (CNPJ) e o quadro de sócios das empresas que vendem para Mostardas.

Por que: fiscalizar uma compra inclui saber quem está por trás da empresa: sócios,
administradores e representantes legais, desde quando a empresa existe e se está ativa.

Fonte: Cadastro Nacional da Pessoa Jurídica, da Receita Federal, consultado pelo Minha Receita
(minhareceita.org), espelho aberto e mensal dos arquivos públicos da Receita. Em 2026 a Receita
mudou o endereço desses arquivos; quando o novo endereço oficial estiver estável, este coletor
pode ler direto da fonte primária sem mudar o formato da saída.

Incremental: só consulta CNPJs novos ou vistos há mais de 30 dias (a base muda uma vez por mês),
com poucas consultas simultâneas, para não sobrecarregar um serviço gratuito.

Privacidade (ARQUITETURA.md, decisão 10): publica nome, qualificação e data de entrada de cada
sócio, com o CPF mascarado como a própria Receita publica. Não publica endereço, telefone,
e-mail nem faixa etária: em microempreendedor individual, esses dados são os da pessoa.

Uso: python3 scripts/coletar_cnpj.py [--max 400]
"""
import argparse
import concurrent.futures
import datetime as dt
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from privacidade import mascarar_cpf_em_nome  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FORNECEDORES = RAIZ / "dados" / "compras" / "fornecedores.json"
SAIDA = RAIZ / "dados" / "empresas"
API = "https://minhareceita.org/{cnpj}"
VALIDADE_DIAS = 30
TIPO_SOCIO = {1: "PJ", 2: "PF", 3: "Estrangeiro"}


def consultar(cnpj):
    req = urllib.request.Request(API.format(cnpj=cnpj), headers={"User-Agent": "guia-instituicoes-mostardas (projeto cidadao)"})
    for tentativa in range(6):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, OSError):  # inclui tempo esgotado e conexão interrompida
            pass
        time.sleep(2 ** tentativa)
    raise RuntimeError(f"sem resposta para {cnpj}")


def normalizar(j, hoje):
    socios = []
    for s in j.get("qsa") or []:
        tipo = TIPO_SOCIO.get(s.get("identificador_de_socio"), "Outro")
        doc = (s.get("cnpj_cpf_do_socio") or "").strip() or None
        if tipo == "PF" and doc and "*" not in doc:
            doc = None  # CPF sem máscara nunca sai daqui
        socio = {"nome": mascarar_cpf_em_nome((s.get("nome_socio") or "").strip()), "tipo": tipo,
                 "qualificacao": s.get("qualificacao_socio"), "entrada": s.get("data_entrada_sociedade"), "doc": doc}
        rep = (s.get("nome_representante_legal") or "").strip()
        if rep:
            socio["representante"] = {"nome": rep, "qualificacao": s.get("qualificacao_representante_legal")}
        socios.append(socio)
    return {
        "razao_social": mascarar_cpf_em_nome(j.get("razao_social") or ""), "nome_fantasia": (j.get("nome_fantasia") or "").strip() or None,
        "situacao": j.get("descricao_situacao_cadastral"), "data_situacao": j.get("data_situacao_cadastral"),
        "motivo_situacao": (j.get("descricao_motivo_situacao_cadastral") or "").strip() or None,
        "abertura": j.get("data_inicio_atividade"), "atividade": j.get("cnae_fiscal_descricao"), "natureza": j.get("natureza_juridica"),
        "porte": j.get("porte"), "capital_social": j.get("capital_social"), "municipio": j.get("municipio"), "uf": j.get("uf"),
        "mei": bool(j.get("opcao_pelo_mei")), "socios": socios, "consultado_em": hoje,
    }


def gravar(base):
    """Um registro por linha: o histórico do Git mostra exatamente qual empresa mudou."""
    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas = [f"  {json.dumps(k)}: {json.dumps(base[k], ensure_ascii=False, separators=(',', ':'))}" for k in sorted(base)]
    (SAIDA / "empresas.json").write_text("{\n" + ",\n".join(linhas) + "\n}\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=400, help="máximo de consultas nesta execução")
    a = ap.parse_args()
    hoje = dt.date.today()
    caminho = SAIDA / "empresas.json"
    base = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}
    cnpjs = sorted({"".join(ch for ch in f["doc"] if ch.isdigit()) for f in json.loads(FORNECEDORES.read_text(encoding="utf-8"))
                    if f["tipo"] == "J" and f.get("doc")})
    limite = (hoje - dt.timedelta(days=VALIDADE_DIAS)).isoformat()
    pendentes = [c for c in cnpjs if c not in base] + [c for c in cnpjs if c in base and base[c]["consultado_em"] < limite]
    pendentes = pendentes[:a.max]

    def tarefa(cnpj):
        try:
            j = consultar(cnpj)
        except RuntimeError:
            return cnpj, None  # fica para a próxima execução; uma falha não derruba as outras
        time.sleep(0.3)
        return cnpj, (normalizar(j, hoje.isoformat()) if j else {"nao_encontrado": True, "consultado_em": hoje.isoformat()})

    feitos = falhas = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        for cnpj, reg in ex.map(tarefa, pendentes):
            if reg is None:
                falhas += 1
                continue
            base[cnpj] = reg
            feitos += 1
            if feitos % 200 == 0:
                gravar(base)
    gravar(base)
    fonte = {"id": "f-cnpj-receita", "titulo": "Cadastro Nacional da Pessoa Jurídica (Receita Federal), consultado pelo Minha Receita",
             "emissor": "Receita Federal, pelo espelho aberto minhareceita.org", "tipo": "dados-oficiais", "url": "https://minhareceita.org/",
             "consultado_em": hoje.isoformat(), "empresas": len(base)}
    (SAIDA / "fonte.json").write_text(json.dumps(fonte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    com_socios = sum(1 for r in base.values() if r.get("socios"))
    print(f"ok: {feitos} consultas nesta execução ({falhas} ficaram para a próxima); {len(base)} empresas na base, {com_socios} com quadro de sócios; faltam {len(cnpjs) - len(base)}")


if __name__ == "__main__":
    main()
