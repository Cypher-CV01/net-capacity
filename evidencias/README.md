# Evidências do projeto (itens 4 e 5 da atividade)

| Pasta | Conteúdo | Como gerar |
|---|---|---|
| `logs/` | Logs e eventos reais da aplicação exportados do Loki (todas as instâncias) e lista de alvos do Prometheus | `scripts/coletar-evidencias.sh` na instância ops |
| `dashboards/` | Prints dos dashboards do Grafana (Capacidade e Plataforma) e do painel web | Captura de tela |
| `infra/` | Saída do `terraform apply`/`output`, console AWS (ALB com 2 alvos saudáveis, Auto Scaling, SQS, RDS, Lambda) e e-mail do SNS | Captura de tela / copiar do terminal |
| `demo/` | Teste de alta disponibilidade (balanceamento e falha de instância) e resiliência da fila | `scripts/teste-ha.sh` |

Eventos registrados em JSON pelos serviços (filtráveis no Loki pelo label `event`):

| Evento | Serviço | Significado |
|---|---|---|
| `collector_started` | collector | Coletor iniciou (quantidade de equipamentos e interfaces) |
| `cycle_published` | collector | Ciclo de coleta publicado na fila SQS |
| `processor_ready` | processor | Processor conectado à fila |
| `capacity_alert` | processor | Interface atingiu o limiar de expansão (≥ 80%) |
| `sample_failed` | processor | Falha ao processar uma amostra (será reprocessada) |
| `relatorio_capacidade` | Lambda (CloudWatch Logs) | Execução do relatório periódico |
