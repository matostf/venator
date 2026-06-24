from app.reverse.commons_search import _candidates_from_pages


def _page(extmeta):
    return {
        "title": "File:Exemplo.jpg",
        "imageinfo": [{
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Exemplo.jpg",
            "url": "https://upload.wikimedia.org/x/Exemplo.jpg",
            "thumburl": "https://upload.wikimedia.org/thumb/Exemplo.jpg",
            "mime": "image/jpeg", "width": 2000, "height": 1500,
            "extmetadata": extmeta,
        }],
    }


def test_extrai_date_time_original():
    pages = [_page({"DateTimeOriginal": {"value": "1808"}})]
    c = _candidates_from_pages(pages, strategy="direct")[0]
    assert c.date == "1808"


def test_fallback_para_datetime():
    pages = [_page({"DateTime": {"value": "1839-01-01"}})]
    c = _candidates_from_pages(pages, strategy="direct")[0]
    assert c.date == "1839-01-01"


def test_sem_data_fica_none():
    pages = [_page({})]
    c = _candidates_from_pages(pages, strategy="direct")[0]
    assert c.date is None
