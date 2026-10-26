# Arquitetura de dados do Guia das Instituições de Mostardas

## O problema que ela resolve

Os dados de uma prefeitura mudam o tempo todo, e cada um muda num ritmo diferente:

- um secretário pode ser trocado por uma portaria publicada numa terça qualquer;
- a Mesa da Câmara muda todo ano;
- os gastos saem a cada dois meses;
- um telefone muda sem aviso.

Se esses fatos forem escritos direto na página, o guia envelhece em silêncio e ninguém sabe o que ainda vale. Por isso cada informação precisa dizer quatro coisas:

- de onde veio;
- quando foi conferida;
- desde quando vale;
- por que existe.

```
fontes oficiais ──coletar──▶ bruto/  (cópia fiel + hash)
                                 │
                        extrair e conferir
                                 ▼
                             dados/  (fatos curados: fonte, validade, base legal)
                                 │
                             construir   (valida e calcula o frescor)
                                 ▼
                site (HTML estático)  +  dados abertos (os mesmos JSON)
```

## Decisões e porquês

**1. Três camadas: `bruto/`, `dados/` e site.**
- `bruto/` guarda a cópia do que a fonte publicou, com data e SHA-256. Sites oficiais mudam e apagam, e a cópia é a prova do que estava lá. Também permite extrair de novo sem coletar de novo.
- `dados/` é a única fonte da verdade do projeto.
- O site é só uma das saídas. Os mesmos dados podem alimentar CSV, boletim de WhatsApp ou folha impressa sem reescrever nada.

**2. Os dados ficam separados pelo ritmo em que mudam.**

| Camada | Exemplos | Muda quando |
|---|---|---|
| Estrutura | órgãos, cargos, base legal | sai lei nova (raro) |
| Ocupação | quem é titular, partido, Mesa | ato ou eleição (a qualquer momento) |
| Números | gastos, orçamento, população | periodicamente (bimestral, anual) |
| Eventos | sessões, audiências, reuniões | segue um calendário |

Se tudo ficasse junto, cada troca de secretário obrigaria a mexer em dados estáveis. Separados, cada camada tem a própria rotina de atualização e o próprio coletor.

**3. Nada se apaga: tudo tem validade.**
Trocar um secretário não sobrescreve o registro. Fecha-se o antigo (`valido_ate`) e abre-se um novo (`valido_desde`). O histórico também é transparência ("quantos secretários de Saúde passaram em 2025?"), e o guia consegue mostrar como era em qualquer data.

**4. Duas datas diferentes.**
`valido_desde` é quando o fato passou a valer no mundo, pela data do ato. `conferido_em` é quando o projeto viu o fato na fonte. A primeira conta a história; a segunda mede a incerteza. Uma página conferida hoje pode estar desatualizada amanhã, e o leitor tem o direito de saber há quanto tempo cada coisa foi vista.

**5. Toda afirmação aponta para uma fonte, e a fonte tem tipo.**
Os tipos são `ato-oficial` (lei ou portaria no Diário), `dados-oficiais` (APIs do Tesouro, IBGE, TSE), `site-oficial` (página do órgão), `imprensa` e `resposta-lai`. Quando duas fontes discordam, vale esta ordem: ato oficial, dados oficiais, site oficial, imprensa. Site de prefeitura costuma ficar desatualizado, e uma regra fixa resolve o conflito sempre do mesmo jeito, sem opinião.

**6. O porquê também é dado.**
`normas.json` guarda cada regra com a referência exata (ex.: CF, art. 29, IV, a) e uma explicação em linguagem simples. Órgãos, cargos e eventos apontam para ela. Três ganhos:
- o cidadão entende a regra por trás do fato;
- quando a lei muda, a correção se faz num lugar só;
- dá para checar automaticamente se o município cumpre o que a lei exige (por exemplo, se um conselho obrigatório existe).

**7. Cada tipo de dado tem prazo de validade.**

| Dado | Revisar a cada | Por quê |
|---|---|---|
| Titulares de secretaria | 30 dias | troca por portaria, sem aviso |
| Vereadores e partidos | 30 dias | suplentes assumem, vereadores trocam de partido |
| Contatos e horários | 90 dias | mudam sem ato oficial |
| Conselhos | 90 dias | nomeações e mandatos vencem |
| Gastos | 60 dias | o Tesouro recebe relatório a cada bimestre |
| Mesa Diretora | 365 dias | eleição anual ou bienal |
| Estrutura e base legal | 180 dias | só muda por lei |

O build compara `conferido_em` com o prazo e marca "a conferir" sozinho. O frescor vira um número visível ao leitor, não uma promessa.

**8. Lacunas e pedidos de informação são dados.**
O que não se encontra vira um registro com a pergunta pronta para o e-SIC. Quando o pedido é feito, entram o protocolo, a data e o prazo legal (20 dias, mais 10 com justificativa, LAI art. 11). A ausência de informação também é informação, e o prazo da resposta pode ser acompanhado em público. A resposta vira fonte do tipo `resposta-lai`.

**9. Identificadores estáveis e códigos oficiais.**
Cada registro tem um id curto que não muda (`sec-saude`, `cargo-prefeito`). Onde existe código oficial, ele vai junto: IBGE 4312500, código da função de governo, número do candidato no TSE e, no futuro, CNES dos postos e INEP das escolas. Os códigos permitem cruzar com as bases nacionais sem adivinhar nomes, e os ids dão endereços estáveis às páginas.

**10. Pessoas: o mínimo.**
Uma pessoa só aparece pelo cargo público que ocupa: nome público, cargo e período. Não entram CPF nem contato pessoal, e conselheiros da sociedade civil não são nomeados. Assim o projeto cumpre a LGPD e o princípio de que a transparência é sobre o poder público, não sobre a vida dos moradores.

