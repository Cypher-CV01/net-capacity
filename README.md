# NetCapacity — monitoramento de capacidade de uplinks GPON e HFC

Projeto de conclusão da disciplina **Arquiteturas de Computação em Nuvem** (AWS Academy Cloud Architecting).
Aplicação de três camadas em microserviços Docker na AWS, com mensageria (Amazon SQS), função serverless
(AWS Lambda), alta disponibilidade (ALB + Auto Scaling em 2 zonas) e observabilidade (Prometheus, Loki e Grafana).

| Entregável da atividade | Onde está |
|---|---|
| 0 — RACI da equipe | [`docs/raci.md`](docs/raci.md) |
| 1 — Desenho da arquitetura | [`docs/architecture.md`](docs/architecture.md) e [`docs/arquitetura.png`](docs/arquitetura.png) |
| 1 — Detalhamento do projeto, HA, monitoramento e observabilidade | este README |
| 2 — Código da aplicação | [`frontend/`](frontend), [`services/`](services), [`database/`](database), [`lambda/`](lambda) |
| 3 — Infraestrutura como código (Terraform) | [`infra/terraform/`](infra/terraform) |
| 4 — Logs e eventos da aplicação funcionando | [`evidencias/logs/`](evidencias/logs) |
| 5 — Prints de dashboards reais | [`evidencias/dashboards/`](evidencias/dashboards) |
| 6 — Apresentação | [`docs/apresentacao.pdf`](docs/apresentacao.pdf) |

## 1. Cenário e problema

Um provedor de internet opera mais de 400 elementos de acesso: OLTs GPON (Huawei MA5800-X15, ZTE C600) e CMTS HFC
(Cisco cBR-8, Casa CG100, Arris E6000). Cada equipamento sobe para a rede por **pares de uplinks 10G em caminhos
distintos** (rotas protegidas). Hoje, decidir quando expandir depende de um analista abrir gráficos de uplink
equipamento por equipamento: o processo é manual, lento e reativo.

**O NetCapacity resolve isso** coletando a utilização dos uplinks de forma leve (SNMP com MIBs públicas, só os
contadores das portas de uplink, sem onerar os equipamentos), consolidando GPON x HFC em painéis e tendências, e
**avisando automaticamente quando uma interface chega a 80%**, que é o ponto de planejar a expansão.

> Na nuvem, a demonstração usa um **coletor simulado** (40 equipamentos, 160 uplinks). O coletor SNMP real
> (`services/snmp_host.py`) roda apenas na rede de gerência autorizada da empresa; equipamentos reais nunca são
> expostos à nuvem acadêmica.

## 2. Arquitetura

Visão completa, fluxos e componentes: **[`docs/architecture.md`](docs/architecture.md)**.

```
Usuário ──HTTP──> ALB (2 AZs) ──> EC2 app #1 / app #2 (Auto Scaling 2–4)
                                   frontend · api · processor (+ agentes de observabilidade)
                                         │  ▲                       │
                     grava/consulta ─────┘  └── consome ── Amazon SQS (+DLQ) <── collector (EC2 ops)
                                   Amazon RDS PostgreSQL (subnets privadas)
EventBridge (1 h) ──> Lambda ──GET /api/interfaces (ALB)──> SNS ──> e-mail "AÇÃO NECESSÁRIA"
EC2 ops: Prometheus (descobre as instâncias) · Loki (logs) · Grafana (Prometheus + Loki + RDS + CloudWatch)
```

### Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React 18 + TypeScript + Vite, servido por Nginx |
| Backend | Python 3.12: FastAPI (API), processor e collector |
| Banco de dados | Amazon RDS PostgreSQL 16 |
| Mensageria | Amazon SQS (fila principal + dead-letter queue) |
| Serverless | AWS Lambda (Python) + Amazon EventBridge + Amazon SNS |
| Contêineres | Docker + Docker Compose em EC2 Amazon Linux 2023 |
| Rede e entrada | VPC em 2 AZs, Application Load Balancer, Security Groups por camada |
| Escala | EC2 Auto Scaling Group com política de CPU |
| IaC | Terraform (executado pelo AWS CloudShell) |
| Observabilidade | Prometheus, node-exporter, cAdvisor, Loki, Promtail, Grafana, Amazon CloudWatch |

### Microserviços

