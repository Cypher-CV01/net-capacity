"""Processador de amostras: consome a fila, calcula a utilização e grava no PostgreSQL.

Pode rodar em várias instâncias ao mesmo tempo (consumidores concorrentes):
cada mensagem é entregue a apenas um processador. É assim que a camada de
processamento tem alta disponibilidade e escala horizontalmente.
"""
import os
import time

from prometheus_client import Counter, Histogram, start_http_server

from common import SampleQueue, connect_db, log

THRESHOLD = float(os.getenv('ALERT_THRESHOLD_PERCENT', '80'))

PROCESSED = Counter('netcapacity_processor_samples_total', 'Amostras gravadas no banco', ['technology'])
ALERTS = Counter('netcapacity_processor_alerts_total', 'Alertas de expansão gerados (>= limiar)', ['technology'])
FAILED = Counter('netcapacity_processor_failures_total', 'Amostras que falharam no processamento')
LATENCY = Histogram('netcapacity_processor_seconds', 'Tempo para gravar uma amostra no banco')


class Processor:
    def __init__(self):
        self.db = None

    def handle(self, s):
        with LATENCY.time():
            try:
                if self.db is None or self.db.closed:
                    self.db = connect_db()
                utilization = max(float(s['rx_bps']), float(s['tx_bps'])) / float(s['capacity_bps']) * 100
                with self.db.transaction():
                    self.db.execute('INSERT INTO devices(id,vendor,technology) VALUES(%s,%s,%s) '
                                    'ON CONFLICT(id) DO UPDATE SET vendor=EXCLUDED.vendor, technology=EXCLUDED.technology',
                                    (s['device_id'], s['vendor'], s['technology']))
                    self.db.execute('INSERT INTO interfaces(device_id,ifindex,name,capacity_bps) VALUES(%s,%s,%s,%s) '
                                    'ON CONFLICT(device_id,ifindex) DO UPDATE SET name=EXCLUDED.name, capacity_bps=EXCLUDED.capacity_bps',
                                    (s['device_id'], s['ifindex'], s['interface'], s['capacity_bps']))
                    self.db.execute('INSERT INTO metrics(device_id,ifindex,observed_at,rx_bps,tx_bps,utilization_percent,source) '
                                    'VALUES(%s,%s,%s,%s,%s,%s,%s)',
                                    (s['device_id'], s['ifindex'], s['observed_at'], s['rx_bps'], s['tx_bps'],
                                     utilization, s['source']))
                    if utilization >= THRESHOLD:
                        self.db.execute('INSERT INTO alerts(device_id,ifindex,observed_at,utilization_percent,message) '
                                        'VALUES(%s,%s,%s,%s,%s)',
                                        (s['device_id'], s['ifindex'], s['observed_at'], utilization,
                                         'Expansion threshold reached'))
                PROCESSED.labels(s['technology']).inc()
                if utilization >= THRESHOLD:
                    ALERTS.labels(s['technology']).inc()
                    log('capacity_alert', level='WARNING', device_id=s['device_id'], interface=s['interface'],
                        utilization_percent=round(utilization, 1), threshold=THRESHOLD)
            except Exception:
                FAILED.inc()
                if self.db is not None and not self.db.closed:
                    self.db.close()
                self.db = None
                raise


def main():
    start_http_server(int(os.getenv('METRICS_PORT', '9101')))
    processor = Processor()
    while True:
        try:
            queue = SampleQueue()
            log('processor_ready', backend=queue.backend, threshold=THRESHOLD)
            queue.consume(processor.handle)
        except Exception as exc:  # noqa: BLE001 - reconecta e continua
            log('processor_reconnecting', level='ERROR', error=repr(exc))
            time.sleep(3)


if __name__ == '__main__':
    main()
