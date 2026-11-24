# Infraestrutura como código — NetCapacity v0.2

Terraform executado pelo **AWS CloudShell** no AWS Academy Learner Lab (`us-east-1`).

## Recursos criados

| Arquivo | Recursos |
|---|---|
| `vpc.tf` | VPC `10.0.0.0/16`, 2 subnets públicas + 2 privadas (2 AZs), Internet Gateway, rotas |
| `security.tf` | Security groups por camada: ALB, app, ops, banco (regras mínimas entre eles) |
| `alb.tf` | Application Load Balancer, target group (health check `/health`), listener HTTP 80 |
| `app.tf` | Launch template (Amazon Linux 2023, IMDSv2) + Auto Scaling Group (mín 2, máx 4, 2 AZs) + política de CPU 60% + instance refresh |
| `ops.tf` | EC2 de operação (coletor, Prometheus, Loki, Grafana) + Elastic IP; aplica as migrações do banco |
| `rds.tf` | RDS PostgreSQL 16 `db.t3.micro` em subnets privadas (Multi-AZ opcional) |
| `sqs.tf` | Fila `netcapacity-samples` (long polling, criptografada) + DLQ |
| `lambda.tf` | Lambda de relatório + regra EventBridge + tópico SNS com e-mail |
| `user_data_app.sh.tftpl` / `user_data_ops.sh.tftpl` | Inicialização das instâncias (Docker, clone do repositório, `.env`, `docker compose up`) |

Restrições do Learner Lab atendidas: sem criação de IAM (usa `LabRole` e `LabInstanceProfile`), key pair `vockey`,
sem NAT Gateway, tipos de instância permitidos.

## Implantação (CloudShell)

```bash
# Uma vez: Terraform em ~/bin e providers em /tmp (ver guia do CloudShell)
cd ~/net-capacity && git pull
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars      # preencher senhas, e-mail e my_ip_cidr
terraform init
terraform validate
terraform plan -out plano.tfplan                  # esperado na criação: 47 to add
terraform apply plano.tfplan && rm plano.tfplan   # ~15 min (RDS) + ~8 min de build nas instâncias
terraform output
```

Após o `apply`: confirmar o e-mail do SNS, aguardar os 2 alvos ficarem `healthy` (`../../scripts/status.sh`)
e abrir `app_url` e `grafana_url`.

## Operação

| Ação | Comando (na raiz do repositório) |
|---|---|
| Ver o estado do ambiente | `./scripts/status.sh` |
| Pausar ao fim do dia | `./scripts/pausar.sh` |
| Retomar | `./scripts/retomar.sh` |
| Demonstrar balanceamento | `./scripts/teste-ha.sh balanceamento` |
| Demonstrar falha de instância | `./scripts/teste-ha.sh falha` |
| Publicar código novo nas instâncias app | `git push` e depois `aws autoscaling start-instance-refresh --auto-scaling-group-name netcapacity-app-asg` |
| Atualizar a instância ops | SSH → `cd /opt/netcapacity && sudo git pull && sudo docker compose -f deploy/docker-compose.ops.yml --env-file .env up -d --build` |
| Apagar tudo (custo zero) | `cd infra/terraform && terraform destroy` |

Logs de inicialização de qualquer instância: `sudo tail -f /var/log/netcapacity-bootstrap.log`.