**11. Por enquanto, o banco de dados é JSON no Git.**
O volume é pequeno (centenas de registros). O Git dá de graça o histórico e a autoria: cada mudança é um commit com a fonte. Qualquer pessoa pode auditar o diff ou copiar o projeto. Quando entrarem dados transacionais (cada empenho, cada contrato do PNCP, milhares de linhas por ano), essa camada passa para SQLite, DuckDB ou Parquet gerado pelos coletores. Os fatos curados continuam no Git.

**12. O site é estático, gerado a partir dos dados.**
Abre rápido em celular simples e internet fraca, custa quase nada (Cloudflare Pages), não tem servidor nem banco expostos e é fácil de arquivar. Muda o dado, roda o build, publica.

**13. O build é o guardião.**
`scripts/construir.py` se recusa a gerar o site se:
- um fato não tiver fonte;
- uma fonte não tiver data de consulta;
- um id apontar para registro que não existe;
- dois titulares ocuparem o mesmo cargo de vaga única no mesmo período.

Os princípios da Carta passam a valer por construção, não por boa vontade.

**14. Cada fonte tem seu coletor e sua cadência.**
- O que tem API é automático: o Tesouro (SICONFI) em `scripts/coletar_siconfi.py`, e no futuro IBGE, TSE e PNCP.
- O que é página ou PDF (sites oficiais, Diário Oficial) é monitorado por cópia e comparação, e cada mudança abre uma revisão humana.
- O que vem por pedido de informação entra à mão.

Automatiza-se o que é estruturado. Pessoas conferem o que é ambíguo, como interpretar uma portaria.

## Arquivos

| Arquivo | O que guarda |
|---|---|
| `dados/fontes.json` | fontes: tipo, emissor, URL, data de consulta |
| `dados/normas.json` | regras: referência, link e explicação em linguagem simples |
| `dados/orgaos.json` | estrutura: o que faz, por que existe, a quem se subordina |
| `dados/cargos.json` | cargos: quantas vagas, como se chega, base legal |
| `dados/ocupacoes.json` | quem ocupa cada cargo, desde quando, por qual ato |
| `dados/contatos.json` | endereço, telefone, e-mail e horário, com validade |
| `dados/eventos.json` | sessões e audiências recorrentes e a regra que as exige |
| `dados/financas/` | séries de gastos geradas pelos coletores |
| `dados/lacunas.json` | o que falta, a pergunta para o e-SIC e o andamento |
| `bruto/` | cópias das fontes coletadas automaticamente, com SHA-256 |
| `modelos/` | aparência da página (HTML, CSS, JS) |
| `scripts/` | coletores e o build |

## Camada transacional: compras, contratos e pagamentos (26/10/2026)

A decisão 11 previa que, quando entrassem dados transacionais, eles sairiam da curadoria à mão. Foi o que aconteceu:

| Coletor | Fonte | Atualização na fonte | Saída |
|---|---|---|---|
| `scripts/coletar_licitacon.py` | LicitaCon do TCE-RS: Prefeitura (52400) e Câmara (52401) | quase diária | `dados/compras/` |
| `scripts/coletar_empenhos.py ANO` | despesa por empenhos do TCE-RS (arquivo estadual do ano) | a cada dois meses, com atraso | `dados/pagamentos/resumo-ANO.json` |
| `scripts/construir_compras.py` | as duas saídas acima | a cada coleta | `compras.html` e `compras-dados.json` |

**Por quê, item por item:**
- **Uma fonte oficial só para compras.** O município é obrigado a informar cada processo ao LicitaCon, e o TCE-RS publica tudo em arquivos abertos. O PNCP e o Portal da Transparência municipal ficam como fontes de conferência.
- **Baixa só quando mudou.** O arquivo estadual de empenhos tem até 1,35 GB por ano. O coletor compara o `Last-Modified`, lê o arquivo em fluxo e guarda em `bruto/` só as linhas de Mostardas.
- **O vencedor pode vir do contrato.** Quando a licitação não informa quem ganhou, o nome vem do contrato assinado a partir dela.
- **Os indicadores medem só o que a lei mede.**
  - O de aditivos usa só o acréscimo de quantidade (código ACA). Renovação, reajuste e reequilíbrio aumentam o valor, mas não entram no limite de 25% do art. 125.
  - O de concorrência conta os licitantes registrados, que batem com as propostas.
  - Nenhum indicador é acusação, e a página diz isso.
- **Privacidade (decisão 10).**
  - CPF sempre mascarado (`***.123.456-**`).
  - Pagamentos a pessoas físicas só somados por tipo, porque ali há auxílios sociais.
  - A folha aparece como folha, sem nomes.
- **Os limites da fonte aparecem na página.**
  - Os dados são informados pelo próprio município e não são analisados pelo TCE-RS.
  - Em 26/10/2026, os pagamentos de 2026 iam só até 27/02/2026.

## Próximos passos, e quando fazer cada um

- **Atualização automática diária** dos coletores e da página: agora, porque os dados de compras mudam quase todo dia.
- **Pagamentos em tempo real** pelo Portal da Transparência municipal (Pronim): quando a atualização automática estiver rodando. O portal só entrega dados por formulário e com sessão, então o coletor é mais frágil.
- **Coletor do PNCP** para conferir o LicitaCon: quando houver divergência a explicar.

- **Monitor semanal** dos sites oficiais e do Diário Oficial (cópia e comparação): quando o guia estiver no ar.
- **JSON Schema público** dos dados abertos: quando alguém de fora for reutilizar os dados.
- **Banco analítico**: quando entrarem empenhos e contratos.
- **Página de erratas** gerada a partir do histórico do Git: no primeiro erro corrigido.
