variable "region" {
  description = "Região da AWS (o Learner Lab permite us-east-1 e us-west-2)"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Prefixo usado no nome dos recursos"
  type        = string
  default     = "netcapacity"
}

variable "my_ip_cidr" {
  description = "Seu IP público em /32 (para SSH e Grafana). Descubra em https://checkip.amazonaws.com"
  type        = string
}

variable "instance_type" {
  description = "Tipo da EC2 da aplicação (t3.large comporta app + observabilidade)"
  type        = string
  default     = "t3.large"
}

variable "key_name" {
  description = "Key pair para SSH. O Learner Lab já cria a 'vockey' (baixe labsuser.pem em AWS Details)"
  type        = string
  default     = "vockey"
}

variable "repo_url" {
  description = "URL pública do repositório Git. Vazio = só prepara a EC2 com Docker (sem subir a aplicação)"
  type        = string
  default     = ""
}

variable "repo_branch" {
  description = "Branch a ser clonada"
  type        = string
  default     = "main"
}

variable "db_username" {
  description = "Usuário master do RDS"
  type        = string
  default     = "netcapacity"
}

variable "db_password" {
  description = "Senha do RDS e do RabbitMQ (somente letras e números, 12+ caracteres)"
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[A-Za-z0-9]{12,}$", var.db_password))
    error_message = "Use 12 ou mais caracteres, apenas letras e números (evita problemas na URL de conexão)."
  }
}

variable "db_multi_az" {
  description = "RDS Multi-AZ (alta disponibilidade). false na demo para economizar orçamento"
  type        = bool
  default     = false
}

variable "alert_email" {
  description = "E-mail que receberá o relatório de capacidade (confirme a assinatura SNS no e-mail)"
  type        = string
}

variable "alert_threshold_percent" {
  description = "Limiar de utilização que indica necessidade de expansão"
  type        = number
  default     = 80
}

variable "report_schedule" {
  description = "Frequência da Lambda de relatório (EventBridge). rate(1 hour) na demo; cron diário em produção"
  type        = string
  default     = "rate(1 hour)"
}
