"""Acesso às fontes com novas tentativas.

Por que: servidores públicos ficam fora do ar ou lentos com frequência. De 27/10 a 12/11/2026,
o servidor de dados do TCE-RS não respondeu ao GitHub, e uma única conexão esgotada derrubava
a coleta inteira. Uma oscilação curta passa com novas tentativas; uma queda longa é tratada
pelo alarme de frescor (scripts/conferir_frescor.py), não por aqui.
"""
import time
import urllib.error
import urllib.request

AGENTE = "mostardas-por-dentro (projeto cidadao; github.com/lucasbarrios2/mostardas-por-dentro)"
ESPERAS = (20, 60, 180)  # segundos entre as tentativas


def abrir(url, metodo="GET", timeout=180):
    """Abre a URL e devolve a resposta; tenta de novo em erro de rede ou 5xx. 4xx sobe na hora."""
    req = urllib.request.Request(url, method=metodo, headers={"User-Agent": AGENTE})
    for tentativa, espera in enumerate((*ESPERAS, None), start=1):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code < 500 or espera is None:
                raise
            erro = e
        except (urllib.error.URLError, OSError) as e:
            if espera is None:
                raise
            erro = e
        print(f"aviso: tentativa {tentativa} falhou em {url} ({erro}); nova tentativa em {espera}s", flush=True)
        time.sleep(espera)
