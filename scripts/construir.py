"""Gera o Guia das Instituições de Mostardas a partir de dados/.

Por que um build em vez de HTML escrito à mão: os dados mudam em ritmos diferentes e a
página é só uma visão deles. O build valida tudo antes (ARQUITETURA.md, decisão 13) e
calcula o frescor de cada informação (decisão 7). Havendo erro, nada é gerado.

Uso: python3 scripts/construir.py SAIDA.html [--hoje AAAA-MM-DD]
"""
import argparse
import datetime as dt
import html
import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
MODELOS = RAIZ / "modelos"

TIPOS_FONTE = {"ato-oficial", "dados-oficiais", "site-oficial", "imprensa", "resposta-lai"}
# Prazo de validade, em dias, de cada tipo de dado (ARQUITETURA.md, decisão 7).
PRAZO = {"ocupacao": 30, "contato": 90, "conselho": 90, "orgao": 180, "financas": 60, "evento": 90}
CAMPOS_COM_FONTE = ("o_que_faz", "composicao", "reunioes", "lei_criacao", "evidencia", "servicos", "gasto_pessoal",
                    "estrutura", "nota_titular")
ROTULO_FUNCAO = {"Legislativa": "Câmara de Vereadores", "Desporto e Lazer": "Esporte e lazer"}
TIPO_ORGAO = {
    "executivo": "Poder Executivo", "gabinete": "Gabinete", "secretaria": "Secretaria",
    "legislativo": "Poder Legislativo", "conselho": "Conselho municipal", "conselho-tutelar": "Conselho Tutelar",
}
NAO_ACHADO = "não encontrado nas fontes consultadas"


def esc(x):
    return html.escape(str(x), quote=True)


def ler(nome, padrao=None):
    caminho = DADOS / nome
    if not caminho.exists():
        if padrao is not None:
            return padrao
        raise SystemExit(f"Arquivo obrigatório ausente: dados/{nome}")
    return json.loads(caminho.read_text(encoding="utf-8"))


def indexar(lista, nome, erros):
    idx = {}
    for item in lista:
        chave = item.get("id")
        if not chave:
            erros.append(f"{nome}: registro sem id")
        elif chave in idx:
            erros.append(f"{nome}: id repetido '{chave}'")
        else:
            idx[chave] = item
    return idx


# ---------------------------------------------------------------- carga e validação

