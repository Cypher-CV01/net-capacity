"""Coletor simulado de uplinks (OLTs GPON e CMTS HFC).

Gera amostras realistas e publica na fila (RabbitMQ local ou Amazon SQS na AWS).
O coletor SNMP real (snmp_host.py) roda fora da nuvem, na rede de gerência autorizada.

Modelo de tráfego:
  - cada equipamento tem 2 pares protegidos de uplinks 10G (4 interfaces);
  - carga base por equipamento + ciclo "diário" acelerado (1 dia = 1 hora, para a demo);
  - alguns equipamentos "quentes" crescem devagar até passar de 80% (alerta de expansão).
"""
import math
import os
import random
import time
import zlib
from datetime import datetime, timezone

from prometheus_client import Counter, Gauge, start_http_server

from common import SampleQueue, log

MODELS = [
    # (prefixo, fabricante, modelo, tecnologia, portas em pares protegidos)
    ('OLT-HW', 'HUAWEI', 'MA5800-X15', 'GPON', ['0/8/0', '0/9/0', '0/8/1', '0/9/1']),
    ('OLT-ZTE', 'ZTE', 'C600', 'GPON', ['1/10/1', '1/11/1', '1/10/2', '1/11/2']),
    ('CMTS-CSC', 'CISCO', 'cBR-8', 'HFC', ['Te4/1/0', 'Te5/1/0', 'Te4/1/1', 'Te5/1/1']),
    ('CMTS-CASA', 'CASA', 'CG100', 'HFC', ['10GE0/0', '10GE1/0', '10GE0/1', '10GE1/1']),
    ('CMTS-ARR', 'ARRIS', 'E6000', 'HFC', ['xe13/0', 'xe14/0', 'xe13/1', 'xe14/1']),
]
CAPACITY_BPS = 10_000_000_000
DAY_SECONDS = 3600            # ciclo diário acelerado para a demonstração

PUBLISHED = Counter('netcapacity_collector_published_samples_total', 'Amostras publicadas na fila')
ERRORS = Counter('netcapacity_collector_errors_total', 'Falhas ao publicar amostras')
LAST_CYCLE = Gauge('netcapacity_collector_last_cycle_timestamp_seconds', 'Horário do último ciclo concluído')


def build_inventory(count):
    devices = []
    for n in range(count):
        prefix, vendor, model, tech, ports = MODELS[n % len(MODELS)]
        number = n // len(MODELS) + 1
        device_id = f'{prefix}-{number:02d}'
        seed = zlib.crc32(device_id.encode())
        devices.append({
            'device_id': device_id, 'vendor': f'{vendor} {model}', 'technology': tech, 'ports': ports,
            'base': 35 + seed % 30,                 # carga base 35-64 %
            'phase': (seed % 628) / 100,            # desloca o pico de cada equipamento
            'hot': n % 7 == 3,                      # ~1 em 7 cresce até passar de 80 %
        })
    return devices


def utilization(dev, elapsed, now):
    daily = 12 * math.sin(2 * math.pi * now / DAY_SECONDS + dev['phase'])
    growth = min(35, elapsed / 60 * 0.5) if dev['hot'] else 0     # +0,5 ponto por minuto, até +35
    return max(2.0, min(98.0, dev['base'] + daily + growth + random.uniform(-3, 3)))


def main():
    interval = max(5, int(os.getenv('POLL_INTERVAL_SECONDS', '60')))
    count = max(1, min(100, int(os.getenv('SIMULATED_DEVICES', '40'))))
    if os.getenv('COLLECTION_MODE', 'simulated').lower() != 'simulated':
        raise SystemExit('Coleta SNMP real usa services/snmp_host.py na rede autorizada; '
                         'este container só gera dados simulados.')
    start_http_server(int(os.getenv('METRICS_PORT', '9102')))
    devices = build_inventory(count)
    queue = SampleQueue()
    started = time.time()
    log('collector_started', devices=count, interfaces=count * 4, interval_seconds=interval,
        backend=queue.backend)
    cycle = 0
    while True:
        now = time.time()
        observed_at = datetime.now(timezone.utc).isoformat()
        samples = []
        for dev in devices:
            for pair in range(2):
                total = utilization(dev, now - started, now + pair * 400)
                share = random.uniform(0.47, 0.53)      # balanceamento do LAG entre os 2 membros
                for member, port in enumerate(dev['ports'][pair * 2:pair * 2 + 2]):
                    pct = total * (share if member == 0 else 1 - share) * 2
                    pct = max(1.0, min(99.0, pct))
                    tx = CAPACITY_BPS * pct / 100
                    samples.append(dict(
                        device_id=dev['device_id'], vendor=dev['vendor'], technology=dev['technology'],
                        ifindex=100 + pair * 2 + member, interface=port, capacity_bps=CAPACITY_BPS,
                        rx_bps=round(tx * random.uniform(0.15, 0.35)), tx_bps=round(tx),
                        observed_at=observed_at, source='simulated'))
        try:
            sent = queue.publish_many(samples)
            PUBLISHED.inc(sent)
            if sent < len(samples):
                ERRORS.inc(len(samples) - sent)
            cycle += 1
            LAST_CYCLE.set(time.time())
            log('cycle_published', cycle=cycle, samples=sent)
        except Exception as exc:  # noqa: BLE001 - segue tentando no próximo ciclo
            ERRORS.inc(len(samples))
            log('publish_failed', level='ERROR', error=repr(exc))
            time.sleep(5)
            queue = SampleQueue()
        time.sleep(max(1, interval - (time.time() - now)))


if __name__ == '__main__':
    main()
