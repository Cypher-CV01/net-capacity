"""Demo producer. Real SNMP runs through legacy/ on the host in this first MVP."""
import json
import math
import os
import random
import time
from datetime import datetime, timezone
import pika
from common import connect_amqp

mode = os.getenv('COLLECTION_MODE', 'simulated').lower()
if mode != 'simulated':
    raise SystemExit('SNMP real requires the explicit legacy bridge described in README; no silent fallback to simulation.')
interval = max(5, int(os.getenv('POLL_INTERVAL_SECONDS', '20')))
count = max(1, min(50, int(os.getenv('SIMULATED_DEVICES', '8'))))
connection, channel = connect_amqp()
print('Simulated collector started', flush=True)
cycle = 0
while True:
    for i in range(count):
        tech = 'GPON' if i % 2 == 0 else 'HFC'
        vendor = ('HUAWEI' if i % 4 == 0 else 'ZTE') if tech == 'GPON' else ('CISCO' if i % 4 == 1 else 'ARRIS')
        device = f'{tech}-DEMO-{i+1:02d}'
        for port in range(2):
            capacity = 10_000_000_000
            percent = max(2, min(98, 35 + (i * 11) % 50 + 15 * math.sin(cycle/3 + i) + random.uniform(-4, 4)))
            sample = dict(device_id=device, vendor=vendor, technology=tech,
                          ifindex=100+port, interface=f'10GE-demo-{port+1}',
                          capacity_bps=capacity, rx_bps=capacity*percent/100*0.55,
                          tx_bps=capacity*percent/100, observed_at=datetime.now(timezone.utc).isoformat(),
                          source='simulated')
            channel.basic_publish(exchange='', routing_key='netcapacity.samples',
                                  body=json.dumps(sample).encode(),
                                  properties=pika.BasicProperties(delivery_mode=2))
    print(f'Published cycle {cycle+1} for {count} devices', flush=True)
    cycle += 1
    time.sleep(interval)