def carregar(hoje):
    erros = []
    d = {
        "municipio": ler("municipio.json"),
        "fontes": indexar(ler("fontes.json"), "fontes", erros),
        "normas": indexar(ler("normas.json"), "normas", erros),
        "orgaos": indexar(ler("orgaos.json"), "orgaos", erros),
        "provimentos": indexar(ler("provimentos.json"), "provimentos", erros),
        "pessoas": indexar(ler("pessoas.json", []), "pessoas", erros),
        "ocupacoes": ler("ocupacoes.json", []),
        "contatos": ler("contatos.json", []),
        "eventos": indexar(ler("eventos.json", []), "eventos", erros),
        "lacunas": indexar(ler("lacunas.json", []), "lacunas", erros),
        "financas": [json.loads(p.read_text(encoding="utf-8")) for p in sorted((DADOS / "financas").glob("*.json"))],
    }
    cargos = ler("cargos.json")
    d["grupos"] = indexar(cargos["grupos"], "grupos", erros)
    d["cargos"] = indexar(cargos["cargos"], "cargos", erros)

    F, N, O = d["fontes"], d["normas"], d["orgaos"]

    def data_ok(valor, onde):
        if not valor:
            erros.append(f"{onde}: falta data")
            return None
        try:
            x = dt.date.fromisoformat(valor)
        except ValueError:
            erros.append(f"{onde}: data inválida '{valor}'")
            return None
        if x > hoje:
            erros.append(f"{onde}: data no futuro '{valor}'")
        return x

    def fonte_ok(fid, onde):
        if not fid:
            erros.append(f"{onde}: sem fonte")
        elif fid not in F:
            erros.append(f"{onde}: fonte inexistente '{fid}'")

    def normas_ok(ids, onde, obrigatoria=False):
        if obrigatoria and not ids:
            erros.append(f"{onde}: sem base legal")
        for n in ids or []:
            if n not in N:
                erros.append(f"{onde}: norma inexistente '{n}'")

    def campo_ok(campo, onde):
        if not isinstance(campo, dict) or not campo.get("texto"):
            erros.append(f"{onde}: falta texto")
            return
        if campo.get("normas"):
            normas_ok(campo["normas"], onde)
        else:
            fonte_ok(campo.get("fonte"), onde)

    for f in F.values():
        onde = f"fonte {f['id']}"
        if f.get("tipo") not in TIPOS_FONTE:
            erros.append(f"{onde}: tipo '{f.get('tipo')}' fora de {sorted(TIPOS_FONTE)}")
        if not f.get("url") or not f.get("titulo"):
            erros.append(f"{onde}: falta url ou título")
        data_ok(f.get("consultado_em"), onde)
    for n in N.values():
        if not (n.get("referencia") and n.get("url") and n.get("explica")):
            erros.append(f"norma {n['id']}: falta referência, url ou explicação")
    for p in d["provimentos"].values():
        normas_ok(p.get("normas"), f"provimento {p['id']}")
    for o in O.values():
        onde = f"órgão {o['id']}"
        if o.get("tipo") not in TIPO_ORGAO:
            erros.append(f"{onde}: tipo desconhecido '{o.get('tipo')}'")
        if o.get("pai") and o["pai"] not in O:
            erros.append(f"{onde}: pai inexistente '{o['pai']}'")
        for nome in CAMPOS_COM_FONTE:
            if nome in o:
                campo_ok(o[nome], f"{onde}.{nome}")
        if "evidencia" in o:
            data_ok(o["evidencia"].get("data"), f"{onde}.evidencia")
        if "por_que" in o:
            blocos = o["por_que"] if isinstance(o["por_que"], list) else [o["por_que"]]
            for b in blocos:
                normas_ok(b.get("normas"), f"{onde}.por_que", obrigatoria=True)
    for g in d["grupos"].values():
        normas_ok(g.get("por_que", {}).get("normas"), f"grupo {g['id']}")
    for c in d["cargos"].values():
        onde = f"cargo {c['id']}"
        if c.get("orgao") is not None and c["orgao"] not in O:
            erros.append(f"{onde}: órgão inexistente '{c['orgao']}'")
        if c.get("grupo") and c["grupo"] not in d["grupos"]:
            erros.append(f"{onde}: grupo inexistente '{c['grupo']}'")
        if c.get("provimento") not in d["provimentos"]:
            erros.append(f"{onde}: provimento inexistente '{c.get('provimento')}'")
        if "remuneracao" in c:
            campo_ok(c["remuneracao"], f"{onde}.remuneracao")

    ids_ocup = set()
    for oc in d["ocupacoes"]:
        onde = f"ocupação {oc.get('id')}"
        if oc.get("id") in ids_ocup:
            erros.append(f"{onde}: id repetido")
        ids_ocup.add(oc.get("id"))
        if oc.get("cargo") not in d["cargos"]:
            erros.append(f"{onde}: cargo inexistente '{oc.get('cargo')}'")
        if oc.get("pessoa") not in d["pessoas"]:
            erros.append(f"{onde}: pessoa inexistente '{oc.get('pessoa')}'")
        # Data desconhecida é permitida, mas precisa ser dita: sem data, exige uma nota (decisão 4).
        ini = data_ok(oc["valido_desde"], onde + ".valido_desde") if oc.get("valido_desde") else None
        if not oc.get("valido_desde") and not oc.get("nota"):
            erros.append(f"{onde}: sem valido_desde e sem nota explicando por quê")
        if oc.get("valido_ate"):
            fim = dt.date.fromisoformat(oc["valido_ate"])
            if ini and fim < ini:
                erros.append(f"{onde}: termina antes de começar")
        if oc.get("encerrado") and not oc.get("valido_ate") and not oc.get("nota"):
            erros.append(f"{onde}: encerrado sem data e sem nota explicando por quê")
        fonte_ok(oc.get("fonte"), onde)
        data_ok(oc.get("conferido_em"), onde + ".conferido_em")
    # Nenhum cargo pode ter mais ocupantes simultâneos do que vagas (decisões 3 e 13).
    # Registro encerrado sem data de fim não entra nas datas posteriores ao seu início.
    hoje_iso = hoje.isoformat()
    for c in d["cargos"].values():
        vagas = c.get("vagas")
        if not isinstance(vagas, int):
            continue
        todos = [o for o in d["ocupacoes"] if o.get("cargo") == c["id"]]
        datados = [o for o in todos if o.get("valido_desde")]

        def vale_em(x, t):
            if x["valido_desde"] > t:
                return False
            if x.get("valido_ate"):
                return x["valido_ate"] >= t
            return not x.get("encerrado") or x["valido_desde"] == t
        for o in datados:
            t = o["valido_desde"]
            simultaneos = [x for x in datados if vale_em(x, t)]
            if len(simultaneos) > vagas:
                erros.append(f"cargo {c['id']}: {len(simultaneos)} ocupantes em {t} para {vagas} vaga(s)")
                break
        hoje_ativos = [o for o in todos if not o.get("encerrado") and (not o.get("valido_desde") or o["valido_desde"] <= hoje_iso)
                       and (not o.get("valido_ate") or o["valido_ate"] >= hoje_iso)]
        if len(hoje_ativos) > vagas:
            erros.append(f"cargo {c['id']}: {len(hoje_ativos)} ocupantes hoje para {vagas} vaga(s); feche o registro de quem saiu")
    for ct in d["contatos"]:
        onde = f"contato de {ct.get('orgao')}"
        if ct.get("orgao") not in O:
            erros.append(f"{onde}: órgão inexistente")
        fonte_ok(ct.get("fonte"), onde)
        data_ok(ct.get("conferido_em"), onde + ".conferido_em")
        for canal in ct.get("canais", []):
            fonte_ok(canal.get("fonte") or ct.get("fonte"), f"{onde}.canal {canal.get('tipo')}")
    for ev in d["eventos"].values():
        onde = f"evento {ev['id']}"
        if ev.get("orgao") and ev["orgao"] not in O:
            erros.append(f"{onde}: órgão inexistente")
        if ev.get("normas"):
            normas_ok(ev["normas"], onde)
        else:
            fonte_ok(ev.get("fonte"), onde)
    for la in d["lacunas"].values():
        if la.get("destino") not in ("prefeitura", "camara"):
            erros.append(f"lacuna {la['id']}: destino deve ser prefeitura ou camara")
        if not la.get("pergunta"):
            erros.append(f"lacuna {la['id']}: falta a pergunta")
    for fin in d["financas"]:
        fonte_ok(fin.get("fonte"), f"finanças {fin.get('id')}")
        data_ok(fin.get("conferido_em"), f"finanças {fin.get('id')}")
        fonte_ok(fin.get("natureza_destaques", {}).get("fonte"), f"finanças {fin.get('id')}.natureza")
    for pop in d["municipio"].get("populacao", []):
        fonte_ok(pop.get("fonte"), f"população {pop.get('ano')}")

    if erros:
        print("O build parou. Corrija os dados:", file=sys.stderr)
        for e in erros:
            print("  - " + e, file=sys.stderr)
        sys.exit(1)
    return d


# ---------------------------------------------------------------- formatação

def br_data(s):
    return dt.date.fromisoformat(s).strftime("%d/%m/%Y")


def milhar(v, casas=0):
    s = f"{v:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def reais_curto(v):
    if v >= 1e6:
        return "R$ " + f"{v / 1e6:.1f}".replace(".", ",") + " mi"
    if v >= 1e3:
        return f"R$ {v / 1e3:.0f} mil"
    return f"R$ {v:.0f}"


def pct(x):
    return "menos de 0,1%" if x < 0.1 else f"{x:.1f}".replace(".", ",") + "%"


