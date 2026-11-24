#!/bin/bash
# Resumo do ambiente (rodar no CloudShell).
P=${PROJECT:-netcapacity}
echo "== Instâncias =="
aws ec2 describe-instances --filters "Name=tag:Project,Values=$P" \
  "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query "Reservations[].Instances[].[Tags[?Key=='Name']|[0].Value,InstanceId,Placement.AvailabilityZone,State.Name]" \
  --output table
echo "== Alvos no Load Balancer =="
TG=$(aws elbv2 describe-target-groups --names "$P-app-tg" --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null)
[ -n "$TG" ] && aws elbv2 describe-target-health --target-group-arn "$TG" \
  --query "TargetHealthDescriptions[].[Target.Id,TargetHealth.State]" --output table
echo "== Fila SQS =="
for q in "$P-samples" "$P-samples-dlq"; do
  URL=$(aws sqs get-queue-url --queue-name "$q" --query QueueUrl --output text 2>/dev/null) && \
  echo "$q: $(aws sqs get-queue-attributes --queue-url "$URL" --attribute-names ApproximateNumberOfMessages --query 'Attributes.ApproximateNumberOfMessages' --output text) mensagens"
done
echo "== Banco =="
aws rds describe-db-instances --db-instance-identifier "$P-db" \
  --query "DBInstances[0].[DBInstanceStatus,MultiAZ,AvailabilityZone]" --output text 2>/dev/null
