# Quatro security groups, um por camada. As regras ficam em recursos separados
# porque app e ops se referenciam (Prometheus -> app, Promtail -> Loki).

resource "aws_security_group" "alb" {
  name        = "${var.project}-alb-sg"
  description = "Application Load Balancer - entrada publica HTTP"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${var.project}-alb-sg" }
}

resource "aws_security_group" "app" {
  name        = "${var.project}-app-sg"
  description = "Instancias da aplicacao - so recebem trafego do ALB"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${var.project}-app-sg" }
}

resource "aws_security_group" "ops" {
  name        = "${var.project}-ops-sg"
  description = "Instancia de operacao - coletor e observabilidade"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${var.project}-ops-sg" }
}

resource "aws_security_group" "db" {
  name        = "${var.project}-db-sg"
  description = "RDS PostgreSQL - acesso apenas das instancias"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${var.project}-db-sg" }
}

# ---------- ALB ----------
resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTP da internet"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

# ---------- Aplicação ----------
resource "aws_vpc_security_group_ingress_rule" "app_http_from_alb" {
  security_group_id            = aws_security_group.app.id
  description                  = "HTTP somente vindo do ALB"
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
}

resource "aws_vpc_security_group_ingress_rule" "app_ssh" {
  security_group_id = aws_security_group.app.id
  description       = "SSH (administracao)"
  cidr_ipv4         = var.my_ip_cidr
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
}

resource "aws_vpc_security_group_ingress_rule" "app_metrics_from_ops" {
  for_each = {
    api       = 8000
    cadvisor  = 8080
    node      = 9100
    processor = 9101
  }
  security_group_id            = aws_security_group.app.id
  description                  = "Prometheus coletando metricas (${each.key})"
  referenced_security_group_id = aws_security_group.ops.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}

# ---------- Operação ----------
resource "aws_vpc_security_group_ingress_rule" "ops_grafana" {
  security_group_id = aws_security_group.ops.id
  description       = "Grafana"
  cidr_ipv4         = var.my_ip_cidr
  ip_protocol       = "tcp"
  from_port         = 3000
  to_port           = 3000
}

resource "aws_vpc_security_group_ingress_rule" "ops_ssh" {
  security_group_id = aws_security_group.ops.id
  description       = "SSH (administracao)"
  cidr_ipv4         = var.my_ip_cidr
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
}

resource "aws_vpc_security_group_ingress_rule" "ops_loki_from_app" {
  security_group_id            = aws_security_group.ops.id
  description                  = "Promtail das instancias enviando logs ao Loki"
  referenced_security_group_id = aws_security_group.app.id
  ip_protocol                  = "tcp"
  from_port                    = 3100
  to_port                      = 3100
}

# ---------- Banco ----------
resource "aws_vpc_security_group_ingress_rule" "db_from_app" {
  security_group_id            = aws_security_group.db.id
  description                  = "PostgreSQL vindo da aplicacao"
  referenced_security_group_id = aws_security_group.app.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_ingress_rule" "db_from_ops" {
  security_group_id            = aws_security_group.db.id
  description                  = "PostgreSQL vindo da operacao (migracao e Grafana)"
  referenced_security_group_id = aws_security_group.ops.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

# ---------- Saída liberada (pacotes, imagens Docker, Git, APIs da AWS) ----------
resource "aws_vpc_security_group_egress_rule" "all" {
  for_each = {
    alb = aws_security_group.alb.id
    app = aws_security_group.app.id
    ops = aws_security_group.ops.id
  }
  security_group_id = each.value
  description       = "Saida liberada"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
