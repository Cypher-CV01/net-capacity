# NetCapacity · MVP 0.1

Plataforma demonstrativa de monitoramento de capacidade de uplinks GPON/HFC. Reaproveita **sem alterar** os scripts do Capacity Monitor original em `legacy/` e adiciona microserviços Docker: React, FastAPI, PostgreSQL, RabbitMQ, collector simulado e processor.

## Executar no Windows / VS Code

Pré-requisitos: Docker Desktop com Compose, Git e VS Code.

```powershell
Copy-Item .env.example .env
# Edite .env e altere as senhas locais; mantenha DATABASE_URL e AMQP_URL consistentes.
docker compose up -d --build
docker compose ps
```

- Interface: http://localhost:8080
- API: http://localhost:8000/docs
- Health: http://localhost:8000/health
- RabbitMQ Management: http://localhost:15672 (usuário e senha do `.env`)

Na primeira inicialização, aguarde os healthchecks e ~20 segundos pelas primeiras amostras. O frontend atualiza a cada 10 segundos.

```powershell
docker compose logs -f collector processor api
docker compose down
# Atenção: o comando abaixo apaga o banco local do MVP:
# docker compose down -v
```

## Dados simulados e SNMP real

- **Simulado:** padrão e executável no Compose. Gera amostras sintéticas de 8 dispositivos e 16 interfaces, variando utilização e disparando alertas a partir de 80%.
- **SNMP real:** os três scripts originais foram preservados em `legacy/`: `capacity_monitor.py` (descoberta), `capacity_sampler.py` (amostras), `capacity_analyzer.py` (relatório). O código usa SNMPv2c, arquivos CSV e inventário; requer acesso autorizado à rede de gestão e revisão de configuração.
- **Ponte SNMP:** `services/import_legacy.py` converte snapshots de contadores do CSV legado em taxas bps e publica no RabbitMQ. Ela é executada separadamente em uma máquina com acesso autorizado e requer `AMQP_URL` acessível. O adaptador não faz polling, não suporta stream contínuo e não foi validado com equipamentos reais. Alterar `COLLECTION_MODE=snmp` no Docker **não** ativa coleta real: o collector encerra com mensagem explícita.

Para testar o legado separadamente no Windows, crie `legacy/config/devices.csv` baseado no exemplo, configure `.env` local com credenciais read-only, instale `legacy/requirements.txt` em um ambiente virtual Python compatível e execute os comandos de ajuda/uso indicados pelos scripts. **Nunca envie IPs internos, comunidades, senhas, inventário real ou logs sensíveis ao GitHub.**

### Importar amostras reais já coletadas (etapa experimental)

O arquivo legado `output/samples.csv` contém **contadores de octetos**, não taxas. O adaptador exige duas amostras por interface, calcula `bps = delta_octets * 8 / delta_segundos`, descarta deltas inválidos e não transmite IPs/aliases. Para executar, use Python no Windows com `pika` instalado e `AMQP_URL` apontando para um RabbitMQ autorizado. O RabbitMQ deste Compose só expõe o painel de gestão na porta 15672; para importar a partir do host, configure uma porta AMQP local **restrita a 127.0.0.1** (`127.0.0.1:5672:5672`) no serviço `rabbitmq` e use `amqp://usuario:senha@localhost:5672/%2F`. Não publique essa porta na Internet.

```powershell
$env:AMQP_URL = 'amqp://netcapacity:SUA_SENHA@localhost:5672/%2F'
python services/import_legacy.py C:\caminho\samples.csv C:\caminho\uplinks.json
```

A importação reenvia todas as amostras calculáveis a cada execução e pode gerar duplicatas. Use apenas em laboratório até haver controle de checkpoint e idempotência.

## O que está funcionando no MVP

- React/TypeScript com cards, filtros GPON/HFC, tabela de interfaces e indicação de 80%.
- FastAPI com `/health`, `/api/summary`, `/api/interfaces`, `/api/alerts` e Swagger.
- RabbitMQ durável, processador de eventos e banco PostgreSQL.
- Dados sintéticos marcados como `simulated`.
- CI com sintaxe Python, testes unitários, validação Compose e build.
- Preservação integral dos scripts `.py` e requirements originais.

## Pendências técnicas

1. Testar a ponte CSV SNMP com dados anonimizados e RabbitMQ acessível, automatizar importação incremental e suportar contadores com discontinuidades.
2. Validar nomes/índices IF-MIB e reset de contadores 64-bit; a ponte CSV calcula taxa entre duas amostras, enquanto o MVP simula bps diretamente.
3. Modelar pares redundantes, LAG e capacidade N-1; não somar capacidades sem verificar a topologia.
4. Adicionar testes de integração, segurança/autenticação, retenção e agregação histórica.
5. Acrescentar Grafana/Prometheus/Loki, Terraform, CD e documentação de alta disponibilidade.
6. Parametrizar o limiar na API (o processador usa `ALERT_THRESHOLD_PERCENT`, mas o resumo usa 80 fixo neste MVP).

## Estrutura

```text
legacy/                 Scripts Python originais (sem dados corporativos)
services/               API, collector simulado, processor, adaptador futuro
frontend/               React + Vite + Nginx
 database/              PostgreSQL schema
 docs/                  Arquitetura e RACI
 tests/                 Testes iniciais
 .github/workflows/      CI
 docker-compose.yml      Ambiente de desenvolvimento
```

## GitHub

Crie um repositório privado chamado `NetCapacity` na sua conta (nenhum repositório foi criado automaticamente):

```powershell
git init
git add .
git commit -m "feat: bootstrap NetCapacity MVP"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/NetCapacity.git
git push -u origin main
```

Antes de publicar, revise o conteúdo de `legacy/` e substitua qualquer referência operacional sensível remanescente. Não coloque o ZIP original nem arquivos `.env` no repositório.

## v0.2 — SNMP via VPN no Windows + LAG

See [`docs/v02-windows-snmp.md`](docs/v02-windows-snmp.md). The original v0.1 stack and `legacy/` scripts remain intact. Frontend uses host port **8081**, as validated on Windows. The Docker RabbitMQ service additionally binds AMQP only to `127.0.0.1:5672` for the optional host collector. Database migration `database/002_lag.sql` must be applied to existing volumes before using `/api/lags`.
