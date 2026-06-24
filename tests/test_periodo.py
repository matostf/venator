from app.reverse.periodo import mapear_periodo, Periodo


def test_seculo_romano():
    p = mapear_periodo("século XVI")
    assert p == Periodo(rotulo="século XVI", ano_inicio=1500, ano_fim=1599, termo_en="16th-century")


def test_ano_vira_seculo():
    p = mapear_periodo("1815")
    assert p.ano_inicio == 1800 and p.ano_fim == 1899 and p.termo_en == "19th-century"


def test_ano_dentro_de_frase():
    p = mapear_periodo("Desembarque da família real em 1808")
    assert p.termo_en == "19th-century"


def test_antiguidade():
    p = mapear_periodo("Antiguidade")
    assert p.termo_en == "ancient" and p.ano_inicio < 0


def test_vazio_ou_desconhecido():
    assert mapear_periodo("") is None
    assert mapear_periodo(None) is None
    assert mapear_periodo("coisa sem período") is None
