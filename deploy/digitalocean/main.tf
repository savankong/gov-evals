# Aegis Eval on DigitalOcean.
#
# Provisions the managed pieces the platform needs: Postgres for the control
# plane, Valkey for the campaign queue, a Space for the evidence store, and the
# container registry the deploy workflow pushes signed images to.
#
# Run this BEFORE creating the App Platform app. The app spec does not create
# its databases -- its `databases:` entries name an existing cluster through
# `cluster_name` and attach to it, so the cluster names here and there have to
# agree. They did not, and the result was `doctl apps create` failing with
# "database cluster (aegis-pg) was not found". The names are variables now and
# default to what .do/app.yaml expects.
#
# The Space is the one piece App Platform cannot provide, so it comes from
# here either way. Put its name into AEGIS_S3_BUCKET in the app spec: bucket
# names are globally unique, so the spec ships with a placeholder.
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

variable "registry_name" {
  type        = string
  default     = "aegis-eval"
  description = <<-EOT
    Container registry name, and the value of the DO_REGISTRY repository secret
    the deploy workflow reads -- the two must agree. Images land at
    registry.digitalocean.com/<registry_name>/aegis-api and .../aegis-web.

    A name, not a credential. It is read from `secrets` because that is where
    the workflow looks, and GitHub redacts every registered secret value from
    logs regardless of whether it is sensitive -- which is why it shows as
    `***` beside the image digests rather than because it needs hiding.

    The default matches the live reference deployment.

    DigitalOcean registry names are GLOBALLY unique, like Spaces buckets, so
    this can collide with another account's. Terraform reports that as a plain
    409; change the name rather than retrying.
  EOT
}

variable "registry_tier" {
  type        = string
  default     = "basic"
  description = <<-EOT
    Registry subscription tier.

    `starter` is free but holds ONE repository, and this deployment pushes two
    -- aegis-api and aegis-web -- so it cannot work here. The second push fails
    with a quota error after the first has already succeeded, which reads like
    a flake and is not one. `basic` is ~$5/month for 5 repositories and 5 GB,
    and is the smallest tier that actually fits.
  EOT

  validation {
    condition     = contains(["starter", "basic", "professional"], var.registry_tier)
    error_message = "registry_tier must be starter, basic or professional."
  }
}

variable "create_registry" {
  type        = bool
  default     = false
  description = <<-EOT
    Whether to create the registry, as opposed to attaching to one that exists.

    Defaults to FALSE because the reference deployment's registry already
    exists: `aegis-eval`, Basic tier, NYC3, created 19 Sep 2026. DigitalOcean
    allows exactly one registry per account, so leaving this on would make
    every apply fail against the one already there.

    A NEW deployment on a fresh account must set this to `true`. Getting that
    wrong is not silent: `doctl registry login` fails in the deploy workflow
    before anything is built, and the workflow's preflight names what is
    missing.
  EOT
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

variable "postgres_cluster_name" {
  type        = string
  default     = "aegis-pg"
  description = <<-EOT
    Postgres cluster name. This must equal the cluster_name that
    .do/app.yaml gives its aegis-db entry: App Platform looks the cluster up by
    name and attaches to it. A mismatch fails app creation with
    "database cluster (aegis-pg) was not found", and creating the app anyway
    with its own databases block would bill for a second pair of clusters.
  EOT
}

variable "valkey_cluster_name" {
  type        = string
  default     = "aegis-valkey"
  description = "Valkey cluster name. Must equal .do/app.yaml's aegis-queue cluster_name."
}

locals {
  prefix = "${var.project_name}-${var.environment}"
  tags   = [var.project_name, var.environment, "managed-by-terraform"]
}

# ---------------------------------------------------------------------------
# Control-plane database
# ---------------------------------------------------------------------------

resource "digitalocean_database_cluster" "postgres" {
  # Must match .do/app.yaml's databases[].cluster_name: App Platform attaches
  # to an existing cluster by this name rather than creating one.
  name       = var.postgres_cluster_name
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
  # Must match .do/app.yaml's databases[].cluster_name.
  name       = var.valkey_cluster_name
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
    id                                     = "abort-incomplete-uploads"
    enabled                                = true
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
# Container registry
# ---------------------------------------------------------------------------

# Holds the images the deploy workflow builds, signs by digest and verifies
# before rolling out. Without it that workflow stops at its own preflight and
# the signing pipeline never runs at all -- which is what happened on the first
# real deployment.
#
# Note what this does and does not buy. The registry makes the signed images an
# attested artifact of record for a commit. It does not yet make them the thing
# that serves traffic: .do/app.yaml still builds from GitHub source, so App
# Platform runs its own build output. Closing that gap means pointing the
# spec's components at `image:` with the digest the workflow verified, and this
# registry is the prerequisite for it, not the whole of it. See docs/security.md.
resource "digitalocean_container_registry" "aegis" {
  count = var.create_registry ? 1 : 0

  name                   = var.registry_name
  subscription_tier_slug = var.registry_tier
  region                 = var.region
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

output "registry_name" {
  # Deliberately the variable rather than the resource attribute. The resource's
  # name IS var.registry_name, so reading it back proves nothing -- and indexing
  # [0] through a conditional is a trap when create_registry is false and the
  # resource has count 0.
  value       = var.registry_name
  description = <<-EOT
    Set as the DO_REGISTRY repository secret, under
    Settings -> Secrets and variables -> Actions. It is a name rather than a
    credential, but the workflow reads it from `secrets`, so that is where it
    goes.
  EOT
}

output "registry_endpoint" {
  # Constructed, not read back, for the same reason -- and because this is
  # exactly how the deploy workflow builds it from DO_REGISTRY, so the two
  # cannot drift.
  value       = "registry.digitalocean.com/${var.registry_name}"
  description = "Where the deploy workflow pushes. Images are addressed by digest downstream, never by tag."
}

output "secret_key" {
  value       = random_password.secret_key.result
  sensitive   = true
  description = "Set as AEGIS_SECRET_KEY."
}

output "environment_block" {
  sensitive   = true
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
