resource "aws_glue_catalog_database" "main" {
  name = replace(var.project, "-", "_")
}

resource "aws_glue_catalog_table" "temperature_features" {
  name          = "temperature_features"
  database_name = aws_glue_catalog_database.main.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    classification        = "parquet"
    "parquet.compression" = "SNAPPY"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data.id}/processed/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetHiveOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "dt"
      type = "date"
    }
    columns {
      name = "country"
      type = "string"
    }
    columns {
      name = "city"
      type = "string"
    }
    columns {
      name = "baseline_temperature_30y"
      type = "double"
    }
    columns {
      name = "temperature_stddev_10y"
      type = "double"
    }
    columns {
      name = "year_over_year_change"
      type = "double"
    }
    columns {
      name = "temperature_anomaly"
      type = "double"
    }
  }
}

output "glue_database" {
  value = aws_glue_catalog_database.main.name
}

output "glue_table" {
  value = aws_glue_catalog_table.temperature_features.name
}
