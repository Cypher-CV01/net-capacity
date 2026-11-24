# RACI da equipe

**R** = executa · **A** = responde pelo resultado (um por linha) · **C** = consultado · **I** = informado

| Integrante | Papel |
|---|---|
| **Luan Medeiros** | Infraestrutura e IaC (Terraform, AWS, alta disponibilidade) |
| **[Nome do integrante 2]** | Aplicação (frontend, backend, banco, mensageria, serverless) |
| **[Nome do integrante 3]** | Observabilidade (Prometheus, Loki, Grafana, evidências) |

| Etapa / entregável | Luan | Integrante 2 | Integrante 3 |
|---|---|---|---|
| Cenário, requisitos e funcionalidades | C | A/R | C |
| 0 — RACI da equipe | A/R | C | C |
| 1 — Desenho da arquitetura e README | A/R | C | C |
| 2 — Código: frontend (React + Nginx) | I | A/R | I |
| 2 — Código: API, collector e processor | C | A/R | C |
| 2 — Código: banco de dados (schema e migrações) | C | A/R | I |
| 2 — Mensageria (Amazon SQS + DLQ) | R | A/R | I |
| 2 — Função serverless (Lambda + SNS) | R | A/R | I |
| 3 — IaC: rede, segurança, RDS, SQS (Terraform) | A/R | C | I |
| 3 — IaC: ALB, Auto Scaling, instâncias (Terraform) | A/R | C | C |
| Alta disponibilidade e escalabilidade (testes) | A/R | C | C |
| Instrumentação (`/metrics`, logs em JSON) | C | R | A/R |
| Prometheus, Loki, Promtail, Grafana | C | I | A/R |
| 4 — Registros de logs e eventos | C | C | A/R |
| 5 — Prints dos dashboards | I | I | A/R |
| 6 — Apresentação (PPT/PDF) | R | R | R (A: Luan) |
| Demo ao vivo / gravada | R | R | R (A: Luan) |
| Envio da URL do repositório no Blackboard | R | R | R |

> Execução: por decisão do grupo, toda a implementação foi realizada no ambiente AWS do Luan, pelo AWS CloudShell, seguindo a divisão acima para revisão e apresentação de cada parte.