| Serviço | Responsabilidade | Escala |
|---|---|---|
| `frontend` | Painel web; proxy de `/api` e `/health` para a API | 1 por instância app (≥ 2) |
| `api` | Consultas (`/api/summary`, `/api/interfaces`, `/api/alerts`, `/api/lags`), `/health`, `/metrics` | 1 por instância app (≥ 2) |
| `processor` | Consome a fila, calcula utilização, grava no banco, gera alertas | 1 por instância app (consumidores concorrentes) |
| `collector` | Produz as amostras dos uplinks e publica na fila | 1 (instância ops) |
| `relatorio-capacidade` | Lambda: relatório periódico por e-mail | Gerenciado pela AWS |

## 3. Alta disponibilidade e escalabilidade

| Camada | Como fica disponível | O que acontece numa falha |
|---|---|---|
| Entrada | **Application Load Balancer** em 2 zonas, health check em `/health` a cada 15 s (passa por Nginx → API → banco) | Instância doente sai do balanceamento em ~45 s; o tráfego segue para a outra |
| Aplicação | **Auto Scaling Group** com mínimo 2 instâncias, uma em cada AZ; instâncias idênticas e sem estado | Instância perdida é substituída automaticamente (nova sobe em ~8 min); a outra atende sozinha enquanto isso |
| Escalabilidade | Política *target tracking*: CPU média de 60%, de 2 até 4 instâncias | Carga alta → novas instâncias entram no ALB e no Prometheus sozinhas |
| Atualização | *Instance refresh* rolling (mín. 50% saudáveis) | Deploy troca instâncias uma a uma, sem derrubar o site |
| Processamento | **Consumidores concorrentes** na fila SQS (um processor por instância) | Se um processor cai, o outro continua; mensagens não confirmadas voltam para a fila |
| Mensageria | **Amazon SQS** (serviço gerenciado, replicado em várias AZs), retenção de 1 dia, DLQ após 5 falhas | Se todos os processors param, a fila acumula e esvazia quando voltam, **sem perda de dados** |
| Banco | **Amazon RDS** com backup automático; opção `db_multi_az = true` cria réplica síncrona em outra AZ com failover automático | Com Multi-AZ, failover em 1–2 min; a API e o processor reconectam sozinhos |
| Serverless | Lambda, EventBridge e SNS são regionais e gerenciados | Sem servidor para cair |
| Contêineres | `restart: unless-stopped` em todos os serviços | Container que falha é reiniciado pelo Docker |

**Pontos únicos assumidos na demo (e como resolver em produção):**
- A instância **ops** (coletor e observabilidade) é única para economizar créditos. Se ela cair, o site continua no ar; só a coleta pausa (a fila guarda o que já foi publicado). Em produção: coletor em ECS/Fargate ou ASG de 1 instância, Prometheus/Loki gerenciados (Amazon Managed Prometheus, Grafana Cloud/Amazon Managed Grafana).
- O RDS roda Single-AZ por padrão (custo). Basta `db_multi_az = true` no `terraform.tfvars`.
- As instâncias ficam em subnets públicas (sem NAT Gateway, por custo), mas só aceitam HTTP vindo do ALB. Em produção: subnets privadas + NAT Gateway, imagens no Amazon ECR e HTTPS no ALB.

Testes de HA (roteiro da demo): `scripts/teste-ha.sh balanceamento` mostra o campo `served_by` alternando entre as
instâncias; `scripts/teste-ha.sh falha` encerra uma instância e mostra o site respondendo durante a substituição.

## 4. Monitoramento e observabilidade

| Pilar | Ferramenta | O que coleta |
|---|---|---|
| Métricas de infraestrutura | **node-exporter** (cada instância) | CPU, memória, disco, rede |
| Métricas de contêineres | **cAdvisor** (instâncias app) | CPU, memória e reinícios por container |
| Métricas da aplicação | **`/metrics`** na API (prometheus-fastapi-instrumentator) e no processor/collector (prometheus-client) | Requisições/s, latência p95, erros 5xx, amostras publicadas e gravadas, alertas gerados |
| Coleta de métricas | **Prometheus** (instância ops), descoberta automática das instâncias pela API da EC2 (tag `Role=app`), retenção de 7 dias | Instâncias novas do Auto Scaling entram no monitoramento sem editar configuração |
| Logs | Serviços Python escrevem **logs em JSON** (`level`, `event`); **Promtail** em cada instância envia os logs de todos os containers ao **Loki** | Busca por serviço, instância, nível e evento (ex.: `{event="capacity_alert"}`) |
| Serviços gerenciados | **Amazon CloudWatch** | ALB (requisições, alvos saudáveis, 5xx), SQS (fila e DLQ), RDS (CPU, conexões), Lambda (execuções, erros), logs da Lambda |
| Visualização | **Grafana** com datasources e dashboards provisionados como código (`observability/grafana/`) | Dashboards *Capacidade dos uplinks* e *Plataforma e alta disponibilidade* |
| Alerta de negócio | Lambda + SNS | E-mail com as interfaces ≥ 80% |

