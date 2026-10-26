"""A privacidade é testada, não prometida: se um CPF vazar para os dados publicados, o CI fica vermelho."""
import json
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from privacidade import mascarar_cpf_em_nome, mascarar_cpf_rotulado, mascarar_documento, tem_cpf_exposto  # noqa: E402


class Regras(unittest.TestCase):
    def test_cpf_mascarado_no_documento(self):
        self.assertEqual(mascarar_documento("F", "12345678901"), "***.456.789-**")

    def test_cnpj_formatado_inteiro(self):
        self.assertEqual(mascarar_documento("J", "37899196000108"), "37.899.196/0001-08")

    def test_cpf_dentro_do_nome_de_mei(self):
        self.assertEqual(mascarar_cpf_em_nome("FULANO DE TAL 12345678901"), "FULANO DE TAL ***.456.789-**")

    def test_renavam_no_objeto_fica(self):
        texto = "VEICULO RENAVAM 12345678901, PLACA ABC1234"
        self.assertEqual(mascarar_cpf_rotulado(texto), texto)

    def test_cpf_rotulado_no_objeto_sai(self):
        self.assertIn("***.456.789-**", mascarar_cpf_rotulado("PALESTRA DE FULANO, CPF 123.456.789-01"))


class DadosPublicados(unittest.TestCase):
    def nomes(self):
        c = RAIZ / "dados" / "compras"
        for r in json.loads((c / "contratos.json").read_text(encoding="utf-8")):
            if r["fornecedor"]:
                yield "contrato", r["fornecedor"]["nome"]
        for r in json.loads((c / "licitacoes.json").read_text(encoding="utf-8")):
            for v in r["vencedores"]:
                yield "licitação", v["nome"]
        for r in json.loads((c / "fornecedores.json").read_text(encoding="utf-8")):
            yield "fornecedor", r["nome"]
        for p in (RAIZ / "dados" / "pagamentos").glob("resumo-*.json"):
            for r in json.loads(p.read_text(encoding="utf-8"))["credores"]:
                yield "pagamento", r["nome"]
        emp = RAIZ / "dados" / "empresas" / "empresas.json"
        if emp.exists():
            for e in json.loads(emp.read_text(encoding="utf-8")).values():
                yield "empresa", e.get("razao_social", "")
                for s in e.get("socios", []):
                    yield "sócio", s["nome"]

    def test_nenhum_nome_com_cpf_exposto(self):
        expostos = [(onde, nome[:20]) for onde, nome in self.nomes() if tem_cpf_exposto(nome)]
        self.assertEqual(expostos, [])

    def test_documento_de_pessoa_fisica_sempre_mascarado(self):
        c = RAIZ / "dados" / "compras"
        for r in json.loads((c / "fornecedores.json").read_text(encoding="utf-8")):
            if r["tipo"] == "F" and r["doc"]:
                self.assertTrue(r["doc"].startswith("***"), r["nome"][:20])
        emp = RAIZ / "dados" / "empresas" / "empresas.json"
        if emp.exists():
            for e in json.loads(emp.read_text(encoding="utf-8")).values():
                for s in e.get("socios", []):
                    if s["tipo"] == "PF" and s.get("doc"):
                        self.assertIn("*", s["doc"])

    def test_pagamentos_a_pessoas_fisicas_sem_nome(self):
        for p in (RAIZ / "dados" / "pagamentos").glob("resumo-*.json"):
            for x in json.loads(p.read_text(encoding="utf-8"))["pessoas_fisicas"]:
                self.assertEqual(set(x), {"tipo", "pago", "n"})


if __name__ == "__main__":
    unittest.main()
