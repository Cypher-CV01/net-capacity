data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.app.id]
  key_name               = var.key_name

  # No Learner Lab não é possível criar roles IAM: usamos o perfil pronto.
  iam_instance_profile = "LabInstanceProfile"

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    repo_url    = var.repo_url
    repo_branch = var.repo_branch
    db_host     = aws_db_instance.postgres.address
    db_user     = var.db_username
    db_password = var.db_password
    threshold   = var.alert_threshold_percent
  })

  # Mudou o repo_url ou a senha? A EC2 é recriada e sobe tudo de novo sozinha.
  user_data_replace_on_change = true

  tags = { Name = "${var.project}-app" }
}

# IP fixo: no Learner Lab a EC2 para ao fim da sessão e o IP público mudaria.
resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"
  tags     = { Name = "${var.project}-app-eip" }
}
