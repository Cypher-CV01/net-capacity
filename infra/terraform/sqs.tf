# Mensageria gerenciada: Amazon SQS (replicada em várias zonas pela própria AWS).
# O coletor publica amostras; os processadores das instâncias consomem em paralelo.

resource "aws_sqs_queue" "samples_dlq" {
  name                      = "${var.project}-samples-dlq"
  message_retention_seconds = 1209600 # 14 dias para investigar falhas
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "samples" {
  name                       = "${var.project}-samples"
  visibility_timeout_seconds = 60    # tempo para um processador tratar a mensagem
  receive_wait_time_seconds  = 20    # long polling: menos requisições vazias
  message_retention_seconds  = 86400 # 1 dia
  sqs_managed_sse_enabled    = true

  # Após 5 tentativas com erro, a mensagem vai para a fila de "mensagens mortas"
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.samples_dlq.arn
    maxReceiveCount     = 5
  })
}
