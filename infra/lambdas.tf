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

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  for_each = local.services

  name               = "${var.project}-${each.key}-exec"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  for_each = aws_iam_role.lambda_exec

  role       = each.value.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_s3" {
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

resource "aws_iam_role_policy" "lambda_s3" {
  for_each = local.services

  name   = "${var.project}-${each.key}-s3"
  role   = aws_iam_role.lambda_exec[each.key].id
  policy = data.aws_iam_policy_document.lambda_s3[each.key].json
}

data "aws_iam_policy_document" "ingest_ssm" {
  statement {
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${var.aws_region}:*:parameter/${var.project}/kaggle/*"]
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ingest_ssm" {
  name   = "${var.project}-ingest-ssm"
  role   = aws_iam_role.lambda_exec["ingest"].id
  policy = data.aws_iam_policy_document.ingest_ssm.json
}

resource "aws_lambda_function" "service" {
  for_each = local.services

  function_name = "${var.project}-${each.key}"
  role          = aws_iam_role.lambda_exec[each.key].arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.service[each.key].repository_url}@${data.aws_ecr_image.service[each.key].image_digest}"
  architectures = ["x86_64"]

  memory_size = 3008
  timeout     = 600

  environment {
    variables = merge(
      { DATA_BUCKET = aws_s3_bucket.data.id },
      each.key == "ingest" ? {
        KAGGLE_TOKEN_PARAM = "/${var.project}/kaggle/token"
        HOME = "/tmp"
      } : {},
    )
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each = local.services

  name              = "/aws/lambda/${aws_lambda_function.service[each.key].function_name}"
  retention_in_days = 14
}

output "lambda_arns" {
  value = { for k, fn in aws_lambda_function.service : k => fn.arn }
}
