import pytest
from tests.conftest import gerar_cpf_valido


def test_tarifas_mensais_por_categoria(client):
    # Comum: R$ 30,00
    cli_c = client.post(
        "/clientes", json={"nome": "Cli C", "cpf": gerar_cpf_valido(911), "email": "tar_c@test.com", "categoria": "comum"}
    ).json()["id"]
    cta_c = client.post("/contas", json={"cliente_id": cli_c, "numero": "CTA-TAR-C", "limite_credito": "500.00"}).json()["id"]

    res_c = client.post(f"/contas/{cta_c}/tarifas/cobrar-mensalidade")
    assert res_c.status_code == 201
    assert res_c.json()["valor"] == "30.00"
    assert res_c.json()["estado"] == "cobrada"

    # Premium: R$ 0,00 (sem tarifa / isenta)
    cli_p = client.post(
        "/clientes", json={"nome": "Cli P", "cpf": gerar_cpf_valido(912), "email": "tar_p@test.com", "categoria": "premium"}
    ).json()["id"]
    cta_p = client.post("/contas", json={"cliente_id": cli_p, "numero": "CTA-TAR-P", "limite_credito": "500.00"}).json()["id"]

    res_p = client.post(f"/contas/{cta_p}/tarifas/cobrar-mensalidade")
    assert res_p.status_code == 201
    assert res_p.json()["valor"] == "0.00"
    assert res_p.json()["estado"] == "isenta"

    # Empresarial: R$ 120,00
    cli_e = client.post(
        "/clientes", json={"nome": "Cli E", "cpf": gerar_cpf_valido(913), "email": "tar_e@test.com", "categoria": "empresarial"}
    ).json()["id"]
    cta_e = client.post("/contas", json={"cliente_id": cli_e, "numero": "CTA-TAR-E", "limite_credito": "500.00"}).json()["id"]

    res_e = client.post(f"/contas/{cta_e}/tarifas/cobrar-mensalidade")
    assert res_e.status_code == 201
    assert res_e.json()["valor"] == "120.00"
    assert res_e.json()["estado"] == "cobrada"
