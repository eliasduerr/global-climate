resource "aws_s3_bucket" "data" {
  bucket = "${var.project}-data"

  # ONLY FOR DEMO PURPOSES, set to `false` in production.
  # Allows `terraform destroy` to cleanup without manual S3 emptying.
  force_destroy = true
}

# ONLY FOR DEMO PURPOSES, set to "Enabled" in production.
# Bucket versioning hinders cleanup.
resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Disabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ONLY FOR DEMO PURPOSES, define specific rules per prefix in production.
# Expires all bucket objects after 7 days.
resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    id     = "demo-expire-all"
    status = "Enabled"
    filter {}
    expiration {
      days = 7
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

output "data_bucket" {
  value = aws_s3_bucket.data.id
}
