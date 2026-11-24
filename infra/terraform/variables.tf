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
  description = "Quem pode acessar SSH e Grafana. Seu IP em /32 ou 0.0.0.0/0 (demo, acesso de qualquer lugar)"
  type        = string
}

variable "key_name" {
  description = "Key pair para SSH. O Learner Lab já cria a 'vockey' (labsuser.pem em AWS Details)"
  type        = string
  default     = "vockey"
}

variable "repo_url" {
  description = "URL pública (https) do repositório Git clonado pelas instâncias"
  type        = string
}

variable "repo_branch" {
  description = "Branch a ser clonada"
  type        = string
  default     = "main"
}

# ---------- Camada de aplicação (alta disponibilidade) ----------
variable "app_instance_type" {
  description = "Tipo das instâncias da aplicação (Auto Scaling Group atrás do ALB)"
  type        = string
  default     = "t3.medium"
}

variable "app_min_size" {
  description = "Mínimo de instâncias da aplicação (2 = uma por zona de disponibilidade)"
  type        = number
  default     = 2
}

variable "app_desired_capacity" {
  description = "Quantidade inicial de instâncias da aplicação"
  type        = number
  default     = 2
}

variable "app_max_size" {
  description = "Máximo de instâncias da aplicação (limite do auto scaling)"
  type        = number
  default     = 4
}

variable "cpu_target_percent" {
  description = "CPU média alvo do Auto Scaling: acima disso cria instâncias, abaixo remove"
  type        = number
  default     = 60
}

# ---------- Instância de operação (coletor + observabilidade) ----------
variable "ops_instance_type" {
  description = "Tipo da instância de operação (coletor, Prometheus, Loki, Grafana)"
  type        = string
  default     = "t3.medium"
}

variable "grafana_admin_password" {
  description = "Senha do usuário admin do Grafana (somente letras e números, 12+ caracteres)"
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[A-Za-z0-9]{12,}$", var.grafana_admin_password))
    error_message = "Use 12 ou mais caracteres, apenas letras e números."
  }
}

variable "simulated_devices" {
  description = "Quantidade de equipamentos simulados (cada um com 4 uplinks de 10G)"
  type        = number
  default     = 40
}

variable "poll_interval_seconds" {
  description = "Intervalo de coleta do simulador, em segundos"
  type        = number
  default     = 60
}

# ---------- Banco de dados ----------
variable "db_username" {
  description = "Usuário master do RDS"
  type        = string
  default     = "netcapacity"
}

variable "db_password" {
  description = "Senha do RDS (somente letras e números, 12+ caracteres)"
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[A-Za-z0-9]{12,}$", var.db_password))
    error_message = "Use 12 ou mais caracteres, apenas letras e números (evita problemas na URL de conexão)."
  }
}

variable "db_multi_az" {
  description = "RDS Multi-AZ (réplica síncrona em outra zona, failover automático). Dobra o custo do banco"
  type        = bool
  default     = false
}

# ---------- Relatório serverless ----------
variable "alert_email" {
  description = "E-mail que recebe o relatório de capacidade (confirme a assinatura SNS)"
  type        = string
}

variable "alert_threshold_percent" {
  description = "Limiar de utilização que indica necessidade de expansão"
  type        = number
  default     = 80
}

variable "report_schedule" {
  description = "Frequência da Lambda de relatório. rate(1 hour) na demo; cron diário em produção"
  type        = string
  default     = "rate(1 hour)"
}
