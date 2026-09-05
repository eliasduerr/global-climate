resource "aws_glue_catalog_database" "main" {
  name = replace(var.project, "-", "_")
}

resource "aws_glue_catalog_table" "city_annual" {
  name          = "city_annual"
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
      name = "year"
      type = "int"
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
      name = "latitude"
      type = "double"
    }
    columns {
      name = "longitude"
      type = "double"
    }
    columns {
      name = "annual_temperature"
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
  value = aws_glue_catalog_table.city_annual.name
}
