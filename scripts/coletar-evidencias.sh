#!/bin/bash
# Exporta logs e eventos da aplicação para a pasta de evidências (item 4 da atividade).
# Rodar NA INSTÂNCIA OPS:  sudo bash /opt/netcapacity/scripts/coletar-evidencias.sh
# Depois, no CloudShell:   scp -i ~/.ssh/labsuser.pem -r ec2-user@IP_OPS:/tmp/evidencias/* evidencias/logs/
set -eu
OUT=/tmp/evidencias
mkdir -p "$OUT"
STAMP=$(date -u +%Y%m%dT%H%MZ)
END=$(date +%s)000000000
START=$(( $(date +%s) - 3600 ))000000000   # última hora

loki() {  # $1 = consulta LogQL, $2 = arquivo
  curl -sG "http://localhost:3100/loki/api/v1/query_range" \
    --data-urlencode "query=$1" --data-urlencode "start=$START" --data-urlencode "end=$END" \
    --data-urlencode "limit=2000" --data-urlencode "direction=backward" |
  jq -r '.data.result[] | .stream as $s | .values[] | "\(.[0] | tonumber / 1e9 | floor | strftime("%Y-%m-%dT%H:%M:%SZ")) [\($s.host)] [\($s.service)] \(.[1])"' \
    | sort > "$OUT/$2"
  echo "$2: $(wc -l < "$OUT/$2") linhas"
}

command -v jq >/dev/null || dnf install -y jq >/dev/null

loki '{service=~".+"}'                        "loki-todos-servicos-$STAMP.log"
loki '{service="collector"}'                  "loki-collector-$STAMP.log"
loki '{service="processor"}'                  "loki-processor-todas-instancias-$STAMP.log"
loki '{service="api"}'                        "loki-api-todas-instancias-$STAMP.log"
loki '{level=~"WARNING|ERROR"}'               "loki-alertas-e-erros-$STAMP.log"

# Alvos monitorados pelo Prometheus (prova da descoberta automática das instâncias)
curl -s http://localhost:9090/api/v1/targets |
  jq -r '.data.activeTargets[] | "\(.labels.job)\t\(.labels.instance)\t\(.health)"' \
  > "$OUT/prometheus-alvos-$STAMP.tsv"
echo "prometheus-alvos-$STAMP.tsv: $(wc -l < "$OUT/prometheus-alvos-$STAMP.tsv") alvos"
chmod -R a+r "$OUT"
echo "Arquivos em $OUT"
