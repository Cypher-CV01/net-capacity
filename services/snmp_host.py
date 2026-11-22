"""Windows host-side SNMPv2c collector for authorized VPN access.
No community/IP leaves the host: only interface metadata and calculated rates go to RabbitMQ.
"""
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


IN_OCTETS = '1.3.6.1.2.1.31.1.1.1.6'
OUT_OCTETS = '1.3.6.1.2.1.31.1.1.1.10'
OPER_STATUS = '1.3.6.1.2.1.2.2.1.8'
SYS_UPTIME = '1.3.6.1.2.1.1.3.0'


def calculate_rate(previous, current, capacity_bps, max_interval=300):
    """Reject resets, downtime, stale intervals and implausible rates."""
    if not previous:
        return None
    seconds = current['monotonic'] - previous['monotonic']
    if seconds <= 0 or seconds > max_interval or current['uptime'] < previous['uptime']:
        return None
    if current['status'] != 1 or previous['status'] != 1:
        return None
    din = current['in'] - previous['in']
    dout = current['out'] - previous['out']
    if din < 0 or dout < 0:
        return None
    rx, tx = din * 8 / seconds, dout * 8 / seconds
    if max(rx, tx) > capacity_bps * 1.2:
        return None
    return rx, tx


async def poll(engine, host, community, ifindexes, port=161):
    from pysnmp.hlapi.v3arch.asyncio import (CommunityData, UdpTransportTarget, ContextData, ObjectType, ObjectIdentity, get_cmd)
    oids = [SYS_UPTIME]
    for idx in ifindexes:
        oids += [f'{OPER_STATUS}.{idx}', f'{IN_OCTETS}.{idx}', f'{OUT_OCTETS}.{idx}']
    result = await get_cmd(engine, CommunityData(community, mpModel=1),
        await UdpTransportTarget.create((host, port), timeout=2, retries=1),
        ContextData(), *[ObjectType(ObjectIdentity(oid)) for oid in oids])
    error, status, _, binds = result
    if error or status:
        raise RuntimeError('SNMP request failed (timeout, authorization or agent error)')
    values = {str(oid): int(value) for oid, value in binds}
    uptime = values[SYS_UPTIME]
    now = time.monotonic()
    return {idx: {'uptime': uptime, 'monotonic': now,
        'status': values[f'{OPER_STATUS}.{idx}'],
        'in': values[f'{IN_OCTETS}.{idx}'], 'out': values[f'{OUT_OCTETS}.{idx}']}
        for idx in ifindexes}


async def main():
    import pika
    from pysnmp.hlapi.v3arch.asyncio import SnmpEngine
    from common import connect_amqp
    inventory_path = Path(os.environ.get('SNMP_INVENTORY', 'config/snmp-devices.json'))
    devices = json.loads(inventory_path.read_text(encoding='utf-8'))['devices']
    interval = max(15, int(os.getenv('SNMP_POLL_SECONDS', '60')))
    community = os.environ.get('SNMP_COMMUNITY')
    if not community:
        raise SystemExit('Set SNMP_COMMUNITY locally; do not commit it to Git.')
    previous = {}
    engine = SnmpEngine()
    connection, channel = connect_amqp()
    print(f'SNMP host collector ready: {len(devices)} configured devices', flush=True)
    while True:
        started = time.monotonic()
        for dev in devices:
            if dev.get('vendor', '').upper() != 'HUAWEI' or dev.get('model') != 'MA5800-X15':
                print('Skipping unsupported model', flush=True)
                continue
            try:
                interfaces = dev['interfaces']
                indexes = [int(x['ifindex']) for x in interfaces]
                samples = await poll(engine, dev['host'], community, indexes, int(dev.get('port', 161)))
                for item in interfaces:
                    idx = int(item['ifindex'])
                    capacity = int(item['capacity_bps'])
                    key = (dev['id'], idx)
                    rates = calculate_rate(previous.get(key), samples[idx], capacity, interval * 3)
                    previous[key] = samples[idx]
                    if rates is None:
                        continue
                    event = dict(device_id=dev['id'], vendor='HUAWEI', technology='GPON',
                        ifindex=idx, interface=item['name'], capacity_bps=capacity,
                        rx_bps=rates[0], tx_bps=rates[1],
                        observed_at=datetime.now(timezone.utc).isoformat(), source='snmp')
                    channel.basic_publish(exchange='', routing_key='netcapacity.samples',
                        body=json.dumps(event).encode(),
                        properties=pika.BasicProperties(delivery_mode=2))
                print(f"SNMP poll OK: {dev['id']}; first cycle is baseline only", flush=True)
            except Exception as exc:
                print(f"SNMP poll failed: {dev.get('id', 'unknown')} ({type(exc).__name__})", flush=True)
        await asyncio.sleep(max(0, interval - (time.monotonic() - started)))


if __name__ == '__main__':
    asyncio.run(main())
