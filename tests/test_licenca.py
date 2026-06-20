from app.licenca import classificar, ResultadoLicenca


def test_nc_e_rejeitada_mesmo_contendo_by():
    # "CC BY-NC" contém "cc by" — o bug do _reusavel. Tem que rejeitar.
    assert classificar("CC BY-NC 4.0").estado == "rejeitado"
    assert classificar("CC BY-NC-SA 3.0").estado == "rejeitado"


def test_nd_e_rejeitada():
    assert classificar("CC BY-ND 4.0").estado == "rejeitado"


def test_cc0_e_pd_sao_livres():
    assert classificar("CC0 1.0").estado == "livre"
    assert classificar("Public domain").estado == "livre"
    assert classificar("Domínio Público").estado == "livre"
    assert classificar("CC0 1.0").credito == ""  # livre não exige crédito


def test_by_e_bysa_exigem_atribuicao_com_credito():
    r = classificar("CC BY 4.0", fonte="Wikimedia Commons", autor="J. Silva")
    assert r.estado == "atribuicao"
    assert r.categoria == "CC BY"
    assert "J. Silva" in r.credito and r.credito.strip() != ""
    assert classificar("CC BY-SA 3.0").categoria == "CC BY-SA"


def test_vazio_ou_desconhecido_e_rejeitado_failclosed():
    assert classificar("").estado == "rejeitado"
    assert classificar("See source").estado == "rejeitado"
    assert classificar("All rights reserved").estado == "rejeitado"
    assert classificar("GFDL only weirdstring").estado == "rejeitado"
