#!/bin/bash
# Pausa o ambiente para economizar créditos do Learner Lab (rodar no CloudShell).
# Mantém: VPC, ALB, fila SQS, Lambda, dados do RDS. Desliga: instâncias, banco e agenda da Lambda.
set -u
P=${PROJECT:-netcapacity}

echo "> Auto Scaling da aplicação para 0 instâncias"
aws autoscaling update-auto-scaling-group --auto-scaling-group-name "$P-app-asg" \
  --min-size 0 --desired-capacity 0

echo "> Parando a instância ops"
OPS=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=$P-ops" "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].InstanceId" --output text)
[ -n "$OPS" ] && aws ec2 stop-instances --instance-ids $OPS >/dev/null

echo "> Parando o RDS"
aws rds stop-db-instance --db-instance-identifier "$P-db" >/dev/null 2>&1 || echo "  (RDS já parado ou parando)"

echo "> Desligando a agenda da Lambda"
aws events disable-rule --name "$P-agenda-relatorio"

echo "Pausado. O ALB continua cobrando ~US\$ 0,55/dia; para custo zero use: terraform destroy"
