import json
import os
import time
from common import connect_amqp, connect_db

threshold = float(os.getenv('ALERT_THRESHOLD_PERCENT', '80'))
while True:
    try:
        db = connect_db()
        connection, channel = connect_amqp()
        channel.basic_qos(prefetch_count=20)
        def on_message(ch, method, properties, body):
            try:
                s = json.loads(body)
                utilization = max(float(s['rx_bps']), float(s['tx_bps'])) / float(s['capacity_bps']) * 100
                with db.transaction():
                    db.execute('INSERT INTO devices(id,vendor,technology) VALUES(%s,%s,%s) ON CONFLICT(id) DO UPDATE SET vendor=EXCLUDED.vendor, technology=EXCLUDED.technology', (s['device_id'],s['vendor'],s['technology']))
                    db.execute('INSERT INTO interfaces(device_id,ifindex,name,capacity_bps) VALUES(%s,%s,%s,%s) ON CONFLICT(device_id,ifindex) DO UPDATE SET name=EXCLUDED.name, capacity_bps=EXCLUDED.capacity_bps', (s['device_id'],s['ifindex'],s['interface'],s['capacity_bps']))
                    db.execute('INSERT INTO metrics(device_id,ifindex,observed_at,rx_bps,tx_bps,utilization_percent,source) VALUES(%s,%s,%s,%s,%s,%s,%s)', (s['device_id'],s['ifindex'],s['observed_at'],s['rx_bps'],s['tx_bps'],utilization,s['source']))
                    if utilization >= threshold:
                        db.execute('INSERT INTO alerts(device_id,ifindex,observed_at,utilization_percent,message) VALUES(%s,%s,%s,%s,%s)', (s['device_id'],s['ifindex'],s['observed_at'],utilization,'Expansion threshold reached'))
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception as exc:
                print('Failed processing sample:',repr(exc),flush=True)
                ch.basic_nack(delivery_tag=method.delivery_tag,requeue=False)
        channel.basic_consume(queue='netcapacity.samples',on_message_callback=on_message)
        print('Processor ready',flush=True)
        channel.start_consuming()
    except Exception as exc:
        print('Processor reconnecting:',repr(exc),flush=True)
        time.sleep(3)
