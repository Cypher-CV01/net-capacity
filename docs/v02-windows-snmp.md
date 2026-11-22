# NetCapacity v0.2 — Windows / Cisco VPN / Huawei MA5800-X15

## Architecture

- Docker Compose: simulated collector, RabbitMQ, processor, PostgreSQL, API, frontend.
- Windows host: optional `services/snmp_host.py` (SNMPv2c read-only, IF-MIB) using the already connected authorized VPN.
- Windows collector sends **derived RX/TX bps only** to RabbitMQ on `127.0.0.1:5672`.
- No management IPs, SNMP community or inventory are included in messages. No VPN routing changes.
- `legacy/` contains the original Python scripts unchanged; discovery of verified `ifIndex` should be done using the legacy tool and checked against the equipment before configuration.

## Setup

1. Copy `.env.example` to `.env` and set matching DB/AMQP credentials. Preserve the existing `.env` when upgrading; do not run `docker compose down -v`.
2. Start Compose: `docker compose up -d --build`.
3. Copy `config/snmp-devices.example.json` to `config/snmp-devices.json`; enter **authorized** IP, verified `ifIndex`, physical interface name and speed. The example IP 192.0.2.10 is documentation-only.
4. Create a Python virtual environment on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r services\requirements-snmp-host.txt
```

5. While connected to Cisco VPN, set local environment variables in the PowerShell session, never commit or paste them:

```powershell
$env:SNMP_INVENTORY = 'config/snmp-devices.json'
$env:SNMP_COMMUNITY = Read-Host 'SNMPv2c community'
$env:AMQP_URL = 'amqp://netcapacity:YOUR_LOCAL_RABBITMQ_PASSWORD@127.0.0.1:5672/%2F'
$env:SNMP_POLL_SECONDS = '60'
.\.venv\Scripts\python.exe services\snmp_host.py
```

6. Wait for two successful polls and check `/api/interfaces` for `source: snmp`. `source: simulated` remains separate. Stop the host collector with Ctrl+C.

**Security:** SNMPv2c does not encrypt the community. Use it only on approved management paths with ACLs. Do not store real inventory or credentials in Git. The v0.2 collector is a lab integration and not yet production-ready: it does not discover LAG/LACP membership, perform SNMPv3, coordinate multiple pollers or persist counter baselines across restarts. The first sample after restarting is deliberately ignored.

## LAG/N-1

1. After actual samples exist, apply the database migration (safe for existing PostgreSQL volume):

```powershell
Get-Content database\002_lag.sql -Raw | docker compose exec -T db psql -U netcapacity -d netcapacity
```

2. Review `config/lags.example.sql` and substitute the actual LAG identifier and verified member ifIndexes. Run it with the same command pattern.
3. `GET http://localhost:8000/api/lags` returns nominal and N-1 capacity estimates. The API returns `null` utilization if any member has never been sampled. The N-1 model assumes all configured members are forwarding and the surviving members can absorb the traffic. It is **not** a substitute for reading actual LACP state, topology or validating path redundancy. The current version does not validate sample freshness, so avoid operational decisions until freshness checks are added.

## Validation

```powershell
docker compose ps
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/summary
Invoke-RestMethod http://localhost:8000/api/lags
```

Do not publish the local AMQP port beyond loopback. If Docker cannot bind 5672, check which local service is using it before changing the port mapping and host URL together.
