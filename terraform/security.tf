resource "aws_security_group" "app" {
  name        = "${var.project}-app-sg"
  description = "EC2 da aplicacao"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP - frontend e API (via Nginx)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH somente do seu IP"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.my_ip_cidr]
  }

  ingress {
    description = "Grafana somente do seu IP"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = [var.my_ip_cidr]
  }

  egress {
    description = "Saida liberada (pacotes, imagens Docker, Git)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-app-sg" }
}

resource "aws_security_group" "db" {
  name        = "${var.project}-db-sg"
  description = "RDS PostgreSQL - acesso apenas a partir da EC2"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL vindo da EC2 da aplicacao"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  tags = { Name = "${var.project}-db-sg" }
}
