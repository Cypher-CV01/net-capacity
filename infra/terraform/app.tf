# Camada de aplicação: Launch Template + Auto Scaling Group (mín. 2, uma por AZ).
# Cada instância roda em containers: frontend (Nginx/React), API, processor
# e os agentes de observabilidade (node-exporter, cAdvisor, Promtail).

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
}

resource "aws_launch_template" "app" {
  name_prefix            = "${var.project}-app-"
  image_id               = data.aws_ami.al2023.id
  instance_type          = var.app_instance_type
  key_name               = var.key_name
  vpc_security_group_ids = [aws_security_group.app.id]
  update_default_version = true

  # No Learner Lab não é possível criar roles IAM: usamos o perfil pronto.
  iam_instance_profile {
    name = "LabInstanceProfile"
  }

  # IMDSv2 obrigatório; hop limit 2 permite que os containers usem a role (SQS).
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size = 30
      volume_type = "gp3"
    }
  }

  user_data = base64encode(templatefile("${path.module}/user_data_app.sh.tftpl", {
    repo_url      = var.repo_url
    repo_branch   = var.repo_branch
    database_url  = local.database_url
    sqs_queue_url = aws_sqs_queue.samples.url
    region        = var.region
    threshold     = var.alert_threshold_percent
    loki_url      = "http://${aws_instance.ops.private_ip}:3100"
  }))

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name    = "${var.project}-app"
      Role    = "app" # usado pelo Prometheus para descobrir as instâncias
      Project = var.project
    }
  }
}

resource "aws_autoscaling_group" "app" {
  name                = "${var.project}-app-asg"
  vpc_zone_identifier = aws_subnet.public[*].id # uma subnet em cada AZ
  target_group_arns   = [aws_lb_target_group.app.arn]
  min_size            = var.app_min_size
  desired_capacity    = var.app_desired_capacity
  max_size            = var.app_max_size

  # EC2: substitui instâncias que pararam. Não usamos "ELB" para que uma falha
  # do banco não faça o ASG destruir todas as instâncias em sequência.
  health_check_type         = "EC2"
  health_check_grace_period = 600

  launch_template {
    id      = aws_launch_template.app.id
    version = aws_launch_template.app.latest_version
  }

  # Mudou o código de inicialização? Troca as instâncias uma a uma, sem derrubar o site.
  instance_refresh {
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 50
      instance_warmup        = 600
    }
  }

  tag {
    key                 = "Project"
    value               = var.project
    propagate_at_launch = true
  }

  lifecycle {
    ignore_changes = [desired_capacity] # o auto scaling ajusta sozinho
  }

  depends_on = [aws_instance.ops] # banco migrado e Loki no ar antes das instâncias
}

# Escalabilidade: mantém a CPU média perto do alvo, criando ou removendo instâncias.
resource "aws_autoscaling_policy" "cpu" {
  name                   = "${var.project}-cpu-target"
  autoscaling_group_name = aws_autoscaling_group.app.name
  policy_type            = "TargetTrackingScaling"

  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = var.cpu_target_percent
  }
}
