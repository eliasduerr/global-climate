locals {
  dashboard_name = "${var.project}-dashboard"
}

data "aws_ecr_image" "dashboard" {
  repository_name = aws_ecr_repository.service["dashboard"].name
  image_tag       = lookup(var.image_tags, "dashboard", local.default_image_tag)
}

# --- Task execution role (image pull + logs) -------------------------------

resource "aws_iam_role" "dashboard_execution" {
  name               = "${local.dashboard_name}-execution"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
}

resource "aws_iam_role_policy_attachment" "dashboard_execution" {
  role       = aws_iam_role.dashboard_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# --- Task role (S3 read on processed/) -------------------------------------

resource "aws_iam_role" "dashboard_task" {
  name               = "${local.dashboard_name}-task"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
}

data "aws_iam_policy_document" "dashboard_task" {
  statement {
    sid       = "ReadProcessed"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data.arn}/processed/*"]
  }
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["processed/*", "processed"]
    }
  }
}

resource "aws_iam_role_policy" "dashboard_task" {
  role   = aws_iam_role.dashboard_task.id
  policy = data.aws_iam_policy_document.dashboard_task.json
}

# --- Infrastructure role (ECS manages ALB / target groups / etc.) ----------

data "aws_iam_policy_document" "dashboard_infrastructure_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "dashboard_infrastructure" {
  name               = "${local.dashboard_name}-infrastructure"
  assume_role_policy = data.aws_iam_policy_document.dashboard_infrastructure_assume.json
}

resource "aws_iam_role_policy_attachment" "dashboard_infrastructure" {
  role       = aws_iam_role.dashboard_infrastructure.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices"
}

# --- Logs ------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "dashboard" {
  name              = "/ecs/${local.dashboard_name}"
  retention_in_days = 14
}

# --- Task security group (egress only) -------------------------------------

resource "aws_security_group" "dashboard_task" {
  name        = "${local.dashboard_name}-task"
  description = "Streamlit task egress to S3 + DNS"
  vpc_id      = aws_vpc.main.id

  egress {
    description = "HTTPS to S3 / STS / ECR"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "DNS over UDP"
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "DNS over TCP"
    from_port   = 53
    to_port     = 53
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- Express service -------------------------------------------------------

resource "aws_ecs_express_gateway_service" "dashboard" {
  service_name            = local.dashboard_name
  execution_role_arn      = aws_iam_role.dashboard_execution.arn
  infrastructure_role_arn = aws_iam_role.dashboard_infrastructure.arn
  task_role_arn           = aws_iam_role.dashboard_task.arn

  cpu               = "256"
  memory            = "512"
  health_check_path = "/_stcore/health"

  primary_container {
    image          = "${aws_ecr_repository.service["dashboard"].repository_url}@${data.aws_ecr_image.dashboard.image_digest}"
    container_port = 8080

    aws_logs_configuration {
      log_group         = aws_cloudwatch_log_group.dashboard.name
      log_stream_prefix = "streamlit"
    }

    environment {
      name  = "DATA_BUCKET"
      value = aws_s3_bucket.data.id
    }

    environment {
      name  = "AWS_REGION"
      value = var.aws_region
    }
  }

  network_configuration {
    subnets         = [for s in aws_subnet.public : s.id]
    security_groups = [aws_security_group.dashboard_task.id]
  }

  scaling_target {
    min_task_count            = 1
    max_task_count            = 2
    auto_scaling_metric       = "AVERAGE_CPU"
    auto_scaling_target_value = 60
  }

  depends_on = [
    aws_iam_role_policy.dashboard_task,
    aws_iam_role_policy_attachment.dashboard_execution,
    aws_iam_role_policy_attachment.dashboard_infrastructure,
  ]
}

output "dashboard_endpoints" {
  description = "HTTPS endpoints for the Streamlit dashboard."
  value       = aws_ecs_express_gateway_service.dashboard.ingress_paths
}
