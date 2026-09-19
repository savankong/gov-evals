# Aegis Eval on DigitalOcean.
#
# Provisions the managed pieces the platform needs: Postgres for the control
# plane, Valkey for the campaign queue, and a Space for the evidence store.
# Run `terraform apply`, then feed the outputs into .do/app.yaml (App Platform)
# or into the droplet's environment.
#
#   export DIGITALOCEAN_TOKEN=...
#   export SPACES_ACCESS_KEY_ID=...        # for the bucket resource
#   export SPACES_SECRET_ACCESS_KEY=...
#   terraform init && terraform apply

terraform {
  required_version = ">= 1.5"
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.43"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "digitalocean" {
  # Reads DIGITALOCEAN_TOKEN, SPACES_ACCESS_KEY_ID and SPACES_SECRET_ACCESS_KEY
  # from the environment so no credential is written to disk.
}

variable "project_name" {
  type        = string
  default     = "aegis-eval"
  description = "Prefix for every resource this stack creates."
}

variable "region" {
  type        = string
  default     = "nyc3"
  description = "DigitalOcean region. Postgres, Valkey and the Space all live here."
}

variable "environment" {
  type        = string
  default     = "production"
  description = "Environment label, used for tagging and the Spaces key prefix."
}

variable "db_size" {
  type        = string
  default     = "db-s-1vcpu-1gb"
  description = "Managed Postgres node size."
}

variable "db_node_count" {
  type        = number
  default     = 1
  description = "Postgres nodes. Two or more gives a standby for failover."
}

variable "valkey_size" {
  type        = string
  default     = "db-s-1vcpu-1gb"
  description = "Managed Valkey node size."
}

variable "trusted_sources" {
  type        = list(string)
  default     = []
  description = <<-EOT
    Droplet or Kubernetes IDs permitted to reach the databases. Leave empty
    when using App Platform, which is attached through its own app ID instead.
  EOT
}

variable "app_platform_app_id" {
  type        = string
  default     = ""
  description = "App Platform app ID to admit through the database firewall."
}

locals {
  prefix = "${var.project_name}-${var.environment}"
  tags   = [var.project_name, var.environment, "managed-by-terraform"]
}

# ---------------------------------------------------------------------------
# Control-plane database
# ---------------------------------------------------------------------------

resource "digitalocean_database_cluster" "postgres" {
  name       = "${local.prefix}-pg"
  engine     = "pg"
  version    = "16"
  size       = var.db_size
  region     = var.region
  node_count = var.db_node_count
  tags       = local.tags

  maintenance_window {
    day  = "sunday"
    hour = "06:00:00"
  }
}

resource "digitalocean_database_db" "aegis" {
  cluster_id = digitalocean_database_cluster.postgres.id
  name       = "aegis"
}

resource "digitalocean_database_user" "aegis" {
  cluster_id = digitalocean_database_cluster.postgres.id
  name       = "aegis"
}

# The database is not reachable from the public internet: only the sources
# named here can connect.
resource "digitalocean_database_firewall" "postgres" {
  cluster_id = digitalocean_database_cluster.postgres.id

  dynamic "rule" {
    for_each = var.trusted_sources
    content {
      type  = "droplet"
      value = rule.value
    }
  }

  dynamic "rule" {
    for_each = var.app_platform_app_id == "" ? [] : [var.app_platform_app_id]
    content {
      type  = "app"
      value = rule.value
    }
  }
}

# ---------------------------------------------------------------------------
# Campaign queue
# ---------------------------------------------------------------------------

resource "digitalocean_database_cluster" "valkey" {
  name       = "${local.prefix}-valkey"
  engine     = "valkey"
  version    = "8"
  size       = var.valkey_size
  region     = var.region
  node_count = 1
  tags       = local.tags
}

resource "digitalocean_database_firewall" "valkey" {
  cluster_id = digitalocean_database_cluster.valkey.id

  dynamic "rule" {
    for_each = var.trusted_sources
    content {
      type  = "droplet"
      value = rule.value
    }
  }

  dynamic "rule" {
    for_each = var.app_platform_app_id == "" ? [] : [var.app_platform_app_id]
    content {
      type  = "app"
      value = rule.value
    }
  }
}

# ---------------------------------------------------------------------------
# Evidence store
# ---------------------------------------------------------------------------

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "digitalocean_spaces_bucket" "evidence" {
  name   = "${local.prefix}-evidence-${random_id.bucket_suffix.hex}"
  region = var.region

  # Evidence is never public. Nothing in the product serves it directly; the
  # API reads it and applies its own access control.
  acl = "private"

  versioning {
    # Evidence is write-once by design, but versioning means an accidental
    # overwrite or delete is recoverable rather than final.
    enabled = true
  }

  lifecycle_rule {
    id      = "abort-incomplete-uploads"
    enabled = true
    abort_incomplete_multipart_upload_days = 7
  }
}

# Belt and braces: the bucket ACL is private, and public access is denied at
# the policy level too, so a later ACL change cannot expose evidence on its own.
resource "digitalocean_spaces_bucket_policy" "evidence_private" {
  region = digitalocean_spaces_bucket.evidence.region
  bucket = digitalocean_spaces_bucket.evidence.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyAnonymousAccess"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "arn:aws:s3:::${digitalocean_spaces_bucket.evidence.name}/*"
        Condition = {
          Bool = { "aws:SecureTransport" = "false" }
        }
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# Application secret
# ---------------------------------------------------------------------------

resource "random_password" "secret_key" {
  length  = 64
  special = false
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "database_url" {
  value       = digitalocean_database_cluster.postgres.private_uri
  sensitive   = true
  description = "Set as AEGIS_DATABASE_URL. The API names the psycopg driver itself."
}

output "redis_url" {
  value       = digitalocean_database_cluster.valkey.private_uri
  sensitive   = true
  description = "Set as AEGIS_REDIS_URL."
}

output "spaces_bucket" {
  value       = digitalocean_spaces_bucket.evidence.name
  description = "Set as AEGIS_S3_BUCKET."
}

output "spaces_endpoint" {
  value       = "https://${var.region}.digitaloceanspaces.com"
  description = "Set as AEGIS_S3_ENDPOINT_URL."
}

output "spaces_region" {
  value       = var.region
  description = "Set as AEGIS_S3_REGION. SigV4 signs with this; a mismatch fails opaquely."
}

output "secret_key" {
  value       = random_password.secret_key.result
  sensitive   = true
  description = "Set as AEGIS_SECRET_KEY."
}

output "environment_block" {
  sensitive = true
  description = "Ready to paste into a droplet .env file."
  value       = <<-EOT
    AEGIS_ENV=${var.environment}
    AEGIS_SECRET_KEY=${random_password.secret_key.result}
    AEGIS_DATABASE_URL=${digitalocean_database_cluster.postgres.private_uri}
    AEGIS_REDIS_URL=${digitalocean_database_cluster.valkey.private_uri}
    AEGIS_QUEUE_BACKEND=redis
    AEGIS_EVIDENCE_BACKEND=s3
    AEGIS_S3_BUCKET=${digitalocean_spaces_bucket.evidence.name}
    AEGIS_S3_REGION=${var.region}
    AEGIS_S3_ENDPOINT_URL=https://${var.region}.digitaloceanspaces.com
    AEGIS_S3_PREFIX=${var.environment}
    AEGIS_SEED_DEMO=false
    AEGIS_TELEMETRY_ENABLED=false
    AEGIS_MAX_CLASSIFICATION=UNCLASSIFIED
  EOT
}
