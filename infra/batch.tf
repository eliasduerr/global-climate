locals {
  services = toset(["ingest", "clean", "features"])

  s3_access = {
    ingest = {
      write = ["raw/*"]
    }
    clean = {
      read  = ["raw/*"]
      write = ["interim/*"]
    }
    features = {
      read  = ["interim/*"]
      write = ["processed/*"]
    }
  }

  ephemeral_storage_gib = {
    ingest   = 30
    clean    = 21
    features = 21
  }

  task_vcpu = {
    ingest   = 2
    clean    = 2
    features = 2
  }
  task_memory_mb = {
    ingest   = 4096
    clean    = 4096
    features = 8192
  }

  default_image_tag = "latest"
}

variable "image_tags" {
  description = "Map of service name -> ECR image tag to deploy."
  type        = map(string)
  default     = {}
}

data "aws_ecr_image" "service" {
  for_each = local.services

  repository_name = aws_ecr_repository.service[each.key].name
  image_tag       = lookup(var.image_tags, each.key, local.default_image_tag)
}

data "aws_iam_policy_document" "task_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task_execution" {
  name               = "${var.project}-task-execution"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "task" {
  for_each = local.services

  name               = "${var.project}-${each.key}-task"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
}

data "aws_iam_policy_document" "task_s3" {
  for_each = local.services

  dynamic "statement" {
    for_each = length(lookup(local.s3_access[each.key], "read", [])) > 0 ? [1] : []
    content {
      sid     = "Read"
      actions = ["s3:GetObject"]
      resources = [
        for p in local.s3_access[each.key].read : "${aws_s3_bucket.data.arn}/${p}"
      ]
    }
  }

  dynamic "statement" {
    for_each = length(lookup(local.s3_access[each.key], "write", [])) > 0 ? [1] : []
    content {
      sid     = "Write"
      actions = ["s3:PutObject", "s3:AbortMultipartUpload"]
      resources = [
        for p in local.s3_access[each.key].write : "${aws_s3_bucket.data.arn}/${p}"
      ]
    }
  }

  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
  }
}

resource "aws_iam_role_policy" "task_s3" {
  for_each = local.services

  name   = "${var.project}-${each.key}-s3"
  role   = aws_iam_role.task[each.key].id
  policy = data.aws_iam_policy_document.task_s3[each.key].json
}

data "aws_iam_policy_document" "ingest_ssm" {
  statement {
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${var.aws_region}:*:parameter/${var.project}/kaggle/*"]
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "ingest_ssm" {
  name   = "${var.project}-ingest-ssm"
  role   = aws_iam_role.task["ingest"].id
  policy = data.aws_iam_policy_document.ingest_ssm.json
}

resource "aws_batch_compute_environment" "fargate" {
  compute_environment_name = "${var.project}-fargate"
  type                     = "MANAGED"

  compute_resources {
    type               = "FARGATE_SPOT"
    max_vcpus          = 8
    subnets            = [for s in aws_subnet.public : s.id]
    security_group_ids = [aws_security_group.task.id]
  }
}

resource "aws_batch_job_queue" "main" {
  name     = "${var.project}-queue"
  state    = "ENABLED"
  priority = 1

  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.fargate.arn
  }
}

resource "aws_cloudwatch_log_group" "batch" {
  for_each = local.services

  name              = "/aws/batch/${var.project}-${each.key}"
  retention_in_days = 14
}

resource "aws_batch_job_definition" "service" {
  for_each = local.services

  name                  = "${var.project}-${each.key}"
  type                  = "container"
  platform_capabilities = ["FARGATE"]

  timeout {
    attempt_duration_seconds = 1800
  }

  container_properties = jsonencode({
    image            = "${aws_ecr_repository.service[each.key].repository_url}@${data.aws_ecr_image.service[each.key].image_digest}"
    jobRoleArn       = aws_iam_role.task[each.key].arn
    executionRoleArn = aws_iam_role.task_execution.arn

    resourceRequirements = [
      { type = "VCPU", value = tostring(local.task_vcpu[each.key]) },
      { type = "MEMORY", value = tostring(local.task_memory_mb[each.key]) },
    ]

    ephemeralStorage = {
      sizeInGiB = local.ephemeral_storage_gib[each.key]
    }

    networkConfiguration = {
      assignPublicIp = "ENABLED"
    }

    runtimePlatform = {
      operatingSystemFamily = "LINUX"
      cpuArchitecture       = "X86_64"
    }

    environment = concat(
      [{ name = "DATA_BUCKET", value = aws_s3_bucket.data.id }],
      each.key == "ingest" ? [
        { name = "KAGGLE_TOKEN_PARAM", value = "/${var.project}/kaggle/token" },
      ] : [],
    )

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.batch[each.key].name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = each.key
      }
    }
  })
}

output "batch_job_queue_arn" {
  value = aws_batch_job_queue.main.arn
}

output "batch_job_definition_arns" {
  value = { for k, jd in aws_batch_job_definition.service : k => jd.arn }
}
