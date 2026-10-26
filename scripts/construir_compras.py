"""Gera a página de licitações, contratos e pagamentos (compras.html) e a base da busca (compras-dados.json).

Por que separado do guia: são milhares de registros que mudam todo dia, vindos de coletores
(dados/compras/, dados/pagamentos/), e não fatos curados à mão. O resumo, os pontos para
acompanhar e as publicações mais recentes saem prontos no HTML, para a página fazer sentido
mesmo sem carregar a base. A busca completa carrega o JSON e filtra no aparelho de quem lê.

Uso: python3 scripts/construir_compras.py PASTA_DE_SAIDA [--hoje AAAA-MM-DD]
"""
import argparse
import collections
import datetime as dt
import email.utils
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from construir import br_data, esc, milhar, pct, reais_curto  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
MODELOS = RAIZ / "modelos"
ORG = ["Prefeitura", "Câmara"]
ORG_IDX = {"prefeitura": 0, "camara": 1}


def ler(rel):
    return json.loads((DADOS / rel).read_text(encoding="utf-8"))


def data_http(texto):
    if not texto:
        return None
    return email.utils.parsedate_to_datetime(texto).date().isoformat()


def digitos(s):
    return "".join(ch for ch in (s or "") if ch.isdigit())


def mi(v):
    return "R$ " + f"{v / 1e6:.1f}".replace(".", ",") + " milhões"


