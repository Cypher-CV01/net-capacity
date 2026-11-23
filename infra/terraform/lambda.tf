# Função serverless: relatório "ação necessária" (interfaces >= limiar).
# EventBridge dispara -> Lambda chama a API -> publica no SNS -> e-mail.

data "aws_iam_role" "lab" {
  name = "LabRole" # role pronta do Learner Lab (não podemos criar roles)
}

data "archive_file" "relatorio" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambda/relatorio_capacidade"
  output_path = "${path.module}/build/relatorio_capacidade.zip"
}

resource "aws_sns_topic" "alertas" {
  name = "${var.project}-alertas-capacidade"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alertas.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_lambda_function" "relatorio" {
  function_name    = "${var.project}-relatorio-capacidade"
  role             = data.aws_iam_role.lab.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.relatorio.output_path
  source_code_hash = data.archive_file.relatorio.output_base64sha256
  timeout          = 30
  memory_size      = 128

  environment {
    variables = {
      API_URL                 = "http://${aws_eip.app.public_ip}"
      SNS_TOPIC_ARN           = aws_sns_topic.alertas.arn
      ALERT_THRESHOLD_PERCENT = tostring(var.alert_threshold_percent)
    }
  }
}

resource "aws_cloudwatch_log_group" "relatorio" {
  name              = "/aws/lambda/${aws_lambda_function.relatorio.function_name}"
  retention_in_days = 7
}

resource "aws_cloudwatch_event_rule" "agenda" {
  name                = "${var.project}-agenda-relatorio"
  description         = "Dispara o relatório de capacidade"
  schedule_expression = var.report_schedule
}

resource "aws_cloudwatch_event_target" "lambda" {
  rule = aws_cloudwatch_event_rule.agenda.name
  arn  = aws_lambda_function.relatorio.arn
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.relatorio.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.agenda.arn
}
