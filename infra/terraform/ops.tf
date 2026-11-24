# Instância de operação: coletor (produtor da fila) e stack de observabilidade
# (Prometheus, Loki, Grafana). Também aplica as migrações do banco na criação.

locals {
  database_url = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.address}:5432/netcapacity"
}

resource "aws_instance" "ops" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.ops_instance_type
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.ops.id]
  key_name               = var.key_name
  iam_instance_profile   = "LabInstanceProfile"

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/user_data_ops.sh.tftpl", {
    repo_url               = var.repo_url
    repo_branch            = var.repo_branch
    database_url           = local.database_url
    db_host                = aws_db_instance.postgres.address
    db_user                = var.db_username
    db_password            = var.db_password
    sqs_queue_url          = aws_sqs_queue.samples.url
    region                 = var.region
    grafana_admin_password = var.grafana_admin_password
    simulated_devices      = var.simulated_devices
    poll_interval_seconds  = var.poll_interval_seconds
  })
  user_data_replace_on_change = true

  tags = {
    Name = "${var.project}-ops"
    Role = "ops"
  }
}

resource "aws_eip" "ops" {
  instance = aws_instance.ops.id
  domain   = "vpc"
  tags     = { Name = "${var.project}-ops-eip" }
}
