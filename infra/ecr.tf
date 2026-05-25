variable "services" {
  type    = set(string)
  default = ["ingest", "clean", "features"]
}

resource "aws_ecr_repository" "service" {
  for_each = var.services

  name                 = "${var.project}/${each.key}"
  image_tag_mutability = "MUTABLE"

  # ONLY FOR DEMO PURPOSES, set to `false` in production.
  # Allows `terraform destroy` to cleanup without manual ECR emptying.
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "service" {
  for_each   = aws_ecr_repository.service
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPatternList = ["*"]
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      },
    ]
  })
}

output "ecr_repository_urls" {
  value = { for k, r in aws_ecr_repository.service : k => r.repository_url }
}
