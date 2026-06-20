# garimpo-imagens/tests/test_coleta.py
from app.coleta import selecionar, para_resolucao
from app.sources.base import ImageResult
from app.licenca import classificar


def _img(i, lic):
    return ImageResult(id=f"x:{i}", source="Wikimedia Commons", title=f"obra {i}",
                       thumbnail=f"http://t/{i}", full_image=f"http://f/{i}.jpg",
                       source_url=f"http://s/{i}", license=lic, creator="A")


def test_selecionar_descarta_nc_e_respeita_cota():
    cand = [_img(0, "CC BY-NC 4.0"), _img(1, "CC0"), _img(2, "Public domain"),
            _img(3, "CC BY 4.0")]
    out = selecionar(cand, cota=2, fonte_label={"Wikimedia Commons": "commons"})
    assert len(out) == 2                       # cota respeitada
    assert all(o["estadoLicenca"] != "rejeitado" for o in out)  # NC fora


def test_para_resolucao_monta_campos_do_manifesto():
    r = _img(7, "CC BY 4.0")
    res = classificar(r.license, fonte="commons", autor=r.creator or "")
    d = para_resolucao(r, res, fonte="commons", eixo="Roma", periodo="Antiguidade Clássica", consulta="coliseu")
    assert d["estadoLicenca"] == "atribuicao"
    assert d["creditoObrigatorio"].strip() != ""
    assert d["fonte"] == "commons"
    assert d["url"] == "http://f/7.jpg"
    assert d["eixo"] == "Roma" and d["consultaOrigem"] == "coliseu"


def _img_src(src, i, lic="CC0"):
    return ImageResult(id=f"{src}:{i}", source=src, title=f"{src} {i}",
                       thumbnail=f"http://t/{src}/{i}", full_image=f"http://f/{src}/{i}.jpg",
                       source_url=f"http://s/{src}/{i}", license=lic, creator="A")


_FL = {"Wikimedia Commons": "commons", "The Met": "met", "Europeana": "europeana"}


def test_selecionar_faz_round_robin_entre_fontes():
    # Candidatos concatenados commons -> met -> europeana (como o coletor monta).
    # A seleção antiga pegava 6 de commons; a nova intercala entre as fontes.
    cand = ([_img_src("Wikimedia Commons", i) for i in range(5)]
            + [_img_src("The Met", i) for i in range(5)]
            + [_img_src("Europeana", i) for i in range(5)])
    out = selecionar(cand, cota=6, fonte_label=_FL)
    fontes = [o["fonte"] for o in out]
    assert len(out) == 6
    assert fontes.count("commons") <= 3          # Commons não monopoliza
    assert "met" in fontes and "europeana" in fontes  # as outras fontes entram


def test_selecionar_fonte_unica_ainda_respeita_cota_e_licenca():
    # Com uma só fonte, comportamento equivale ao sequencial (cota + descarte NC).
    cand = [_img(0, "CC BY-NC 4.0"), _img(1, "CC0"), _img(2, "Public domain"), _img(3, "CC BY 4.0")]
    out = selecionar(cand, cota=2, fonte_label={"Wikimedia Commons": "commons"})
    assert len(out) == 2
    assert all(o["estadoLicenca"] != "rejeitado" for o in out)
