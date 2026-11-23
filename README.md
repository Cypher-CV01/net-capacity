# Infraestrutura (IaC) — NetCapacity na AWS

Responsável: **Pessoa B** · Ferramenta: **Terraform** · Ambiente: **AWS Academy Learner Lab (us-east-1)**

## O que o Terraform cria

| Arquivo | Recursos |
|---|---|
| `vpc.tf` | VPC 10.0.0.0/16, 2 subnets públicas + 2 privadas (2 AZs), Internet Gateway, rotas |
| `security.tf` | SG da EC2 (80 aberto; 22 e 3000 só do seu IP) e SG do RDS (5432 só a partir da EC2) |
| `rds.tf` | Amazon RDS PostgreSQL 16 `db.t3.micro` nas subnets privadas (Multi-AZ opcional) |
| `ec2.tf` | EC2 Amazon Linux 2023 `t3.large` + Elastic IP; `user_data` instala Docker, clona o repo, cria as tabelas no RDS e sobe o `deploy/docker-compose.aws.yml` |
| `lambda.tf` | Lambda `relatorio-capacidade` + regra EventBridge + tópico SNS com assinatura por e-mail |
| `outputs.tf` | URLs da aplicação, Grafana, SSH e endpoint do RDS |

Restrições do Learner Lab já tratadas: não cria IAM (usa `LabRole` e `LabInstanceProfile`), usa a key pair `vockey`, não usa NAT Gateway, usa Elastic IP porque a EC2 para ao fim de cada sessão.

## Pré-requisitos (Windows)

```powershell
winget install Hashicorp.Terraform
winget install Amazon.AWSCLI
# feche e reabra o terminal
terraform -version
aws --version
```

## Passo a passo

1. **Inicie o Learner Lab**, clique em *Start Lab* e espere a bolinha ficar verde.
2. **Credenciais.** Em *AWS Details → AWS CLI → Show*, copie o bloco inteiro para `%UserProfile%\.aws\credentials`. Repita a cada nova sessão.
   - Baixe também o `labsuser.pem` (*Download PEM*).

   ```powershell
   aws sts get-caller-identity   # deve mostrar a conta e a role voclabs
   ```

3. **Variáveis:**

   ```powershell
   cd infra\terraform
   Copy-Item terraform.tfvars.example terraform.tfvars
   notepad terraform.tfvars    # my_ip_cidr, db_password, alert_email, repo_url
   ```

4. **Criar a infra** (o RDS leva de 5 a 10 minutos):

   ```powershell
   terraform init
   terraform fmt
   terraform validate
   terraform plan -out plano.tfplan
   terraform apply plano.tfplan
   terraform output
   ```

5. **Confirmar a assinatura do SNS** no e-mail ("AWS Notification - Subscription Confirmation").
6. **Validar:**
   - Abrir o `app_url`, cerca de 5 minutos depois do apply, porque o build dos containers demora.
   - Testar a API:

     ```powershell
     Invoke-RestMethod "$(terraform output -raw health_url)"
     ```

   - Testar a Lambda na hora, sem esperar o agendamento:

     ```powershell
     aws lambda invoke --function-name netcapacity-relatorio-capacidade saida.json; Get-Content saida.json
     ```

   - Se algo falhar na EC2, ver o log:

     ```powershell
     ssh -i labsuser.pem ec2-user@<IP>
     sudo tail -100 /var/log/netcapacity-bootstrap.log
     cd /opt/netcapacity; docker compose -f deploy/docker-compose.aws.yml ps
     ```

7. **Fim da sessão:** pode só encerrar o lab, porque EC2 e RDS param sozinhos e voltam na próxima sessão com o mesmo IP. Para zerar tudo e economizar orçamento, use `terraform destroy`.

## Fases (para não depender da Pessoa A)

- **Fase 1** (`repo_url = ""`): sobe VPC, RDS, EC2 com Docker, Lambda e SNS. A Lambda vai falhar ao chamar a API, o que é esperado porque ainda não há aplicação.
- **Fase 2**: com o repositório público no GitHub contendo `deploy/docker-compose.aws.yml`, preencha `repo_url` e rode `terraform apply`. A EC2 é recriada e sobe a aplicação sozinha. O IP não muda, porque o Elastic IP é reaproveitado.

## Alta disponibilidade (para o README principal e os slides)

O que a demo já tem:
- Subnets em 2 AZs.
- RDS gerenciado, com backup automático.
- Fila durável no RabbitMQ: se o processor cair, as mensagens esperam na fila.
- `restart: unless-stopped` nos containers.
- Lambda e SNS são serviços gerenciados, que já são HA.

Evolução para produção:
- Application Load Balancer + Auto Scaling Group (mínimo 2 EC2, uma por AZ) para o frontend e a API.
- `db_multi_az = true` no RDS.
- Amazon MQ (RabbitMQ gerenciado, em cluster) no lugar do container.
- Ou migrar os containers para ECS/EKS.
