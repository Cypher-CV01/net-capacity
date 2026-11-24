#!/bin/bash
# Demonstração de alta disponibilidade (rodar no CloudShell, dentro de infra/terraform ou passando a URL).
#   ./scripts/teste-ha.sh balanceamento   -> mostra o ALB alternando entre as instâncias
#   ./scripts/teste-ha.sh falha           -> derruba uma instância e mostra o site continuando no ar
set -u
P=${PROJECT:-netcapacity}
URL=${APP_URL:-http://$(aws elbv2 describe-load-balancers --names "$P-alb" --query 'LoadBalancers[0].DNSName' --output text)}

balanceamento() {
  echo "Requisições para $URL/health (veja o campo served_by mudar):"
  for i in $(seq 1 10); do
    curl -s "$URL/health"; echo
    sleep 0.5
  done
}

falha() {
  VITIMA=$(aws ec2 describe-instances --filters "Name=tag:Role,Values=app" "Name=tag:Project,Values=$P" \
    "Name=instance-state-name,Values=running" --query "Reservations[0].Instances[0].InstanceId" --output text)
  echo "Encerrando a instância $VITIMA para simular uma falha..."
  echo "(o Auto Scaling tira a instância do ALB, encerra e cria outra no lugar)"
  aws autoscaling terminate-instance-in-auto-scaling-group --instance-id "$VITIMA" \
    --no-should-decrement-desired-capacity >/dev/null
  echo "Testando o site durante a falha (Ctrl+C para parar):"
  while true; do
    printf '%s  ' "$(date +%T)"
    curl -s -o /dev/null -w "HTTP %{http_code}  " "$URL/health"
    curl -s "$URL/health"; echo
    sleep 3
  done
}

case "${1:-balanceamento}" in
  balanceamento) balanceamento ;;
  falha) falha ;;
  *) echo "uso: $0 [balanceamento|falha]"; exit 1 ;;
esac
