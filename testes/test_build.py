"""O build é o guardião (ARQUITETURA.md, decisão 13): dados válidos geram o site; dados ruins param tudo."""
import datetime as dt
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import construir  # noqa: E402


class Build(unittest.TestCase):
    def test_dados_atuais_sao_validos(self):
        d = construir.carregar(dt.date.today())
        self.assertGreater(len(d["orgaos"]), 10)

    def test_fato_sem_fonte_para_o_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            copia = pathlib.Path(tmp) / "dados"
            shutil.copytree(RAIZ / "dados", copia)
            oc = json.loads((copia / "ocupacoes.json").read_text(encoding="utf-8"))
            oc[0].pop("fonte")
            (copia / "ocupacoes.json").write_text(json.dumps(oc), encoding="utf-8")
            original = construir.DADOS
            construir.DADOS = copia
            try:
                with self.assertRaises(SystemExit):
                    construir.carregar(dt.date.today())
            finally:
                construir.DADOS = original

    def test_site_completo(self):
        import construir_site
        with tempfile.TemporaryDirectory() as tmp:
            saida = pathlib.Path(tmp) / "site"
            sys.argv = ["construir_site.py", "--saida", str(saida)]
            construir_site.main()
            self.assertTrue((saida / "index.html").read_text(encoding="utf-8").startswith("<!doctype html>"))
            for arquivo in ("compras.html", "compras-dados.json", "_headers", "dados/compras/licitacoes.csv", "dados/compras/contratos.csv"):
                self.assertTrue((saida / arquivo).exists(), arquivo)


if __name__ == "__main__":
    unittest.main()
