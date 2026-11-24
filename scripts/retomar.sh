#!/bin/bash
# Religa o ambiente pausado (rodar no CloudShell). Leva ~10-15 min até tudo ficar saudável.
set -u
P=${PROJECT:-netcapacity}

echo "> Ligando o RDS (aguarde ~5-10 min)"
aws rds start-db-instance --db-instance-identifier "$P-db" >/dev/null 2>&1 || echo "  (RDS já ligado ou ligando)"
aws rds wait db-instance-available --db-instance-identifier "$P-db"

echo "> Ligando a instância ops"
OPS=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=$P-ops" "Name=instance-state-name,Values=stopped" \
  --query "Reservations[].Instances[].InstanceId" --output text)
[ -n "$OPS" ] && aws ec2 start-instances --instance-ids $OPS >/dev/null

echo "> Auto Scaling da aplicação de volta para 2 instâncias"
aws autoscaling update-auto-scaling-group --auto-scaling-group-name "$P-app-asg" \
  --min-size 2 --desired-capacity 2

echo "> Ligando a agenda da Lambda"
aws events enable-rule --name "$P-agenda-relatorio"

echo "Pronto. As instâncias da aplicação levam ~8 min para construir os containers."
echo "Acompanhe: aws elbv2 describe-target-health --target-group-arn \$(aws elbv2 describe-target-groups --names $P-app-tg --query 'TargetGroups[0].TargetGroupArn' --output text) --query 'TargetHealthDescriptions[].TargetHealth.State'"
