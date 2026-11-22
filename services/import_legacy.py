"""Import existing legacy CSV counter snapshots into the RabbitMQ event stream.

Run from an authorized machine with AMQP_URL exported:
  python import_legacy.py path/to/samples.csv path/to/uplinks.json
Only derived bps, not device IPs, communities or aliases, are sent to RabbitMQ.
"""
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from common import connect_amqp
import pika


def vendor_technology(device):
    vendor = str(device.get('vendor', 'UNKNOWN')).upper()
    typ = str(device.get('device_type', '')).upper()
    tech = 'GPON' if ('OLT' in typ or vendor in ('HUAWEI', 'ZTE')) else 'HFC'
    return vendor, tech


def convert_rows(rows, inventory):
    index = {(host, str(u['ifIndex'])): (dev, u)
             for host, dev in inventory.items() for u in dev.get('uplinks', [])}
    grouped = defaultdict(list)
    for row in rows:
        key = (row.get('hostname'), str(row.get('ifIndex')))
        if key not in index:
            continue
        try:
            dt = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
            in_octets = int(row['in_octets'])
            out_octets = int(row['out_octets'])
        except (ValueError, KeyError, TypeError):
            continue
        grouped[key].append((dt, in_octets, out_octets))
    for key, samples in grouped.items():
        dev, uplink = index[key]
        vendor, tech = vendor_technology(dev)
        capacity_bps = int(float(uplink.get('capacity_gbps') or 0) * 1e9)
        if capacity_bps <= 0:
            continue
        samples.sort(key=lambda x: x[0])
        for previous, current in zip(samples, samples[1:]):
            dt = (current[0] - previous[0]).total_seconds()
            din = current[1] - previous[1]
            dout = current[2] - previous[2]
            # Counter discontinuity/reboot or duplicate timestamp: skip rather than invent traffic.
            if dt <= 0 or din < 0 or dout < 0:
                continue
            rx_bps, tx_bps = din * 8 / dt, dout * 8 / dt
            # Impossible counter deltas are discarded; 20% tolerance for timing jitter.
            if max(rx_bps, tx_bps) > capacity_bps * 1.2:
                continue
            yield {'device_id': key[0], 'ifindex': int(key[1]),
                   'interface': uplink.get('interface') or uplink.get('ifName') or key[1],
                   'vendor': vendor, 'technology': tech, 'capacity_bps': capacity_bps,
                   'rx_bps': rx_bps, 'tx_bps': tx_bps,
                   'observed_at': current[0].isoformat(), 'source': 'snmp_legacy'}


def main(csv_path, inventory_path):
    inventory = json.loads(Path(inventory_path).read_text(encoding='utf-8'))
    with open(csv_path, newline='', encoding='utf-8-sig') as handle:
        events = list(convert_rows(csv.DictReader(handle), inventory))
    print(f'Valid events: {len(events)} (IP and credentials omitted)')
    if not events:
        return
    connection, channel = connect_amqp()
    for event in events:
        channel.basic_publish(exchange='', routing_key='netcapacity.samples',
                              body=json.dumps(event).encode(),
                              properties=pika.BasicProperties(delivery_mode=2))
    connection.close()
    print(f'Published {len(events)} SNMP-derived events')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: python import_legacy.py samples.csv uplinks.json')
    main(sys.argv[1], sys.argv[2])