Dashboards:
- **NetCapacity — Capacidade dos uplinks** (dados do RDS): uplinks ≥ 80% agora, utilização média GPON x HFC no tempo, tráfego por tecnologia, top interfaces e tendência, tabela "ação necessária", alertas por minuto.
- **NetCapacity — Plataforma e alta disponibilidade** (Prometheus, CloudWatch e Loki): instâncias respondendo, alvos saudáveis no ALB, requisições por instância, latência p95, fila SQS e DLQ, produção x consumo, CPU/memória por instância e container, RDS, Lambda, volume de logs e alertas em tempo real.

## 5. Segurança

- Security groups por camada: só o ALB é público na porta 80; as instâncias app só aceitam HTTP do ALB e métricas da instância ops; o RDS só aceita conexões das instâncias; o Prometheus não é exposto.
- RDS em subnets privadas, sem IP público; SSL obrigatório na conexão.
- IMDSv2 obrigatório nas instâncias; SQS com criptografia gerenciada.
- Segredos (`terraform.tfvars`, `.env`, `*.tfstate`, chaves `.pem`) nunca vão para o Git (`.gitignore`).
- Na demo, SSH e Grafana ficam abertos (`my_ip_cidr = 0.0.0.0/0`) por praticidade; SSH só aceita chave e o Grafana exige senha forte. Em produção: SSM Session Manager no lugar de SSH e Grafana atrás de VPN/SSO.

## 6. Estrutura do repositório

```text
frontend/            React + Nginx
services/            API, processor, collector (+ coletor SNMP real e ponte legada)
database/            Schema PostgreSQL (migrações idempotentes)
lambda/              Função serverless de relatório
deploy/              docker-compose.app.yml (instâncias app) e docker-compose.ops.yml (instância ops)
observability/       Prometheus, Loki, Promtail, Grafana (datasources e dashboards)
infra/terraform/     IaC: VPC, SGs, ALB, Auto Scaling, EC2 ops, RDS, SQS, Lambda, SNS, EventBridge
scripts/             pausar, retomar, status, teste de HA, coleta de evidências
evidencias/          Logs exportados e prints (itens 4 e 5)
docs/                Arquitetura, RACI, apresentação
legacy/              Scripts SNMP originais (descoberta, amostragem, relatório Excel)
docker-compose.yml   Ambiente local de desenvolvimento (RabbitMQ no lugar do SQS)
```

## 7. Como implantar (AWS CloudShell)

Passo a passo completo em [`infra/README.md`](infra/README.md). Resumo:

```bash
cd ~/net-capacity/infra/terraform
cp terraform.tfvars.example terraform.tfvars && vim terraform.tfvars
terraform init && terraform plan -out plano.tfplan && terraform apply plano.tfplan
terraform output       # app_url (ALB), grafana_url, ...
```

Desenvolvimento local (sem AWS): `cp .env.example .env && docker compose up -d --build` → http://localhost:8081.

## 8. Custos (Learner Lab, aproximado)

Ligado: ~US$ 4,50/dia (3× t3.medium, ALB, RDS db.t3.micro, IPs públicos). Pausado com `scripts/pausar.sh`:
~US$ 0,80/dia (ALB e discos). `terraform destroy`: zero.

## 9. Limitações e próximos passos

- Coleta real por SNMP validada só fora da nuvem; integração contínua via VPN/Direct Connect é etapa futura.
- Capacidade N-1 considera a perda do maior membro do LAG, sem ler o estado LACP real.
- Previsão de data de saturação por regressão sobre o histórico (hoje: tendência visual no Grafana).
