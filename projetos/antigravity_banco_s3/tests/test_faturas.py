from datetime import date, timedelta


def test_fatura_atraso_juros_e_bloqueio_cartao(client):
    # Cliente Comum: juros de atraso 8% ao mês (0.08)
    cli = client.post(
        "/clientes",
        json={
            "nome": "Cliente Fatura",
            "cpf": "12345678909",
            "email": "fat@example.com",
            "categoria": "comum",
        },
    ).json()

    conta = client.post(
        "/contas",
        json={
            "cliente_id": cli["id"],
            "numero": "FAT-01",
            "tipo": "corrente",
            "saldo_inicial": 2000.0,
            "limite_credito": 0.0,
        },
    ).json()

    cartao = client.post(
        "/cartoes",
        json={"conta_id": conta["id"], "numero": "FAT-CARD-1", "limite": 1500.0},
    ).json()
    assert cartao["estado"] == "ativo"

    # Fatura vencida há 15 dias (mais de 10 dias de atraso)
    vencimento_passado = (date.today() - timedelta(days=15)).isoformat()
    fatura = client.post(
        f"/cartoes/{cartao['id']}/faturas",
        json={
            "cartao_id": cartao["id"],
            "mes_referencia": "2026-10",
            "valor": 1000.0,
            "data_vencimento": vencimento_passado,
        },
    ).json()

    assert fatura["estado"] == "atrasada"
    # Juros esperados: 1000 * 0.08 * (15 / 30) = 40.0
    assert float(fatura["juros_acumulados"]) == 40.0
    assert float(fatura["valor_total"]) == 1040.0

    # Cartão deve ter sido bloqueado pois atraso > 10 dias
    cartao_check = client.get(f"/cartoes/{cartao['id']}").json()
    assert cartao_check["estado"] == "bloqueado"

    # Realiza pagamento debitando da conta
    res_pag = client.post(
        f"/faturas/{fatura['id']}/pagamento",
        json={"debitar_da_conta": True},
    )
    assert res_pag.status_code == 200
    fat_paga = res_pag.json()
    assert fat_paga["estado"] == "paga"
    assert float(fat_paga["valor_pago"]) == 1040.0

    # Saldo da conta: 2000 - 1040 = 960.0
    assert float(client.get(f"/contas/{conta['id']}").json()["saldo"]) == 960.0

    # Cartão deve ter sido desbloqueado após a quitação da fatura
    cartao_pos_pag = client.get(f"/cartoes/{cartao['id']}").json()
    assert cartao_pos_pag["estado"] == "ativo"
