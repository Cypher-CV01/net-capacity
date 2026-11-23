"""Relatório de capacidade (serverless).

Disparada pelo EventBridge. Consulta a API do NetCapacity, filtra as
interfaces com utilização >= limiar e publica no SNS um relatório de
"ação necessária". Usa apenas a biblioteca padrão + boto3 (já incluso
no runtime da Lambda), então não precisa de camadas nem pip.
"""
import json
import os
import urllib.request

import boto3

API_URL = os.environ["API_URL"].rstrip("/")
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
THRESHOLD = float(os.environ.get("ALERT_THRESHOLD_PERCENT", "80"))

sns = boto3.client("sns")


def fetch_interfaces():
    with urllib.request.urlopen(f"{API_URL}/api/interfaces", timeout=10) as resp:
        return json.loads(resp.read())


def lambda_handler(event, context):
    interfaces = fetch_interfaces()
    criticas = [
        i for i in interfaces
        if i.get("utilization_percent") is not None
        and float(i["utilization_percent"]) >= THRESHOLD
    ]
    criticas.sort(key=lambda i: float(i["utilization_percent"]), reverse=True)

    resumo = {"total_interfaces": len(interfaces), "acima_limiar": len(criticas), "limiar": THRESHOLD}
    print(json.dumps({"event": "relatorio_capacidade", **resumo}))  # vai para o CloudWatch Logs

    if not criticas:
        return resumo

    linhas = [
        f"- {i['device_id']} ({i['vendor']}/{i['technology']}) {i['name']}: "
        f"{float(i['utilization_percent']):.1f}% de {int(i['capacity_bps']) / 1e9:.0f} Gb/s"
        for i in criticas
    ]
    mensagem = (
        f"NetCapacity - AÇÃO NECESSÁRIA\n\n"
        f"{len(criticas)} de {len(interfaces)} interfaces de uplink estão em ou acima de {THRESHOLD:.0f}%.\n"
        f"Avaliar expansão de capacidade:\n\n" + "\n".join(linhas[:50]) +
        (f"\n... e mais {len(linhas) - 50}" if len(linhas) > 50 else "") +
        f"\n\nPainel: {API_URL}"
    )
    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=f"[NetCapacity] {len(criticas)} uplinks acima de {THRESHOLD:.0f}%",
        Message=mensagem,
    )
    return resumo
