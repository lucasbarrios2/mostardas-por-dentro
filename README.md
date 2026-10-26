# Mostardas por Dentro

Guia cidadão, independente e apartidário, de como funcionam a Prefeitura, a Câmara e os conselhos de Mostardas/RS. O site traz:

- quem comanda cada órgão e por quê;
- quanto custa cada área;
- todas as licitações, contratos e pagamentos informados ao TCE-RS;
- as empresas fornecedoras, com sócios e representantes legais.

Cada informação tem fonte, data de conferência e a regra que explica por que é assim. As decisões de arquitetura e o motivo de cada uma estão em [ARQUITETURA.md](ARQUITETURA.md).

- Site: `https://mostardas-por-dentro.pages.dev` (depois de configurar o Cloudflare, abaixo)
- Prévia privada: https://claude.ai/artifact/XjzontUgXDatwqGwFQYzjv

## Como o site se atualiza sozinho

Todo dia às 7h30 (Brasília), o GitHub Actions ([`.github/workflows/atualizar.yml`](.github/workflows/atualizar.yml)) faz cinco coisas, em ordem:

1. Roda os coletores.
2. Roda os testes.
3. Monta o site em `site/`.
4. Guarda os dados novos num commit. O histórico do Git é a prova de quando cada dado mudou.
5. Publica no Cloudflare Pages.

Se um teste ou a validação dos dados falhar, nada é publicado.

| Coletor | O que traz | Quando muda na fonte |
|---|---|---|
| `coletar_licitacon.py` | licitações e contratos (TCE-RS) | quase todo dia |
| `coletar_empenhos.py ANO` | pagamentos (TCE-RS) | a cada dois meses |
| `coletar_cnpj.py` | empresas e sócios (Receita Federal) | todo mês |
| `coletar_siconfi.py ANO` | gastos por área (Tesouro) | uma vez por ano |

## Rodar localmente

```bash
python3 -m unittest discover -s testes        # privacidade e build
python3 scripts/construir_site.py             # monta o site em site/
```

## Configurar a publicação no Cloudflare (uma vez)

1. No Cloudflare, crie um token em **My Profile → API Tokens → Create Token → Custom token**. Dê só a permissão **Account → Cloudflare Pages → Edit**.
2. Cadastre o token e o ID da conta como segredos do repositório:

```bash
gh secret set CLOUDFLARE_API_TOKEN -R lucasbarrios2/mostardas-por-dentro
```

```bash
gh secret set CLOUDFLARE_ACCOUNT_ID -R lucasbarrios2/mostardas-por-dentro
```

3. Rode a primeira publicação:

```bash
gh workflow run atualizar.yml -R lucasbarrios2/mostardas-por-dentro
```

## Para trocar um titular (ex.: novo secretário)

1. Em `dados/ocupacoes.json`, preencha `valido_ate` do registro atual. Nada é apagado.
2. Acrescente o novo registro com `valido_desde`, o ato (`forma`), a `fonte` e o `conferido_em`.
3. Se a fonte for nova, cadastre-a em `dados/fontes.json`.
4. Rode os testes e faça o commit; o site é publicado sozinho.

## Privacidade

- CPF de pessoa física sempre mascarado.
- Pagamentos a pessoas físicas só somados por tipo, porque entre elas há quem recebe auxílio social.
- Dos sócios, só nome, qualificação e data de entrada; nada de endereço, telefone, e-mail ou idade.
- Arquivos brutos com CPF completo ficam fora do Git (`.gitignore`).
- Os testes reprovam qualquer CPF exposto nos dados publicados.

## Licença

Código sob a licença MIT ([LICENSE](LICENSE)). Textos e dados curados sob CC BY 4.0: pode reutilizar citando a fonte. Os dados públicos coletados seguem as condições de cada órgão de origem.
