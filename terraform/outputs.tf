output "app_url" {
  description = "Interface web (frontend)"
  value       = "http://${aws_eip.app.public_ip}"
}

output "health_url" {
  description = "Health check da API (via Nginx)"
  value       = "http://${aws_eip.app.public_ip}/health"
}

output "grafana_url" {
  description = "Grafana (Pessoa C sobe a stack de observabilidade)"
  value       = "http://${aws_eip.app.public_ip}:3000"
}

output "ssh_command" {
  description = "Acesso SSH (labsuser.pem baixado em AWS Details)"
  value       = "ssh -i labsuser.pem ec2-user@${aws_eip.app.public_ip}"
}

output "rds_endpoint" {
  description = "Endpoint privado do PostgreSQL"
  value       = aws_db_instance.postgres.address
}

output "lambda_name" {
  value = aws_lambda_function.relatorio.function_name
}

output "sns_topic_arn" {
  value = aws_sns_topic.alertas.arn
}
