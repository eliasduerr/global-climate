locals {
  name = "${var.project}-pipeline"
}

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${local.name}-sfn-role"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

data "aws_iam_policy_document" "sfn_batch" {
  statement {
    sid       = "SubmitAndObserve"
    actions   = ["batch:SubmitJob", "batch:DescribeJobs", "batch:TerminateJob"]
    resources = ["*"]
  }
  statement {
    sid = "SyncCallback"
    actions = [
      "events:PutTargets",
      "events:PutRule",
      "events:DescribeRule",
    ]
    resources = ["arn:aws:events:${var.aws_region}:*:rule/StepFunctionsGetEventsForBatchJobsRule"]
  }
}

resource "aws_iam_role_policy" "sfn_batch" {
  name   = "${local.name}-batch"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn_batch.json
}

resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/vendedlogs/states/${local.name}"
  retention_in_days = 1
}

data "aws_iam_policy_document" "sfn_logs" {
  statement {
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "sfn_logs" {
  name   = "${local.name}-logs"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn_logs.json
}

resource "aws_sfn_state_machine" "pipeline" {
  name     = local.name
  role_arn = aws_iam_role.sfn.arn
  type     = "STANDARD"

  definition = jsonencode({
    Comment = "Global climate ETL pipeline: ingest -> clean -> features"
    StartAt = "Ingest"
    States = {
      Ingest = {
        Type     = "Task"
        Resource = "arn:aws:states:::batch:submitJob.sync"
        Parameters = {
          JobName       = "ingest"
          JobDefinition = aws_batch_job_definition.service["ingest"].arn
          JobQueue      = aws_batch_job_queue.main.arn
        }
        Retry = [{
          ErrorEquals     = ["States.TaskFailed", "Batch.BatchException", "Batch.AWSBatchException"]
          IntervalSeconds = 5
          MaxAttempts     = 3
          BackoffRate     = 2.0
        }]
        Next = "Clean"
      }
      Clean = {
        Type     = "Task"
        Resource = "arn:aws:states:::batch:submitJob.sync"
        Parameters = {
          JobName       = "clean"
          JobDefinition = aws_batch_job_definition.service["clean"].arn
          JobQueue      = aws_batch_job_queue.main.arn
        }
        Retry = [{
          ErrorEquals     = ["States.TaskFailed", "Batch.BatchException", "Batch.AWSBatchException"]
          IntervalSeconds = 5
          MaxAttempts     = 3
          BackoffRate     = 2.0
        }]
        Next = "Features"
      }
      Features = {
        Type     = "Task"
        Resource = "arn:aws:states:::batch:submitJob.sync"
        Parameters = {
          JobName       = "features"
          JobDefinition = aws_batch_job_definition.service["features"].arn
          JobQueue      = aws_batch_job_queue.main.arn
        }
        Retry = [{
          ErrorEquals     = ["States.TaskFailed", "Batch.BatchException", "Batch.AWSBatchException"]
          IntervalSeconds = 5
          MaxAttempts     = 3
          BackoffRate     = 2.0
        }]
        End = true
      }
    }
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.pipeline.arn
}
