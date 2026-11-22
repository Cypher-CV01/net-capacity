import os
import time
import pika
import psycopg

def connect_db():
    return psycopg.connect(os.environ['DATABASE_URL'], autocommit=True)

def connect_amqp():
    for attempt in range(20):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(os.environ['AMQP_URL']))
            channel = connection.channel()
            channel.queue_declare(queue='netcapacity.samples', durable=True)
            return connection, channel
        except pika.exceptions.AMQPConnectionError:
            if attempt == 19:
                raise
            time.sleep(2)