class Pagina:
    def __init__(self, d, hoje):
        self.d, self.hoje = d, hoje
        self.hoje_iso = hoje.isoformat()
        self.fontes_usadas = set()

    # -- peças reutilizadas

    def link_fonte(self, fid):
        self.fontes_usadas.add(fid)
        f = self.d["fontes"][fid]
        return f'<a href="{esc(f["url"])}">{esc(f["titulo"])}</a>'

    def chip_frescor(self, conferido_em, tipo):
        idade = (self.hoje - dt.date.fromisoformat(conferido_em)).days
        if idade > PRAZO[tipo]:
            return f'<span class="chip velho">A conferir: visto há {idade} dias</span>'
        return ""

    def rodape_fonte(self, fontes, conferidos=()):
        """fontes: ids; conferidos: pares (data, tipo) dos dados voláteis da ficha."""
        ids = [i for i in dict.fromkeys(fontes) if i]
        if not ids:
            return ""
        txt = ("Fonte: " if len(ids) == 1 else "Fontes: ") + "; ".join(self.link_fonte(i) for i in ids)
        datas = [c for c in conferidos if c[0]]
        chips = ""
        if datas:
            mais_antiga = min(c[0] for c in datas)
            txt += f" · conferido em {br_data(mais_antiga)}"
            chips = "".join(self.chip_frescor(c[0], c[1]) for c in datas)
        return f'<p class="source">{txt}</p>{chips}'

    def porque(self, por_que, extra_normas=()):
        if isinstance(por_que, list):
            return "".join(self.porque(b) for b in por_que)
        if not por_que and not extra_normas:
            return ""
        por_que = por_que or {}
        normas = [self.d["normas"][n] for n in dict.fromkeys(list(por_que.get("normas", [])) + list(extra_normas))]
        texto = por_que.get("texto") or " ".join(n["explica"] for n in normas)
        refs = " · ".join(f'<a href="{esc(n["url"])}">{esc(n["referencia"])}</a>' for n in normas)
        return (f'<div class="porque"><p><b>Por quê:</b> {esc(texto)}</p>'
                + (f'<p class="ref">Base legal: {refs}</p>' if refs else "") + "</div>")

    def falta(self, txt=NAO_ACHADO):
        return f'<span class="falta-txt">{esc(txt)}</span>'

    def ativas(self, cargo_id):
        return [o for o in self.d["ocupacoes"] if o["cargo"] == cargo_id and not o.get("encerrado")
                and (not o.get("valido_desde") or o["valido_desde"] <= self.hoje_iso)
                and (not o.get("valido_ate") or o["valido_ate"] >= self.hoje_iso)]

    def encerradas(self, cargo_id):
        return [o for o in self.d["ocupacoes"] if o["cargo"] == cargo_id
                and (o.get("encerrado") or (o.get("valido_ate") and o["valido_ate"] < self.hoje_iso))]

    def contato(self, orgao_id):
        cands = [c for c in self.d["contatos"] if c["orgao"] == orgao_id
                 and (not c.get("valido_ate") or c["valido_ate"] >= self.hoje_iso)]
        return max(cands, key=lambda c: c.get("valido_desde", ""), default=None)

    def pessoa(self, pid):
        return self.d["pessoas"][pid]["nome_publico"]

    def financa(self):
        return max(self.d["financas"], key=lambda f: f["exercicio"]) if self.d["financas"] else None

    def populacao(self, ano=None, tipo=None):
        pops = [p for p in self.d["municipio"]["populacao"] if (tipo is None or p["tipo"] == tipo)]
        if ano is not None:
            exatas = [p for p in pops if p["ano"] == ano]
            if exatas:
                return exatas[0]
        return max(pops, key=lambda p: p["ano"])

    def campo(self, o, nome):
        c = o.get(nome)
        return esc(c["texto"]) if c else self.falta()

    def dl(self, linhas):
        return "<dl>" + "".join(f"<div><dt>{esc(k)}</dt><dd>{v}</dd></div>" for k, v in linhas) + "</dl>"

    def linhas_contato(self, ct):
        if not ct:
            return [("Onde fica e contato", self.falta())]
        tel = esc(ct["telefone"]) if ct.get("telefone") else self.falta()
        email = esc(ct["email"]) if ct.get("email") else self.falta()
        return [
            ("Onde fica", esc(ct["endereco"]) if ct.get("endereco") else self.falta()),
            ("Telefone · e-mail", f"{tel} · {email}"),
            ("Horário", esc(ct["horario"]) if ct.get("horario") else self.falta()),
        ]

    # -- seções

    def numeros_cidade(self):
        m = self.d["municipio"]
        censo = self.populacao(tipo="censo")
        vereador = self.d["cargos"].get("vereador")
        n_orgaos = sum(1 for o in self.d["orgaos"].values() if o.get("pai") == "prefeitura")
        fin = self.financa()
        itens = [("População", milhar(censo["valor"])), ("Área", milhar(m["area_km2"]["valor"]) + " km²"),
                 ("Vereadores", str(vereador["vagas"]) if vereador else "—"), ("Órgãos da Prefeitura", str(n_orgaos))]
        if fin:
            itens.append((f"Gasto em {fin['exercicio']}",
                          "R$ " + f"{fin['total_sem_intra']['liquidado'] / 1e6:.1f}".replace(".", ",") + " milhões"))
        dl = "".join(f"<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in itens)
        fontes = [censo["fonte"], m["area_km2"]["fonte"]] + ([fin["fonte"]] if fin else [])
        return (f'    <dl class="city">{dl}</dl>\n'
                f'    <p class="source">População: censo {censo["ano"]}. '
                + "; ".join(self.link_fonte(f) for f in dict.fromkeys(fontes)) + ".</p>")

    def secao_como_funciona(self):
        cards = []
        for g in sorted(self.d["grupos"].values(), key=lambda g: g["ordem"]):
            membros = [c for c in self.d["cargos"].values() if c.get("grupo") == g["id"]]
            como = g["como"]
            if g.get("contar") == "pessoas":
                # Conta quem ocupa de fato: uma pessoa pode responder por mais de uma pasta.
                pessoas = {oc["pessoa"] for c in membros for oc in self.ativas(c["id"])}
                numero = str(len(pessoas))
                como = f"{como} · {len(pessoas)} pessoas para {len(membros)} secretarias"
            else:
                numero = g.get("numero_rotulo") or str(sum(c["vagas"] for c in membros if isinstance(c.get("vagas"), int)))
            provs = {self.d["provimentos"][c["provimento"]]["id"]: self.d["provimentos"][c["provimento"]] for c in membros}
            normas_prov = [n for p in provs.values() for n in p.get("normas", [])]
            cards.append(
                f'<article class="papel"><span class="num">{esc(numero)}</span><h3>{esc(g["titulo"])}</h3>'
                f'<p class="como">{esc(como)}</p><p>{esc(g["o_que_faz"])}</p>'
                + self.porque(g.get("por_que"), normas_prov) + "</article>")
        return f"""
<section id="como-funciona" aria-labelledby="h-como">
  <header>
    <p class="label">1 · Como funciona</p>
    <h2 id="h-como">Quem governa Mostardas, e por quê</h2>
    <div class="prose"><p>O município tem dois Poderes. A <strong>Prefeitura</strong> (Poder Executivo) governa e presta os serviços. A <strong>Câmara de Vereadores</strong> (Poder Legislativo) faz as leis, aprova o orçamento e fiscaliza a Prefeitura. Os <strong>conselhos</strong> juntam governo e sociedade para acompanhar cada área. Cada cartão diz quem é, como chega ao cargo e qual regra explica isso.</p></div>
  </header>
  <div class="papeis">{"".join(cards)}</div>
  <p class="fora"><strong>Quem fiscaliza de fora:</strong> o Tribunal de Contas do Estado (<a href="https://tcers.tc.br/">TCE-RS</a>) analisa as contas e dá o parecer que a Câmara vota. O Ministério Público (<a href="https://www.mprs.mp.br/">MPRS</a>) e a Justiça agem quando a lei não é cumprida. E qualquer pessoa pode pedir informação, como mostra <a href="#participar">Como participar</a>.</p>
</section>"""

    def secao_quanto_custa(self):
        fin = self.financa()
        if not fin:
            return ""
        pop = self.populacao(ano=fin["exercicio"], tipo="estimativa")
        total = fin["total_sem_intra"]["liquidado"]
        linhas = sorted(fin["linhas"], key=lambda l: -l["liquidado"])
        maior = linhas[0]["liquidado"]
        saude_educ = sum(l["liquidado"] for l in linhas if l["funcao_codigo"] in ("10", "12")) / total * 100
        barras = []
        for l in linhas:
            nome = ROTULO_FUNCAO.get(l["funcao"], l["funcao"][:1] + l["funcao"][1:].lower())
            pc = l["liquidado"] / pop["valor"]
            pc_txt = "menos de R$ 1 por morador" if pc < 1 else f"R$ {milhar(pc)} por morador"
            if l["funcao_codigo"] == "01":
                pc_txt += f" (R$ {milhar(pc / 12)} por mês)"
            barras.append(
                f'<li class="bar-row{" camara" if l["funcao_codigo"] == "01" else ""}" tabindex="0" '
                f'data-val="R$ {milhar(l["liquidado"])}" data-share="{esc(pct(l["liquidado"] / total * 100))} do total" '
                f'data-pc="{esc(pc_txt)}"><span class="bar-label">{esc(nome)}</span>'
                f'<span class="bar-track"><span class="bar" style="--w:{l["liquidado"] / maior * 100:.2f}%"></span></span>'
                f'<span class="bar-value">{reais_curto(l["liquidado"])}</span></li>')
        tabela = "".join(
            f'<tr><td>{esc(l["funcao_codigo"])} · {esc(l["funcao"])}</td><td class="n">{milhar(l.get("empenhado", 0), 2)}</td>'
            f'<td class="n">{milhar(l.get("liquidado", 0), 2)}</td><td class="n">{milhar(l.get("pago", 0), 2)}</td></tr>'
            for l in linhas)
        t, i = fin["total_sem_intra"], fin["intraorcamentarias"]
        nat = {c["conta"]: c["liquidado"] for c in fin["natureza_destaques"]["contas"]}
        apos = nat.get("3.1.90.01.00", 0)
        divida = nat.get("3.2.00.00.00", 0) + nat.get("4.6.00.00.00", 0)
        return f"""
<section id="quanto-custa" aria-labelledby="h-custa">
  <header>
    <p class="label">2 · Quanto custa</p>
    <h2 id="h-custa">Para onde foi o dinheiro em {fin["exercicio"]}</h2>
    <p class="headline">Em {fin["exercicio"]}, o município gastou <strong>R$ {f"{total / 1e6:.1f}".replace(".", ",")} milhões</strong>, cerca de <strong>R$ {milhar(round(total / pop["valor"], -2))} por morador</strong>. Saúde e educação ficaram com {f"{saude_educ:.0f}"}%.</p>
  </header>
  <div class="grafico">
    <ul class="bars" aria-label="Gasto do município em {fin["exercicio"]} por área, do maior para o menor">{"".join(barras)}</ul>
    <div class="tip" id="tip" role="tooltip" hidden></div>
  </div>
  {self.rodape_fonte([fin["fonte"], pop["fonte"]], [(fin["conferido_em"], "financas")])}
  <div class="notas">
    <div class="nota"><h3>Como ler</h3><p>A contabilidade pública separa o gasto por <strong>área</strong> (função de governo), não por secretaria. Saúde corresponde em grande parte à Secretaria de Saúde, e a linha da Câmara é a função "Legislativa". "Administração" junta gastos de vários órgãos. O valor por morador usa a estimativa do IBGE para {pop["ano"]} ({milhar(pop["valor"])} pessoas).</p><p>Ficaram fora do total R$ {f"{i['liquidado'] / 1e6:.1f}".replace(".", ",")} milhões em despesas intraorçamentárias, para não contar o mesmo dinheiro duas vezes.</p></div>
    <div class="nota"><h3>O que são "encargos especiais"</h3><p>São despesas que não se ligam a um serviço específico. Em {fin["exercicio"]}, o município gastou R$ {f"{apos / 1e6:.1f}".replace(".", ",")} milhões com aposentadorias do regime próprio dos servidores e R$ {f"{divida / 1e6:.1f}".replace(".", ",")} milhões com juros e amortização de dívidas. Como o relatório não traz a área Previdência, esses valores provavelmente estão nesta linha. A confirmação está entre os <a href="#lacunas">pedidos de informação</a>.</p>{self.rodape_fonte([fin["natureza_destaques"]["fonte"]])}</div>
    <div class="nota"><h3>Palavras do orçamento</h3><dl class="glossario"><dt>Empenhado</dt><dd>O município reservou o dinheiro e assumiu o compromisso.</dd><dt>Liquidado</dt><dd>O serviço foi feito ou a compra foi entregue e conferida. É o número usado acima.</dd><dt>Pago</dt><dd>O dinheiro saiu do caixa.</dd><dt>Intraorçamentária</dt><dd>Dinheiro que passa de um órgão do município para outro, como a contribuição da Prefeitura ao fundo de previdência dos servidores.</dd></dl></div>
  </div>
  <p class="fora"><strong>Quer ver cada compra?</strong> Todas as licitações, contratos e pagamentos, com busca e os pontos que merecem uma pergunta, estão em <a href="compras.html">Licitações, contratos e pagamentos</a>.</p>
  <details class="tabela">
    <summary>Ver a tabela completa (empenhado, liquidado e pago)</summary>
    <div class="table-scroll"><table>
      <thead><tr><th>Função de governo</th><th class="n">Empenhado</th><th class="n">Liquidado</th><th class="n">Pago</th></tr></thead>
      <tbody>{tabela}</tbody>
      <tfoot><tr><td>Total, sem intraorçamentárias</td><td class="n">{milhar(t["empenhado"], 2)}</td><td class="n">{milhar(t["liquidado"], 2)}</td><td class="n">{milhar(t["pago"], 2)}</td></tr>
      <tr><td>Intraorçamentárias (fora do total)</td><td class="n">{milhar(i["empenhado"], 2)}</td><td class="n">{milhar(i["liquidado"], 2)}</td><td class="n">{milhar(i["pago"], 2)}</td></tr></tfoot>
    </table></div>
  </details>
</section>"""

    def quem_comanda(self, org):
        """Titular atual do órgão, com desde quando e por qual ato; devolve (html, fontes, conferidos)."""
        nota = org.get("nota_titular")
        cargo = next((c for c in self.d["cargos"].values() if c["orgao"] == org["id"] and c.get("titular")), None)
        ocs = self.ativas(cargo["id"]) if cargo else []
        if not ocs:
            if nota:
                conferidos = [(org["conferido_em"], "ocupacao")] if org.get("conferido_em") else []
                return esc(nota["texto"]), [nota["fonte"]], conferidos
            return (None, [], []) if not cargo else (self.falta(), [], [])
        partes = []
        for oc in ocs:
            detalhes = ([f'desde {br_data(oc["valido_desde"])}'] if oc.get("valido_desde") else []) + ([oc["forma"]] if oc.get("forma") else [])
            extra = f'<br><span class="label">{esc(" · ".join(detalhes))}</span>' if detalhes else ""
            partes.append(f'<strong>{esc(self.pessoa(oc["pessoa"]))}</strong>{extra}')
        return "<br>".join(partes), [oc["fonte"] for oc in ocs], [(oc["conferido_em"], "ocupacao") for oc in ocs]

    def ficha_orgao(self, o, destaque=False):
        quem, f_quem, c_quem = self.quem_comanda(o)
        ct = self.contato(o["id"])
        linhas = []
        if quem is not None:
            linhas.append(("Quem comanda", quem))
        linhas.append(("O que faz", self.campo(o, "o_que_faz")))
        if o.get("servicos"):
            linhas.append(("Serviços e unidades", esc(o["servicos"]["texto"])))
        linhas += self.linhas_contato(ct)
        fontes = [o.get("o_que_faz", {}).get("fonte"), o.get("servicos", {}).get("fonte")] + f_quem + ([ct["fonte"]] if ct else [])
        conferidos = c_quem + ([(ct["conferido_em"], "contato")] if ct else [])
        return (f'<article class="ficha{" destaque" if destaque else ""}" id="{esc(o["id"])}"><header><p class="label">{esc(TIPO_ORGAO[o["tipo"]])}</p>'
                f'<h3>{esc(o["nome"])}</h3></header>{self.dl(linhas)}{self.porque(o.get("por_que"))}'
                f'{self.rodape_fonte(fontes, conferidos)}</article>')

    def secao_prefeitura(self):
        O = self.d["orgaos"]
        pref = O["prefeitura"]
        eleitos = []
        fontes, conferidos = [], []
        for cid in ("prefeito", "vice-prefeito"):
            for oc in self.ativas(cid):
                det = " · ".join(x for x in (oc.get("partido"), oc.get("forma")) if x)
                eleitos.append((self.d["cargos"][cid]["nome"], f'<strong>{esc(self.pessoa(oc["pessoa"]))}</strong>' + (f' <span class="label">{esc(det)}</span>' if det else "")))
                fontes.append(oc["fonte"])
                conferidos.append((oc["conferido_em"], "ocupacao"))
        if not eleitos:
            eleitos = [("Prefeito e vice", self.falta())]
        ct = self.contato("prefeitura")
        linhas = eleitos + [("O que faz", self.campo(pref, "o_que_faz")), ("Estrutura", self.campo(pref, "estrutura"))] + self.linhas_contato(ct)
        fontes += [pref.get("o_que_faz", {}).get("fonte"), pref.get("estrutura", {}).get("fonte")] + ([ct["fonte"]] if ct else [])
        conferidos += [(ct["conferido_em"], "contato")] if ct else []
        cabeca = (f'<article class="ficha destaque" id="prefeitura-geral"><header><p class="label">Poder Executivo</p><h3>{esc(pref["nome"])}</h3></header>'
                  f'{self.dl(linhas)}{self.porque(pref.get("por_que"))}{self.rodape_fonte(fontes, conferidos)}</article>')
        filhos = sorted((o for o in O.values() if o.get("pai") == "prefeitura"), key=lambda o: (o.get("ordem", 99), o["nome"]))
        return f"""
<section id="prefeitura" aria-labelledby="h-pref">
  <header>
    <p class="label">3 · Prefeitura</p>
    <h2 id="h-pref">Prefeitura e secretarias</h2>
    <div class="prose"><p>O prefeito escolhe quem comanda cada secretaria. Por isso, nesta parte, os nomes mudam mais do que em qualquer outra, e cada ficha diz quando foi conferida.</p></div>
  </header>
  <div class="grid">{cabeca}{"".join(self.ficha_orgao(o) for o in filhos)}</div>
</section>"""

    def secao_camara(self):
        O = self.d["orgaos"]
        cam = O["camara"]
        ct = self.contato("camara")
        fin = self.financa()
        custo = self.falta()
        fontes_custo = []
        if fin:
            leg = next((l for l in fin["linhas"] if l["funcao_codigo"] == "01"), None)
            if leg:
                pop = self.populacao(ano=fin["exercicio"], tipo="estimativa")
                pc = leg["liquidado"] / pop["valor"]
                custo = f'R$ {milhar(leg["liquidado"])} em {fin["exercicio"]}, ou R$ {milhar(pc)} por morador no ano (cerca de R$ {milhar(pc / 12)} por mês)'
                fontes_custo = [fin["fonte"]]
        ver = self.d["cargos"].get("vereador", {})
        sub = ver.get("remuneracao")
        linhas = [("O que faz", self.campo(cam, "o_que_faz")), ("Quanto custa", custo),
                  ("Salário de vereador (subsídio)", esc(sub["texto"]) if sub else self.falta())]
        if cam.get("gasto_pessoal"):
            linhas.append(("Gasto com pessoal", esc(cam["gasto_pessoal"]["texto"])))
            fontes_custo.append(cam["gasto_pessoal"]["fonte"])
        sessoes = [ev for ev in self.d["eventos"].values() if ev.get("orgao") == "camara"]
        for ev in sessoes:
            linhas.append((ev["titulo"], esc(ev["quando"])))
        linhas += self.linhas_contato(ct)
        fontes = [cam.get("o_que_faz", {}).get("fonte")] + fontes_custo + ([sub.get("fonte")] if sub else []) + [ev.get("fonte") for ev in sessoes] + ([ct["fonte"]] if ct else [])
        conferidos = [(ct["conferido_em"], "contato")] if ct else []
        ficha = (f'<article class="ficha destaque" id="camara-geral"><header><p class="label">Poder Legislativo</p><h3>{esc(cam["nome"])}</h3></header>'
                 f'{self.dl(linhas)}{self.porque(cam.get("por_que"))}{self.rodape_fonte(fontes, conferidos)}</article>')
        # Composição: vereadores ativos e, se houver, o cargo na Mesa.
        cargos_mesa = [c for c in self.d["cargos"].values() if c["orgao"] == "camara" and c["id"] != "vereador"]
        mesa, f_mesa = {}, []
        for pos, c in enumerate(cargos_mesa):
            for oc in self.ativas(c["id"]):
                mesa[oc["pessoa"]] = (pos, oc.get("titulo") or c["nome"])
                f_mesa.append(oc["fonte"])
        ocs = sorted(self.ativas("vereador"), key=lambda o: (mesa.get(o["pessoa"], (99,))[0], -(o.get("votos") or 0)))
        f_comp = list(dict.fromkeys([o["fonte"] for o in ocs] + f_mesa))
        c_comp = [(o["conferido_em"], "ocupacao") for o in ocs]

        def nome_cel(o):
            if o.get("valido_desde"):
                return esc(self.pessoa(o["pessoa"]))
            return (f'{esc(self.pessoa(o["pessoa"]))}<br><span class="chip falta">'
                    f'{esc(o.get("forma") or "em exercício")}; posse não encontrada</span>')
        linhas_tab = "".join(
            f'<tr><td>{nome_cel(o)}</td><td>{esc(o.get("partido") or "—")}</td>'
            f'<td class="n">{milhar(o["votos"]) if o.get("votos") else "—"}</td><td>{esc(mesa.get(o["pessoa"], (0, "—"))[1])}</td></tr>'
            for o in ocs)
        # Histórico: quem saiu e as Mesas anteriores (nada se apaga, decisão 3).
        hist, f_hist = [], []
        for o in self.encerradas("vereador"):
            hist.append(f'<li><strong>{esc(self.pessoa(o["pessoa"]))}</strong> ({esc(o.get("partido", ""))}, '
                        f'{milhar(o.get("votos") or 0)} votos em 2024). {esc(o.get("nota", ""))}</li>')
            f_hist.append(o["fonte"])
        anos = {}
        for c in cargos_mesa:
            for o in self.encerradas(c["id"]):
                anos.setdefault(o["valido_desde"][:4], []).append(f'{o.get("titulo") or c["nome"]}: {self.pessoa(o["pessoa"])}')
                f_hist.append(o["fonte"])
        for ano, membros in sorted(anos.items()):
            hist.append(f'<li><strong>Mesa de {esc(ano)}.</strong> {esc(" · ".join(membros))}.</li>')
        hist_html = (f'<h3 class="sub">O que mudou nesta legislatura</h3><ul class="docs">{"".join(hist)}</ul>'
                     f'{self.rodape_fonte(f_hist)}') if hist else ""
        comp = (f'<h3 class="sub">Os {len(ocs)} vereadores</h3><div class="table-scroll solta"><table>'
                f'<thead><tr><th>Vereador ou vereadora</th><th>Partido na eleição</th><th class="n">Votos em 2024</th><th>Cargo na Mesa em {self.hoje.year}</th></tr></thead>'
                f'<tbody>{linhas_tab}</tbody></table></div>{self.rodape_fonte(f_comp, c_comp)}{hist_html}') if ocs else ""
        return f"""
<section id="camara" aria-labelledby="h-camara">
  <header>
    <p class="label">4 · Câmara</p>
    <h2 id="h-camara">Câmara de Vereadores</h2>
  </header>
  <div class="grid">{ficha}</div>
  {comp}
</section>"""

    def recente(self, o):
        ev = o.get("evidencia")
        return bool(ev) and (self.hoje - dt.date.fromisoformat(ev["data"])).days <= 365

    def sinal(self, o):
        ev = o.get("evidencia")
        if not ev:
            return '<span class="chip falta">Sem registro encontrado</span>'
        classe, rotulo = ("ok", "Registro recente") if self.recente(o) else ("falta", "Último registro")
        return f'<span class="chip {classe}">{rotulo}: {br_data(ev["data"])}</span>'

    def ficha_conselho(self, o):
        ct = self.contato(o["id"])
        tutelar = o["tipo"] == "conselho-tutelar"
        linhas = [("O que faz", self.campo(o, "o_que_faz")), ("Composição e mandato", self.campo(o, "composicao"))]
        if not tutelar:
            linhas.append(("Reuniões", self.campo(o, "reunioes")))
        linhas.append(("Lei", self.campo(o, "lei_criacao")))
        linhas += self.linhas_contato(ct)
        if not tutelar:
            ev = o.get("evidencia")
            linhas.append(("Sinal de funcionamento", self.sinal(o) + (f'<br>{esc(ev["texto"])}' if ev else "")))
        fontes = [o.get(k, {}).get("fonte") for k in CAMPOS_COM_FONTE] + ([ct["fonte"]] if ct else [])
        conferidos = [(ct["conferido_em"], "contato")] if ct else []
        if o.get("conferido_em"):
            conferidos.append((o["conferido_em"], "conselho"))
        return (f'<article class="ficha" id="{esc(o["id"])}"><header><p class="label">{esc(TIPO_ORGAO[o["tipo"]])}</p>'
                f'<h3>{esc(o["nome"])}</h3></header>{self.dl(linhas)}{self.porque(o.get("por_que"))}'
                f'{self.rodape_fonte(fontes, conferidos)}</article>')

    def secao_conselhos(self):
        todos = sorted((o for o in self.d["orgaos"].values() if o["tipo"] in ("conselho", "conselho-tutelar")),
                       key=lambda o: (o["tipo"] != "conselho-tutelar", o.get("ordem", 99), o["nome"]))
        completos = [o for o in todos if o.get("ficha_completa")]
        resumidos = [o for o in todos if not o.get("ficha_completa")]
        municipais = [o for o in todos if o["tipo"] == "conselho"]
        n_recentes = sum(1 for o in municipais if self.recente(o))
        # Conselhos com pouca informação vão para uma tabela: resumo antes do detalhe.
        linhas, fontes = [], []
        for o in resumidos:
            base = ""
            if o.get("por_que"):
                refs = [self.d["normas"][n] for n in o["por_que"]["normas"]]
                base = "<br>" + " · ".join(f'<a href="{esc(n["url"])}">{esc(n["referencia"])}</a>' for n in refs)
            linhas.append(f'<tr><td><strong>{esc(o["nome"])}</strong>{base}</td><td>{self.campo(o, "lei_criacao")}</td>'
                          f'<td>{self.campo(o, "composicao")}</td><td>{self.sinal(o)}</td></tr>')
            fontes += [o.get(k, {}).get("fonte") for k in CAMPOS_COM_FONTE]
        datas = [o["conferido_em"] for o in resumidos if o.get("conferido_em")]
        tabela = (f'<h3 class="sub">Outros conselhos criados por lei</h3><div class="table-scroll solta"><table>'
                  f'<thead><tr><th>Conselho</th><th>Lei</th><th>Composição e mandato</th><th>Último sinal</th></tr></thead>'
                  f'<tbody>{"".join(linhas)}</tbody></table></div>'
                  f'{self.rodape_fonte(fontes, [(min(datas), "conselho")] if datas else [])}') if resumidos else ""
        extras = []
        so_lei = self.d["municipio"].get("conselhos_so_lei", [])
        nao = self.d["municipio"].get("conselhos_nao_encontrados", [])
        if so_lei:
            extras.append(f'<strong>Só a lei, sem ato recente:</strong> {esc("; ".join(so_lei))}.')
        if nao:
            extras.append(f'<strong>Procurados e não encontrados:</strong> {esc("; ".join(nao))}.')
        extras_html = (f'<p class="fora">{" ".join(extras)} Não achar um registro não prova que o conselho não exista ou não funcione. '
                       'Por isso esses casos entram nos <a href="#lacunas">pedidos de informação</a>.</p>') if extras else ""
        return f"""
<section id="conselhos" aria-labelledby="h-cons">
  <header>
    <p class="label">5 · Conselhos</p>
    <h2 id="h-cons">Conselhos: onde governo e sociedade se encontram</h2>
    <div class="prose"><p>Vários conselhos são exigidos por lei federal, e alguns são condição para o município receber dinheiro da União. Dos {len(municipais)} conselhos municipais encontrados, <strong>{n_recentes} têm algum registro oficial no último ano</strong>: ata, parecer, nomeação ou convocação. Cada ficha mostra o que o conselho faz, por que existe e o sinal mais recente de funcionamento.</p></div>
  </header>
  <div class="grid">{"".join(self.ficha_conselho(o) for o in completos)}</div>
  {tabela}
  {extras_html}
</section>"""

    def canais(self, tipo):
        out = []
        for ct in self.d["contatos"]:
            for c in ct.get("canais", []):
                if c["tipo"] == tipo:
                    out.append((ct["orgao"], c, c.get("fonte") or ct["fonte"]))
        return out

    def secao_participar(self):
        itens = []
        for ev in sorted(self.d["eventos"].values(), key=lambda e: e.get("ordem", 99)):
            fonte = self.rodape_fonte([ev["fonte"]]) if ev.get("fonte") else ""
            itens.append(f'<li><h3>{esc(ev["titulo"])}</h3><p class="quando">{esc(ev["quando"])}</p><p>{esc(ev["descricao"])}</p>'
                         f'{self.porque(None, ev.get("normas", []))}{fonte}</li>')
        esic = self.canais("e-sic")
        links = " ou ".join(f'<a href="{esc(c["url"])}">{esc(c["rotulo"])}</a>' for _, c, _ in esic)
        itens.insert(0, f'<li><h3>Pedir uma informação</h3><p class="quando">Pela internet, a qualquer hora</p>'
                        f'<p>Use o {links}. Guarde o número do protocolo.</p>'
                        f'{self.porque(None, ["lai-10-3", "lai-11"])}{self.rodape_fonte([f for _, _, f in esic])}</li>')
        ouv = self.canais("ouvidoria")
        if ouv:
            itens.insert(1, f'<li><h3>Reclamar, sugerir ou elogiar</h3><p class="quando">Ouvidoria</p>'
                            f'<p>Para problemas com um serviço, use a <a href="{esc(ouv[0][1]["url"])}">ouvidoria da Prefeitura</a>.</p>'
                            f'{self.porque(None, ["l13460-7"])}{self.rodape_fonte([ouv[0][2]])}</li>')
        return f"""
<section id="participar" aria-labelledby="h-part">
  <header>
    <p class="label">6 · Como participar</p>
    <h2 id="h-part">Como participar e acompanhar</h2>
  </header>
  <ul class="acoes">{"".join(itens)}</ul>
</section>"""

    def secao_documentos(self):
        docs = sorted((f for f in self.d["fontes"].values() if f.get("documento")), key=lambda f: f["documento"].get("ordem", 99))
        lis = "".join(f'<li><a href="{esc(f["url"])}">{esc(f["documento"]["nome"])}</a><span>{esc(f["documento"]["descricao"])}</span></li>' for f in docs)
        for f in docs:
            self.fontes_usadas.add(f["id"])
        return f"""
<section id="documentos" aria-labelledby="h-docs">
  <header>
    <p class="label">7 · Documentos</p>
    <h2 id="h-docs">Onde estão os documentos oficiais</h2>
  </header>
  <ul class="docs">{lis}</ul>
</section>"""

    def secao_lacunas(self):
        destinos = {o: c for o, c, _ in self.canais("e-sic")}
        por_destino = {"prefeitura": [], "camara": []}
        for la in self.d["lacunas"].values():
            canal = destinos.get(la["destino"])
            onde = f'<a href="{esc(canal["url"])}">{esc(canal["rotulo"])}</a>' if canal else esc(la["destino"])
            status = {"aberta": "Pedido ainda não feito", "pedido": "Pedido feito, aguardando resposta", "respondida": "Respondida"}.get(la.get("status", "aberta"))
            por_destino[la["destino"]].append(
                f'<li><span class="chip falta">{esc(status)}</span><h3>{esc(la["descricao"])}</h3>'
                f'<p class="pergunta" id="q-{esc(la["id"])}">{esc(la["pergunta"])}</p>'
                f'<p class="source">Enviar para: {onde}</p>'
                f'<button class="copiar" type="button" data-alvo="q-{esc(la["id"])}">Copiar pergunta</button></li>')
        lis = []
        for destino, titulo in (("prefeitura", "Para a Prefeitura"), ("camara", "Para a Câmara")):
            if por_destino[destino]:
                lis.append(f'<li class="grupo-lacunas"><h3 class="sub">{titulo} ({len(por_destino[destino])})</h3></li>' + "".join(por_destino[destino]))
        return f"""
<section id="lacunas" aria-labelledby="h-lac">
  <header>
    <p class="label">8 · O que não encontramos</p>
    <h2 id="h-lac">O que não encontramos, e a pergunta para pedir</h2>
    <div class="prose"><p>A falta de uma informação também é informação. Cada item abaixo tem uma pergunta pronta para o pedido de acesso à informação. Quando a resposta chegar, ela vira fonte deste guia.</p></div>
  </header>
  <ul class="lacunas">{"".join(lis)}</ul>
</section>"""

    def rodape(self):
        n_fatos = len(self.d["ocupacoes"]) + len(self.d["contatos"]) + len(self.d["orgaos"]) + len(self.d["eventos"])
        return (f'    <p><strong>Como este guia é feito.</strong> As informações ficam em arquivos de dados, cada uma com fonte, data de conferência e período de validade. A página é gerada a partir deles. Esta versão foi gerada em {self.hoje.strftime("%d/%m/%Y")} com {n_fatos} registros e {len(self.fontes_usadas)} fontes citadas.</p>\n'
                '    <p><strong>Prazos de conferência.</strong> Titulares de cargos: 30 dias. Contatos: 90 dias. Conselhos: 90 dias. Gastos: 60 dias. Passado o prazo, a ficha mostra "a conferir".</p>\n'
                '    <p><strong>Achou um erro?</strong> Este é um rascunho. Toda correção entra com registro do que mudou e por quê.</p>')

    def montar(self):
        secoes = [self.secao_como_funciona(), self.secao_quanto_custa(), self.secao_prefeitura(), self.secao_camara(),
                  self.secao_conselhos(), self.secao_participar(), self.secao_documentos(), self.secao_lacunas()]
        corpo = (MODELOS / "pagina.html").read_text(encoding="utf-8")
        trocas = {
            "{{estilo}}": (MODELOS / "estilo.css").read_text(encoding="utf-8"),
            "{{script}}": (MODELOS / "interacao.js").read_text(encoding="utf-8"),
            "{{numeros_cidade}}": self.numeros_cidade(),
            "{{secoes}}": "\n".join(secoes),
        }
        for k, v in trocas.items():
            corpo = corpo.replace(k, v)
        return corpo.replace("{{rodape}}", self.rodape())


def documento_completo(fragmento):
    """O Artifact acrescenta doctype, head e body sozinho; um site próprio precisa deles no arquivo."""
    i = fragmento.index('<a class="skip"')
    return ('<!doctype html>\n<html lang="pt-BR">\n<head>\n' + fragmento[:i] + '</head>\n<body>\n'
            + fragmento[i:] + '</body>\n</html>\n')


def gerar(saida, hoje, documento=False):
    d = carregar(hoje)
    pagina = Pagina(d, hoje)
    html_final = pagina.montar()
    if documento:
        html_final = documento_completo(html_final)
    pathlib.Path(saida).write_text(html_final, encoding="utf-8")
    return len(html_final), len(pagina.fontes_usadas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("saida")
    ap.add_argument("--hoje", default=dt.date.today().isoformat())
    ap.add_argument("--documento", action="store_true", help="gera documento HTML completo (site próprio)")
    a = ap.parse_args()
    tamanho, fontes = gerar(a.saida, dt.date.fromisoformat(a.hoje), a.documento)
    print(f"ok: {a.saida} ({tamanho // 1024} KB, {fontes} fontes citadas)")


if __name__ == "__main__":
    main()
