import asyncio
from app.sources import acervos_adapter


def test_mapeia_dict_para_imageresult_e_descarta_sem_imagem(monkeypatch):
    fake = [
        {"title": "Mapa A", "creator": "Anon", "year": "1500",
         "url": "https://x/page", "image": "https://x/a.jpg",
         "license": "Public domain", "source": "bnf-gallica"},
        {"title": "Sem imagem", "creator": "", "year": "",
         "url": "https://x/page2", "license": "Public domain", "source": "bnf-gallica"},
    ]
    monkeypatch.setitem(acervos_adapter._SOURCES, "bnf", lambda q, maxn=10: fake)
    out = asyncio.run(acervos_adapter.search(None, "mapa", limit=10, acervo="bnf"))
    assert len(out) == 1                      # o "Sem imagem" é descartado
    assert out[0].source == "bnf-gallica"
    assert out[0].full_image == "https://x/a.jpg"
    assert out[0].title == "Mapa A"
    assert out[0].id.startswith("bnf:")
