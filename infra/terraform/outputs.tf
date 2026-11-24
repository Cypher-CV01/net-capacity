output "app_url" {
  description = "Aplicação (Application Load Balancer)"
  value       = "http://${aws_lb.app.dns_name}"
}

output "health_url" {
  description = "Health check da aplicação via ALB"
  value       = "http://${aws_lb.app.dns_name}/health"
}

output "grafana_url" {
  description = "Grafana (usuário admin + grafana_admin_password)"
  value       = "http://${aws_eip.ops.public_ip}:3000"
}

output "ops_ip" {
  description = "IP público da instância de operação"
  value       = aws_eip.ops.public_ip
}

output "ssh_ops" {
  description = "SSH na instância de operação"
  value       = "ssh -i ~/.ssh/labsuser.pem ec2-user@${aws_eip.ops.public_ip}"
}

output "asg_name" {
  description = "Auto Scaling Group da aplicação"
  value       = aws_autoscaling_group.app.name
}

output "sqs_queue_url" {
  value = aws_sqs_queue.samples.url
}

output "sqs_dlq_url" {
  value = aws_sqs_queue.samples_dlq.url
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