class Compras:
    def __init__(self, hoje):
        self.hoje, self.hoje_iso = hoje, hoje.isoformat()
        self.L = ler("compras/licitacoes.json")
        self.C = ler("compras/contratos.json")
        self.fonte_lc = ler("compras/fonte.json")
        self.normas = {n["id"]: n for n in ler("normas.json")}
        self.pag = {}
        for p in sorted((DADOS / "pagamentos").glob("resumo-*.json")):
            r = json.loads(p.read_text(encoding="utf-8"))
            self.pag[r["ano"]] = r
        emp = DADOS / "empresas" / "empresas.json"
        self.E = {k: v for k, v in json.loads(emp.read_text(encoding="utf-8")).items() if not v.get("nao_encontrado")} if emp.exists() else {}
        self.fonte_emp = ler("empresas/fonte.json") if (DADOS / "empresas" / "fonte.json").exists() else None
        self.cont_por_cnpj = collections.defaultdict(list)
        for c in self.C:
            f = c["fornecedor"]
            if f and f["tipo"] == "J" and f.get("doc"):
                self.cont_por_cnpj[digitos(f["doc"])].append(c)
        # Quando a licitação não informa o vencedor, o contrato assinado a partir dela informa.
        self.forn_por_lic = collections.defaultdict(dict)
        for c in self.C:
            if c["licitacao"] and c["fornecedor"]:
                self.forn_por_lic[c["licitacao"]][c["fornecedor"]["nome"]] = c["fornecedor"].get("doc")
        datas = [data_http(a.get("last_modified")) for a in self.fonte_lc["copia"]["arquivos"]]
        self.data_lc = max([d for d in datas if d] or [self.fonte_lc["consultado_em"]])

    # -- peças

    def porque(self, ids, texto=None):
        ns = [self.normas[i] for i in ids]
        corpo = texto or " ".join(n["explica"] for n in ns)
        refs = " · ".join(f'<a href="{esc(n["url"])}">{esc(n["referencia"])}</a>' for n in ns)
        return f'<div class="porque"><p><b>Por quê:</b> {esc(corpo)}</p><p class="ref">Base legal: {refs}</p></div>'

    def fonte_lc_html(self):
        return (f'<p class="source">Fonte: <a href="{esc(self.fonte_lc["url"])}">{esc(self.fonte_lc["titulo"])}</a>, '
                f'arquivo de {br_data(self.data_lc)}. Dados informados pelo próprio órgão e não analisados pelo TCE-RS.</p>')

    def valor_lic(self, l):
        if l["valor_homologado"]:
            return l["valor_homologado"], "h"
        if l["valor_estimado"]:
            return l["valor_estimado"], "e"
        return None, ""

    def vencedores(self, l):
        pares = [(v["nome"], v.get("doc")) for v in l["vencedores"]] or list(self.forn_por_lic.get(l["id"], {}).items())
        texto = "; ".join(n + (f" ({d})" if d else "") for n, d in pares[:3])
        return texto + (f" e mais {len(pares) - 3}" if len(pares) > 3 else "")

    def cartao_lic(self, l):
        v, tv = self.valor_lic(l)
        meta = []
        if v is not None:
            meta.append(f'{"Valor homologado" if tv == "h" else "Valor estimado"}: <b>R$ {milhar(v, 2)}</b>')
        if l["abertura"]:
            meta.append(f'Data: <b>{br_data(l["abertura"])}</b>')
        if l["participantes"]:
            meta.append(f'Participantes: <b>{l["participantes"]}</b>')
        ok = l["situacao"] in ("Concluída", "Contratação direta publicada")
        ruim = l["situacao"] in ("Revogada", "Deserta", "Fracassada")
        quem = self.vencedores(l)
        venc = f'<p class="meta"><span>Quem ganhou: <b>{esc(quem)}</b></span></p>' if quem else ""
        link = f'<a href="{esc(l["link"])}" rel="noopener">Ver documentos no TCE-RS</a>' if l["link"] else ""
        return (f'<li class="res"><div class="topo"><span class="id">{esc(l["modalidade"])} {esc(l["numero"])} · {ORG[ORG_IDX[l["orgao"]]]}</span>'
                f'<span class="chip {"ok" if ok else "falta" if ruim else "info"}">{esc(l["situacao"])}</span></div>'
                f'<p class="obj">{esc(l["objeto"])}</p><p class="meta">{"".join(f"<span>{m}</span>" for m in meta)}</p>{venc}{link}</li>')

    def cartao_con(self, c):
        vig = c["fim"] and c["fim"] >= self.hoje_iso
        estado = f'Em vigor até {br_data(c["fim"])}' if vig else (f'Terminou em {br_data(c["fim"])}' if c["fim"] else "Vigência não informada")
        f = c["fornecedor"]
        doc = f' ({esc(f["doc"])})' if f and f.get("doc") else ""
        forn = f'<p class="meta"><span>Fornecedor: <b>{esc(f["nome"])}{doc}</b></span></p>' if f else ""
        val = [f'Valor inicial: <b>R$ {milhar(c["valor_inicial"], 2)}</b>']
        if c["valor_atual"] != c["valor_inicial"]:
            val.append(f'Valor com aditivos: <b>R$ {milhar(c["valor_atual"], 2)}</b>')
        if c["assinatura"]:
            val.append(f'Assinado em: <b>{br_data(c["assinatura"])}</b>')
        link = f'<a href="{esc(c["link"])}" rel="noopener">Ver documentos no TCE-RS</a>' if c["link"] else ""
        return (f'<li class="res"><div class="topo"><span class="id">{esc(c["instrumento"])} {esc(c["numero"])} · {ORG[ORG_IDX[c["orgao"]]]} · {esc(c["modalidade"])}</span>'
                f'<span class="chip {"ok" if vig else "info"}">{esc(estado)}</span></div><p class="obj">{esc(c["objeto"])}</p>{forn}'
                f'<p class="meta">{"".join(f"<span>{m}</span>" for m in val)}</p>{link}</li>')

    # -- seções

    def aviso(self):
        p26 = self.pag.get(self.hoje.year)
        pag = f' Pagamentos: até {br_data(p26["periodo"]["fim"])}, porque o município envia esses dados a cada dois meses.' if p26 else ""
        return (f'    <p class="notice"><strong>De onde vêm os dados.</strong> Do LicitaCon e das prestações de contas que o próprio município envia ao '
                f'Tribunal de Contas do Estado (TCE-RS), que publica tudo sem analisar antes. Licitações e contratos: arquivo do TCE-RS de '
                f'{br_data(self.data_lc)}.{pag}</p>')

    def secao_resumo(self):
        ano = self.hoje.year
        la = [l for l in self.L if l["ano"] == ano]
        ca = [c for c in self.C if c["ano"] == ano]
        diretas = [l for l in la if l["grupo"] == "direta"]
        vig = [c for c in self.C if c["fim"] and c["fim"] >= self.hoje_iso and (c["inicio"] or "") <= self.hoje_iso]
        p25 = self.pag.get(ano - 1)
        kpis = [
            (f"Processos de compra em {ano}", milhar(len(la)), f"{len(diretas)} sem licitação, por dispensa ou inexigibilidade ({pct(100 * len(diretas) / max(len(la), 1))})"),
            (f"Valor contratado em {ano}", mi(sum(c["valor_atual"] for c in ca)), f"em {milhar(len(ca))} contratos assinados"),
            ("Contratos em vigor hoje", milhar(len(vig)), f"somam {mi(sum(c['valor_atual'] for c in vig))}"),
        ]
        if p25:
            kpis.append((f"Pago pela Prefeitura em {ano - 1}", mi(p25["totais"]["prefeitura"]["pago"]), f"a {milhar(p25['n_credores'])} empresas e órgãos, além da folha"))
        kpi_html = "".join(f'<div class="kpi"><span class="label">{esc(t)}</span><span class="valor">{esc(v)}</span><span class="det">{esc(d)}</span></div>' for t, v, d in kpis)
        # Processos do ano por modalidade: um único tom, valores ao lado.
        por = collections.defaultdict(lambda: [0, 0.0])
        for l in la:
            v, _ = self.valor_lic(l)
            por[l["modalidade"]][0] += 1
            por[l["modalidade"]][1] += v or 0
        maior = max((n for n, _ in por.values()), default=1)
        barras = "".join(
            f'<li class="bar-row" tabindex="0" data-val="{n} processos" data-share="{esc(pct(100 * n / max(len(la), 1)))} dos processos de {ano}" '
            f'data-pc="R$ {milhar(v, 2)} somados"><span class="bar-label">{esc(m)}</span><span class="bar-track"><span class="bar" style="--w:{100 * n / maior:.2f}%"></span></span>'
            f'<span class="bar-value">{n}</span></li>' for m, (n, v) in sorted(por.items(), key=lambda x: -x[1][0]))
        linhas = []
        for a in range(ano - 5, ano + 1):
            ls = [l for l in self.L if l["ano"] == a]
            cs = [c for c in self.C if c["ano"] == a]
            d = sum(1 for l in ls if l["grupo"] == "direta")
            linhas.append(f'<tr><td>{a}{" (até hoje)" if a == ano else ""}</td><td class="n">{milhar(len(ls))}</td><td class="n">{pct(100 * d / max(len(ls), 1))}</td>'
                          f'<td class="n">{milhar(len(cs))}</td><td class="n">{reais_curto(sum(c["valor_atual"] for c in cs))}</td></tr>')
        return f"""
<section id="resumo" aria-labelledby="h-resumo">
  <header><p class="label">1 · Resumo</p><h2 id="h-resumo">O que o município compra</h2></header>
  <div class="kpis">{kpi_html}</div>
  <div class="duas">
    <div class="grafico"><h3 class="sub">Processos de {ano} por modalidade</h3>
      <ul class="bars" aria-label="Processos de compra de {ano} por modalidade, do mais usado ao menos usado">{barras}</ul>
      <div class="tip" id="tip" role="tooltip" hidden></div></div>
    <div><h3 class="sub">Ano a ano</h3><div class="table-scroll solta"><table>
      <thead><tr><th>Ano</th><th class="n">Processos</th><th class="n">Sem licitação</th><th class="n">Contratos</th><th class="n">Valor contratado</th></tr></thead>
      <tbody>{"".join(linhas)}</tbody></table></div></div>
  </div>
  {self.fonte_lc_html()}
</section>"""

    def secao_como(self):
        cartoes = [
            ("Licitação", "A regra", "Várias empresas disputam e vence a melhor proposta. Hoje, o mais comum é o pregão eletrônico.", ["l14133-28"]),
            ("Dispensa", "Exceção prevista em lei", "A Prefeitura contrata sem licitação, quando o valor é baixo ou em casos que a lei lista.", ["l14133-75", "d12807", "l14133-75-3"]),
            ("Inexigibilidade", "Quando não há disputa possível", "Só um fornecedor pode atender, por exemplo um produto exclusivo.", ["l14133-74"]),
            ("Aditivos", "Mudanças no contrato", "Prazo, valor e quantidade podem mudar depois da assinatura, dentro de limites.", ["l14133-125", "l8666-65-1"]),
            ("Publicação", "Sem publicação, o contrato não vale", "Mostardas já publica no Portal Nacional de Contratações Públicas (PNCP), antes do prazo obrigatório.", ["l14133-94", "l14133-176"]),
        ]
        itens = "".join(f'<li><h3>{esc(t)}</h3><p class="quando">{esc(q)}</p><p>{esc(d)}</p>{self.porque(n)}</li>' for t, q, d, n in cartoes)
        return f"""
<section id="como-compra" aria-labelledby="h-como">
  <header><p class="label">2 · Como a Prefeitura compra</p><h2 id="h-como">As regras de cada tipo de compra</h2></header>
  <ul class="acoes">{itens}</ul>
</section>"""

    def secao_acompanhar(self):
        ano = self.hoje.year
        unico = sorted((l for l in self.L if l["ano"] >= ano - 1 and l["grupo"] == "competitiva" and l["participantes"] == 1 and l["situacao"] == "Concluída"),
                       key=lambda l: -(self.valor_lic(l)[0] or 0))
        acima = sorted((c for c in self.C if c["valor_inicial"] > 0 and c["acrescimo_quantidade"] / c["valor_inicial"] > 0.25),
                       key=lambda c: -c["acrescimo_quantidade"] / c["valor_inicial"])
        limite = (self.hoje + dt.timedelta(days=60)).isoformat()
        vencendo = sorted((c for c in self.C if c["fim"] and self.hoje_iso <= c["fim"] <= limite), key=lambda c: -c["valor_atual"])
        forn = collections.defaultdict(lambda: {"nome": "", "doc": None, "valor": 0.0, "n": 0})
        for c in self.C:
            if c["ano"] >= ano - 1 and c["fornecedor"]:
                k = (c["fornecedor"]["nome"], c["fornecedor"].get("doc"))
                forn[k]["nome"], forn[k]["doc"] = k
                forn[k]["valor"] += c["valor_atual"]
                forn[k]["n"] += 1
        top = sorted(forn.values(), key=lambda f: -f["valor"])[:10]
        t_unico = "".join(f'<tr><td>{esc(l["modalidade"])} {esc(l["numero"])}</td><td>{esc(l["objeto"][:140])}</td><td class="n">R$ {milhar(self.valor_lic(l)[0] or 0, 2)}</td><td>{esc(self.vencedores(l))}</td></tr>' for l in unico[:10])
        t_acima = "".join(f'<tr><td>{esc(c["numero"])}</td><td>{esc(c["objeto"][:140])}</td><td class="n">R$ {milhar(c["valor_inicial"], 2)}</td><td class="n">R$ {milhar(c["acrescimo_quantidade"], 2)}</td><td class="n">{pct(100 * c["acrescimo_quantidade"] / c["valor_inicial"])}</td></tr>' for c in acima[:12])
        t_venc = "".join(f'<tr><td>{esc(c["numero"])}</td><td>{esc(c["objeto"][:140])}</td><td>{esc((c["fornecedor"] or {}).get("nome", "—"))}</td><td class="n">R$ {milhar(c["valor_atual"], 2)}</td><td>{br_data(c["fim"])}</td></tr>' for c in vencendo[:12])
        hoje_menos = f"{ano - 1}-01-01"
        nao_ativas = []
        recentes = []
        pessoas = collections.defaultdict(set)
        for k, e in self.E.items():
            cs = self.cont_por_cnpj.get(k, [])
            for s in e.get("socios", []):
                if s["tipo"] == "PF":
                    pessoas[(s["nome"], s.get("doc"))].add(k)
            if not cs:
                continue
            ultimo = max((c["assinatura"] or "" for c in cs), default="")
            if e.get("situacao") not in (None, "ATIVA") and ultimo >= hoje_menos:
                nao_ativas.append((e, k, ultimo))
            prim = min((c["assinatura"] for c in cs if c["assinatura"]), default=None)
            if prim and prim >= "2021-01-01" and e.get("abertura"):
                dias = (dt.date.fromisoformat(prim) - dt.date.fromisoformat(e["abertura"])).days
                if 0 <= dias < 180:
                    recentes.append((e, k, prim, dias, sum(c["valor_atual"] for c in cs)))
        recentes.sort(key=lambda x: -x[4])
        multi = sorted(((p, ks) for p, ks in pessoas.items() if len(ks) > 1),
                       key=lambda x: (-len(x[1]), -sum(c["valor_atual"] for k in x[1] for c in self.cont_por_cnpj.get(k, []))))
        cnpj_fmt = lambda k: f"{k[:2]}.{k[2:5]}.{k[5:8]}/{k[8:12]}-{k[12:]}"
        t_inativas = "".join(f'<tr><td>{esc(e["razao_social"])}<br><span class="label">{cnpj_fmt(k)}</span></td><td>{esc(e["situacao"].title())}'
                             f'{" desde " + br_data(e["data_situacao"]) if e.get("data_situacao") else ""}</td><td>{br_data(u)}</td></tr>' for e, k, u in nao_ativas)
        t_recentes = "".join(f'<tr><td>{esc(e["razao_social"])}<br><span class="label">{cnpj_fmt(k)}</span></td><td>{br_data(e["abertura"])}</td>'
                             f'<td>{br_data(p)}</td><td class="n">{d}</td><td class="n">R$ {milhar(v, 2)}</td></tr>' for e, k, p, d, v in recentes[:12])
        t_multi = "".join(f'<tr><td>{esc(n)}<br><span class="label">{esc(doc or "")}</span></td><td>{esc("; ".join(self.E[k]["razao_social"] for k in sorted(ks)))}</td>'
                          f'<td class="n">R$ {milhar(sum(c["valor_atual"] for k in ks for c in self.cont_por_cnpj.get(k, [])), 2)}</td></tr>' for (n, doc), ks in multi[:15])
        t_top = "".join(f'<tr><td>{esc(f["nome"])}</td><td>{esc(f["doc"] or "—")}</td><td class="n">{f["n"]}</td><td class="n">R$ {milhar(f["valor"], 2)}</td></tr>' for f in top)

        def bloco(titulo, intro, cab, linhas, porque, vazio):
            corpo = (f'<div class="table-scroll solta"><table><thead><tr>{"".join(f"<th>{h}</th>" for h in cab)}</tr></thead><tbody>{linhas}</tbody></table></div>'
                     if linhas else f'<p class="fora">{esc(vazio)}</p>')
            return f'<div class="nota"><h3>{esc(titulo)}</h3><p>{esc(intro)}</p>{corpo}{porque}</div>'
        return f"""
<section id="acompanhar" aria-labelledby="h-acomp">
  <header><p class="label">3 · Pontos para acompanhar</p><h2 id="h-acomp">Pontos para acompanhar</h2>
    <div class="prose"><p>Nada aqui é acusação. São situações que merecem uma pergunta, porque muitas vezes têm explicação. A pergunta pode ir pelo e-SIC, como mostra o guia.</p></div></header>
  {bloco(f"Licitações com um só participante ({ano - 1}–{ano})", f"{len(unico)} licitações concluídas tiveram uma única empresa na disputa. Sem concorrência, não há comparação de preços. Às vezes o mercado é pequeno ou a exigência é técnica.",
         ["Processo", "Objeto", "Valor", "Quem ganhou"], t_unico, "", "Nenhuma licitação concluída com um só participante no período.")}
  {bloco("Contratos com acréscimo de quantidade acima de 25%", f"{len(acima)} contratos, desde 2016, tiveram acréscimos de quantidade maiores que 25% do valor inicial. Renovações, reajustes e reequilíbrios não entram nessa conta.",
         ["Contrato", "Objeto", "Valor inicial", "Acréscimo", "% do inicial"], t_acima, self.porque(["l14133-125", "l8666-65-1"]), "Nenhum contrato acima do limite.")}
  {bloco("Contratos que terminam nos próximos 60 dias", f"{len(vencendo)} contratos terminam até {br_data(limite)}. É a hora de acompanhar se haverá renovação ou nova licitação.",
         ["Contrato", "Objeto", "Fornecedor", "Valor", "Termina em"], t_venc, "", "Nenhum contrato termina nos próximos 60 dias.")}
  {bloco(f"Quem mais recebeu em contratos ({ano - 1}–{ano})", "Valor contratado, com aditivos. Valor contratado não é o mesmo que valor pago; os pagamentos estão mais abaixo.",
         ["Fornecedor", "CNPJ ou CPF", "Contratos", "Valor"], t_top, "", "Nenhum contrato no período.")}
  {bloco(f"Empresas com contrato desde {ano - 1} que hoje não estão ativas", f"{len(nao_ativas)} empresas assinaram contrato desde {ano - 1} e hoje aparecem como baixadas, inaptas ou suspensas na Receita. Vale perguntar se estavam ativas na assinatura e quem cumpre o contrato.",
         ["Empresa", "Situação na Receita", "Último contrato"], t_inativas, "", "Todas as empresas com contrato recente estão ativas.") if self.E else ""}
  {bloco("Empresas abertas menos de seis meses antes do primeiro contrato", f"{len(recentes)} empresas, desde 2021, começaram a vender para o município pouco depois de abertas. Empresa nova não é problema por si só, mas vale saber quem está por trás e se tinha experiência no serviço.",
         ["Empresa", "Aberta em", "Primeiro contrato", "Dias", "Total contratado"], t_recentes, "", "Nenhuma empresa nessa situação.") if self.E else ""}
  {bloco("Pessoas sócias de mais de uma empresa fornecedora", f"{len(multi)} pessoas são sócias de duas ou mais empresas que vendem para o município. Ter sócios em comum não é proibido, mas, se essas empresas disputam a mesma licitação, a concorrência pode não ser real.",
         ["Pessoa", "Empresas", "Total contratado"], t_multi, "", "Nenhuma pessoa nessa situação.") if self.E else ""}
  {self.fonte_lc_html()}{self.fonte_emp_html()}
</section>"""

    def fonte_emp_html(self):
        if not self.fonte_emp:
            return ""
        return (f'<p class="source">Empresas e sócios: <a href="{esc(self.fonte_emp["url"])}">{esc(self.fonte_emp["titulo"])}</a>, '
                f'consultado em {br_data(self.fonte_emp["consultado_em"])}. A Receita publica o CPF dos sócios já mascarado.</p>')

    def secao_empresas(self):
        if not self.E:
            return ""
        com_socios = sum(1 for e in self.E.values() if e.get("socios"))
        top = sorted(self.E.items(), key=lambda kv: -sum(c["valor_atual"] for c in self.cont_por_cnpj.get(kv[0], [])))[:8]
        cards = "".join(self.cartao_emp(k, e) for k, e in top)
        return f"""
<section id="empresas" aria-labelledby="h-emp">
  <header><p class="label">6 · Empresas e sócios</p><h2 id="h-emp">Quem está por trás de cada empresa</h2>
    <div class="prose"><p>{milhar(len(self.E))} empresas venderam para o município. Para {milhar(com_socios)} delas, a Receita informa o quadro de sócios. As outras são, em geral, microempreendedores individuais, cujo dono é a própria pessoa que dá nome à empresa.</p>
    <p>Aparecem os sócios, os administradores e os representantes legais. Endereço, telefone e e-mail ficam de fora, porque no microempreendedor costumam ser os da pessoa.</p></div></header>
  <div class="filtros" hidden>
    <label class="busca" for="e-q">Buscar empresa, CNPJ ou nome de sócio<input id="e-q" type="search" placeholder="Ex.: nome de uma pessoa ou de uma empresa"></label>
    <label for="e-sit">Situação na Receita<select id="e-sit"><option value="">Todas</option><option>ATIVA</option><option>BAIXADA</option><option>INAPTA</option><option>SUSPENSA</option></select></label>
  </div>
  <p class="conta" id="e-conta" aria-live="polite">As empresas que mais contrataram com o município. A busca completa está carregando…</p>
  <ul class="resultados" id="e-res">{cards}</ul>
  <button class="mais" id="e-mais" type="button" hidden>Mostrar mais</button>
  {self.fonte_emp_html()}
</section>"""

    def cartao_emp(self, k, e):
        cs = self.cont_por_cnpj.get(k, [])
        total = sum(c["valor_atual"] for c in cs)
        socios = "".join(f'<li><b>{esc(s["nome"])}</b> · {esc(s.get("qualificacao") or "")}{" desde " + br_data(s["entrada"]) if s.get("entrada") else ""}'
                         f'{" · representante: " + esc(s["representante"]["nome"]) if s.get("representante") else ""}</li>' for s in e.get("socios", []))
        socios_html = f'<ul class="socios">{socios}</ul>' if socios else '<p class="meta">A Receita não informa quadro de sócios para esta empresa.</p>'
        ativa = e.get("situacao") == "ATIVA"
        return (f'<li class="res"><div class="topo"><span class="id">{k[:2]}.{k[2:5]}.{k[5:8]}/{k[8:12]}-{k[12:]}{" · MEI" if e.get("mei") else ""}</span>'
                f'<span class="chip {"ok" if ativa else "falta"}">{esc((e.get("situacao") or "Situação não informada").title())}</span></div>'
                f'<p class="obj">{esc(e["razao_social"])}</p><p class="meta"><span>Aberta em <b>{br_data(e["abertura"]) if e.get("abertura") else "—"}</b></span>'
                f'<span>{esc(e.get("atividade") or "")}</span><span>{esc(e.get("municipio") or "")}{"/" + esc(e["uf"]) if e.get("uf") else ""}</span></p>'
                f'<p class="meta"><span>Contratos com o município: <b>{len(cs)}</b></span><span>Total: <b>R$ {milhar(total, 2)}</b></span></p>{socios_html}</li>')

    def secao_busca(self, tipo):
        if tipo == "lic":
            recentes = "".join(self.cartao_lic(l) for l in self.L[:10])
            situacoes = sorted({l["situacao"] for l in self.L})
            filtros = f"""<div class="filtros" hidden>
      <label class="busca" for="l-q">Buscar no objeto, número ou vencedor<input id="l-q" type="search" placeholder="Ex.: merenda, asfalto, 66/2026"></label>
      <label for="l-ano">Ano<select id="l-ano"><option value="">Todos</option></select></label>
      <label for="l-grupo">Tipo<select id="l-grupo"><option value="">Todos</option><option value="competitiva">Com disputa (licitação)</option><option value="direta">Sem licitação</option><option value="chamamento">Chamamento</option><option value="alienacao">Leilão</option></select></label>
      <label for="l-sit">Situação<select id="l-sit"><option value="">Todas</option>{"".join(f'<option>{esc(s)}</option>' for s in situacoes)}</select></label>
      <label for="l-org">Órgão<select id="l-org"><option value="">Todos</option><option value="0">Prefeitura</option><option value="1">Câmara</option></select></label>
      <label for="l-ordem">Ordenar<select id="l-ordem"><option value="data">Mais recentes</option><option value="valor">Maior valor</option></select></label>
    </div>"""
            return f"""
<section id="licitacoes" aria-labelledby="h-lic">
  <header><p class="label">4 · Buscar licitações</p><h2 id="h-lic">Todas as licitações e compras sem licitação</h2>
    <div class="prose"><p>{milhar(len(self.L))} processos desde 2006, da Prefeitura e da Câmara. Cada um tem o link para os documentos oficiais no TCE-RS.</p></div></header>
  {filtros}
  <p class="conta" id="l-conta" aria-live="polite">As 10 publicações mais recentes. A busca completa está carregando…</p>
  <ul class="resultados" id="l-res">{recentes}</ul>
  <button class="mais" id="l-mais" type="button" hidden>Mostrar mais</button>
</section>"""
        recentes = "".join(self.cartao_con(c) for c in self.C[:10])
        filtros = """<div class="filtros" hidden>
      <label class="busca" for="c-q">Buscar no objeto, fornecedor ou número<input id="c-q" type="search" placeholder="Ex.: transporte escolar, nome da empresa"></label>
      <label for="c-ano">Ano<select id="c-ano"><option value="">Todos</option></select></label>
      <label for="c-org">Órgão<select id="c-org"><option value="">Todos</option><option value="0">Prefeitura</option><option value="1">Câmara</option></select></label>
      <label for="c-ordem">Ordenar<select id="c-ordem"><option value="data">Mais recentes</option><option value="valor">Maior valor</option></select></label>
      <label class="marca" for="c-vig"><input id="c-vig" type="checkbox"> Só os que estão em vigor</label>
    </div>"""
        return f"""
<section id="contratos" aria-labelledby="h-con">
  <header><p class="label">5 · Buscar contratos</p><h2 id="h-con">Todos os contratos e atas</h2>
    <div class="prose"><p>{milhar(len(self.C))} contratos e atas de registro de preços, com fornecedor, valor, aditivos e vigência.</p></div></header>
  {filtros}
  <p class="conta" id="c-conta" aria-live="polite">Os 10 contratos assinados mais recentemente. A busca completa está carregando…</p>
  <ul class="resultados" id="c-res">{recentes}</ul>
  <button class="mais" id="c-mais" type="button" hidden>Mostrar mais</button>
</section>"""

    def bloco_pagamentos(self, r):
        p, cam = r["totais"]["prefeitura"], r["totais"].get("camara", {})
        completo = r["periodo"]["fim"] and r["periodo"]["fim"][5:] >= "12-01"
        titulo = f'{r["ano"]}' + ("" if completo else f' (até {br_data(r["periodo"]["fim"])})')
        folha = "".join(f'<tr><td>{esc(f["nome"])}</td><td class="n">R$ {milhar(f["pago"], 2)}</td></tr>' for f in r["folha"])
        cred = "".join(f'<tr><td>{esc(c["nome"])}<br><span class="label">{esc(", ".join(c["funcoes"]))}</span></td><td>{esc(c["cnpj"])}</td><td class="n">R$ {milhar(c["pago"], 2)}</td></tr>' for c in r["credores"][:15])
        pf = "".join(f'<tr><td>{esc(x["tipo"])}</td><td class="n">{milhar(x["n"])}</td><td class="n">R$ {milhar(x["pago"], 2)}</td></tr>' for x in r["pessoas_fisicas"][:8])
        f = r["fonte"]
        return f"""<div class="nota"><h3>{esc(titulo)}</h3>
      <p>A Prefeitura pagou <strong>R$ {milhar(p.get("pago", 0), 2)}</strong> e a Câmara, <strong>R$ {milhar(cam.get("pago", 0), 2)}</strong>.</p>
      <h4 class="label">Folha e encargos</h4><div class="table-scroll solta"><table><tbody>{folha}</tbody></table></div>
      <h4 class="label">Empresas e órgãos que mais receberam</h4><div class="table-scroll solta"><table><thead><tr><th>Quem recebeu</th><th>CNPJ</th><th class="n">Pago</th></tr></thead><tbody>{cred}</tbody></table></div>
      <h4 class="label">Pagamentos a pessoas físicas, somados por tipo</h4><div class="table-scroll solta"><table><thead><tr><th>Tipo</th><th class="n">Pagamentos</th><th class="n">Total</th></tr></thead><tbody>{pf}</tbody></table></div>
      <p class="source">Fonte: <a href="{esc(f["url"])}">{esc(f["titulo"])}</a>; arquivo de {br_data(data_http(f["copia"].get("last_modified")) or f["consultado_em"])}.</p></div>"""

    def secao_pagamentos(self):
        if not self.pag:
            return ""
        blocos = "".join(self.bloco_pagamentos(self.pag[a]) for a in sorted(self.pag, reverse=True))
        return f"""
<section id="pagamentos" aria-labelledby="h-pag">
  <header><p class="label">7 · Pagamentos</p><h2 id="h-pag">Quem recebeu dinheiro do município</h2>
    <div class="prose"><p>Os pagamentos incluem restos a pagar de anos anteriores e repasses internos, como ao fundo de previdência dos servidores. Por isso o total é maior que o gasto do ano mostrado no guia.</p>
    <p>Pagamentos a pessoas físicas aparecem somados por tipo, sem nomes. Entre eles há auxílios sociais, e expor quem os recebe seria expor o vizinho.</p></div></header>
  <div class="duas">{blocos}</div>
  <p class="fora"><strong>Por que 2026 só vai até fevereiro:</strong> o município envia esses dados ao TCE-RS a cada dois meses, e o Tribunal ainda não publicou os meses seguintes. O <a href="https://webapp1-mostardas.cidade360.cloud/pronimtb/">Portal da Transparência do município</a> é obrigado a mostrar os pagamentos em tempo real.</p>
  {self.porque(["lrf-48-1-ii"])}
</section>"""

    def secao_fontes(self):
        arqs = "".join(f'<li><a href="{esc(a["url"])}">{esc(a["url"].rsplit("/", 3)[-3])} · {esc(a["url"].rsplit("/", 1)[-1])}</a>'
                       f'<span>Arquivo de {br_data(data_http(a.get("last_modified")) or self.fonte_lc["consultado_em"])} · SHA-256 {esc(a["sha256"][:12])}…</span></li>'
                       for a in self.fonte_lc["copia"]["arquivos"])
        pags = "".join(f'<li><a href="{esc(r["fonte"]["url"])}">{esc(r["fonte"]["titulo"])}</a><span>Dados de {br_data(r["periodo"]["inicio"])} a {br_data(r["periodo"]["fim"])}</span></li>'
                       for _, r in sorted(self.pag.items(), reverse=True))
        return f"""
<section id="fontes" aria-labelledby="h-fontes">
  <header><p class="label">8 · Fontes</p><h2 id="h-fontes">De onde vem cada número</h2>
    <div class="prose"><p>Os coletores baixam os arquivos oficiais, guardam uma cópia com a impressão digital (SHA-256) e só então geram esta página. O LicitaCon é atualizado pelo TCE-RS quase todo dia; os pagamentos, a cada dois meses.</p></div></header>
  <ul class="docs">{arqs}{pags}
    <li><a href="https://pncp.gov.br/app/editais?q=88000922000140">Portal Nacional de Contratações Públicas (PNCP)</a><span>Onde Mostardas (CNPJ 88.000.922/0001-40) publica editais e contratos desde a nova lei.</span></li>
    <li><a href="https://webapp1-mostardas.cidade360.cloud/pronimtb/">Portal da Transparência do município</a><span>Receitas, despesas e compras em tempo real, mantido pela Prefeitura.</span></li>
  </ul>
</section>"""

    # -- base da busca

    def base(self):
        def sufixos(links):
            ls = [x for x in links if x]
            prefixo = os.path.commonprefix(ls) if ls else ""
            return prefixo, [x[len(prefixo):] if x else "" for x in links]
        base_lic, suf_l = sufixos([l["link"] for l in self.L])
        base_con, suf_c = sufixos([c["link"] for c in self.C])
        from coletar_licitacon import MODALIDADES
        lic = []
        for l, s in zip(self.L, suf_l):
            v, tv = self.valor_lic(l)
            cnpjs = [digitos(x["doc"]) for x in l["vencedores"] if x.get("tipo") == "J" and x.get("doc")]
            cnpjs = cnpjs or [digitos(d) for d in self.forn_por_lic.get(l["id"], {}).values() if d and "*" not in d]
            lic.append([ORG_IDX[l["orgao"]], l["mod"], l["numero"], l["ano"], l["objeto"], v, tv, l["situacao"], l["abertura"] or l["homologacao"],
                        l["participantes"], self.vencedores(l) or None, s, [c for c in cnpjs if c in self.E]])
        con = []
        for c, s in zip(self.C, suf_c):
            f = c["fornecedor"] or {}
            con.append([ORG_IDX[c["orgao"]], c["numero"], c["ano"], c["instrumento"], f.get("nome"), f.get("doc"), c["objeto"], c["valor_inicial"],
                        c["valor_atual"], c["aditivos"], c["acrescimo_quantidade"], c["assinatura"], c["fim"], c["mod"], s,
                        digitos(f.get("doc")) if f.get("tipo") == "J" and digitos(f.get("doc")) in self.E else ""])
        emp = {}
        for k, e in self.E.items():
            cs = self.cont_por_cnpj.get(k, [])
            emp[k] = [e["razao_social"], e.get("situacao"), e.get("data_situacao"), e.get("abertura"), e.get("atividade"), e.get("porte"),
                      (e.get("municipio") or "") + ("/" + e["uf"] if e.get("uf") else ""), 1 if e.get("mei") else 0,
                      [[s["nome"], s.get("qualificacao"), s.get("entrada"), s["tipo"], s.get("doc"), (s.get("representante") or {}).get("nome")] for s in e.get("socios", [])],
                      round(sum(c["valor_atual"] for c in cs), 2), len(cs)]
        return {"gerado": self.hoje_iso, "hoje": self.hoje_iso, "org": ORG, "base_lic": base_lic, "base_con": base_con,
                "mods": {k: v[0] for k, v in MODALIDADES.items()}, "grupo": {k: v[1] for k, v in MODALIDADES.items()}, "lic": lic, "con": con, "emp": emp}

    def montar(self):
        secoes = [self.secao_resumo(), self.secao_como(), self.secao_acompanhar(), self.secao_busca("lic"), self.secao_busca("con"),
                  self.secao_empresas(), self.secao_pagamentos(), self.secao_fontes()]
        rodape = (f'    <p><strong>Como esta página é feita.</strong> Gerada em {self.hoje.strftime("%d/%m/%Y")} a partir de {milhar(len(self.L))} processos e '
                  f'{milhar(len(self.C))} contratos do LicitaCon e dos pagamentos de {", ".join(str(a) for a in sorted(self.pag))}. CPF de pessoa física aparece sempre mascarado.</p>\n'
                  '    <p><strong>Achou um erro?</strong> Se um dado parece errado, ele pode ter sido informado errado pelo próprio município. Vale perguntar pelo e-SIC e avisar este projeto.</p>')
        trocas = {"{{estilo}}": (MODELOS / "estilo.css").read_text(encoding="utf-8"), "{{aviso}}": self.aviso(), "{{secoes}}": "\n".join(secoes),
                  "{{rodape}}": rodape, "{{script}}": (MODELOS / "interacao.js").read_text(encoding="utf-8") + "\n" + (MODELOS / "compras.js").read_text(encoding="utf-8")}
        corpo = (MODELOS / "compras.html").read_text(encoding="utf-8")
        for k, v in trocas.items():
            corpo = corpo.replace(k, v)
        return corpo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("saida")
    ap.add_argument("--hoje", default=dt.date.today().isoformat())
    a = ap.parse_args()
    pasta = pathlib.Path(a.saida)
    pasta.mkdir(parents=True, exist_ok=True)
    c = Compras(dt.date.fromisoformat(a.hoje))
    (pasta / "compras.html").write_text(c.montar(), encoding="utf-8")
    base = c.base()
    (pasta / "compras-dados.json").write_text(json.dumps(base, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"ok: compras.html e compras-dados.json ({(pasta / 'compras-dados.json').stat().st_size // 1024} KB) em {pasta}")


if __name__ == "__main__":
    main()
