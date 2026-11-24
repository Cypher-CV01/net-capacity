"""Funções compartilhadas pelos microserviços do NetCapacity.

Mensageria com dois "backends", escolhidos pela variável QUEUE_BACKEND:
  - rabbitmq (padrão): usado no docker-compose.yml local de desenvolvimento
  - sqs: usado na AWS (Amazon SQS, fila gerenciada e Multi-AZ)
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

import psycopg

QUEUE_NAME = 'netcapacity.samples'


def log(event, level='INFO', **fields):
    """Log estruturado em JSON (uma linha por evento) -> fácil de filtrar no Loki."""
    record = {'ts': datetime.now(timezone.utc).isoformat(), 'level': level,
              'service': os.getenv('SERVICE_NAME', os.path.basename(sys.argv[0]).replace('.py', '')),
              'event': event, **fields}
    print(json.dumps(record, default=str), flush=True)


def connect_db():
    return psycopg.connect(os.environ['DATABASE_URL'], autocommit=True)


def connect_amqp():
    """Conexão RabbitMQ (ambiente local e scripts legados de SNMP)."""
    import pika
    for attempt in range(20):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(os.environ['AMQP_URL']))
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE_NAME, durable=True)
            return connection, channel
        except pika.exceptions.AMQPConnectionError:
            if attempt == 19:
                raise
            time.sleep(2)


class SampleQueue:
    """Publica e consome amostras independentemente do backend de fila."""

    def __init__(self):
        self.backend = os.getenv('QUEUE_BACKEND', 'rabbitmq').lower()
        if self.backend == 'sqs':
            import boto3
            region = os.getenv('AWS_REGION') or os.getenv('AWS_DEFAULT_REGION') or 'us-east-1'
            self.sqs = boto3.client('sqs', region_name=region)
            self.url = os.environ['SQS_QUEUE_URL']
        elif self.backend == 'rabbitmq':
            self.connection, self.channel = connect_amqp()
        else:
            raise SystemExit(f'QUEUE_BACKEND inválido: {self.backend} (use rabbitmq ou sqs)')

    def publish_many(self, samples):
        """Envia uma lista de amostras. No SQS, em lotes de 10 (menos requisições)."""
        if self.backend == 'sqs':
            failed = 0
            for start in range(0, len(samples), 10):
                batch = samples[start:start + 10]
                resp = self.sqs.send_message_batch(QueueUrl=self.url, Entries=[
                    {'Id': str(n), 'MessageBody': json.dumps(s)} for n, s in enumerate(batch)])
                failed += len(resp.get('Failed', []))
            return len(samples) - failed
        import pika
        for s in samples:
            self.channel.basic_publish(exchange='', routing_key=QUEUE_NAME, body=json.dumps(s).encode(),
                                       properties=pika.BasicProperties(delivery_mode=2))
        return len(samples)

    def consume(self, handler):
        """Chama handler(amostra) para cada mensagem.
        handler retorna normalmente -> mensagem confirmada (apagada da fila).
        handler lança exceção     -> mensagem volta para a fila (SQS: vai para a DLQ após 5 tentativas).
        """
        if self.backend == 'sqs':
            while True:
                resp = self.sqs.receive_message(QueueUrl=self.url, MaxNumberOfMessages=10,
                                                WaitTimeSeconds=20)  # long polling
                for msg in resp.get('Messages', []):
                    try:
                        handler(json.loads(msg['Body']))
                        self.sqs.delete_message(QueueUrl=self.url, ReceiptHandle=msg['ReceiptHandle'])
                    except Exception as exc:  # noqa: BLE001 - registrado e reprocessado
                        log('sample_failed', level='ERROR', error=repr(exc), message_id=msg.get('MessageId'))
        else:
            self.channel.basic_qos(prefetch_count=20)

            def on_message(ch, method, properties, body):
                try:
                    handler(json.loads(body))
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as exc:  # noqa: BLE001
                    log('sample_failed', level='ERROR', error=repr(exc))
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            self.channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message)
            self.channel.start_consuming()
