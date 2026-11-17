"""O alarme de frescor precisa disparar quando uma fonte para, e só nesse caso."""
import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import conferir_frescor  # noqa: E402


def montar(raiz, licitacon, empresas, pag_anterior, pag_atual=None, ano=2026):
    def grava(rel, conteudo):
        p = raiz / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(conteudo), encoding="utf-8")
    grava("dados/compras/fonte.json", {"consultado_em": licitacon})
    grava("dados/empresas/fonte.json", {"consultado_em": empresas})
    grava(f"bruto/tce-rs/empenhos/manifesto-{ano - 1}.json", {"verificado_em": pag_anterior})
    if pag_atual:
        grava(f"bruto/tce-rs/empenhos/manifesto-{ano}.json", {"verificado_em": pag_atual})


class Frescor(unittest.TestCase):
    hoje = dt.date(2026, 11, 17)

    def niveis(self, **datas):
        with tempfile.TemporaryDirectory() as tmp:
            montar(pathlib.Path(tmp), **datas)
            return [n for *_, n in conferir_frescor.avaliar(self.hoje, pathlib.Path(tmp))]

    def test_tudo_em_dia(self):
        self.assertEqual(self.niveis(licitacon="2026-11-17", empresas="2026-11-16", pag_anterior="2026-11-17", pag_atual="2026-11-17"),
                         ["ok", "ok", "ok", "ok"])

    def test_licitacon_parado_dispara(self):
        # Como em 27/10 a 12/11/2026: o TCE-RS fora do ar por dias seguidos.
        self.assertEqual(self.niveis(licitacon="2026-11-10", empresas="2026-11-16", pag_anterior="2026-11-17", pag_atual="2026-11-17")[0], "erro")

    def test_ano_novo_ainda_sem_arquivo_so_avisa(self):
        self.assertEqual(self.niveis(licitacon="2026-11-17", empresas="2026-11-16", pag_anterior="2026-11-17")[3], "aviso")


if __name__ == "__main__":
    unittest.main()
