# Deploying on DigitalOcean

## What this deployment may hold

DigitalOcean is not FedRAMP authorized and carries no DoD provisional
authorization. A deployment here is appropriate for the commercial SaaS tier
described in PRD section 45: development, demonstrations, vendor evaluation
against public data, and pilots with unclassified material.

It is not a location for CUI, IL4 and above, or source-selection sensitive
information. For those, deploy into a government cloud region under the
customer's own authorization, or on premises.

The spec sets `AEGIS_MAX_CLASSIFICATION=UNCLASSIFIED`, so the platform refuses
an artifact marked above that at the API with a 422 and an explanation. That is
deliberate: a control that depends on every operator remembering which
deployment they are typing into is not a control.

## Choosing a shape

| | App Platform | Droplet | Kubernetes |
| --- | --- | --- | --- |
| Effort | Lowest | Low | Highest |
| Cost at rest | ~$60/mo | ~$30/mo | ~$100/mo |
| Scaling | Per component | Manual | Fine-grained |
| Filesystem | **Ephemeral** | Durable | Ephemeral |
| Best for | Pilots, demos | Cost-sensitive | Many concurrent campaigns |

App Platform is the default path below. The droplet path is in
`deploy/digitalocean/docker-compose.droplet.yml`.

## Storage is not optional on App Platform

Each App Platform container gets an ephemeral filesystem. A container that
writes evidence to local disk loses it on the next deploy, silently, taking the
audit chain with it.

The API refuses that combination. With `AEGIS_EPHEMERAL_FILESYSTEM=true`, it
will not start on SQLite or on the `file` evidence backend, and the error names
what to change. The supplied spec configures managed Postgres and Spaces, and
`scripts/validate_packs.py` fails CI if anyone edits that out.

## Provisioning

### With Terraform

```bash
cd deploy/digitalocean
cp terraform.tfvars.example terraform.tfvars   # edit region and sizes

export DIGITALOCEAN_TOKEN=...
export SPACES_ACCESS_KEY_ID=...
export SPACES_SECRET_ACCESS_KEY=...

terraform init
terraform apply
terraform output -raw environment_block > ../../.env.production
```

This creates managed Postgres 16, managed Valkey 8, and a private, versioned
Space, with database firewalls that admit only the sources you name. Versioning
matters here: evidence is write-once by design, so an accidental overwrite
should be recoverable rather than final.

**The app does not create its own databases.** The `databases:` entries in
`.do/app.yaml` name an existing cluster through `cluster_name` and attach to
it, so `postgres_cluster_name` and `valkey_cluster_name` here have to match
what that file says -- they default to `aegis-pg` and `aegis-valkey`, which is
what the shipped spec expects. If they disagree, `doctl apps create` fails with
`database cluster (aegis-pg) was not found`. Provision first, create the app
second; there is no configuration in which both create a cluster, and nothing
here bills twice.

### By hand

```bash
doctl databases create aegis-pg --engine pg --version 16 --region nyc3 --size db-s-1vcpu-1gb
doctl databases create aegis-valkey --engine valkey --version 8 --region nyc3 --size db-s-1vcpu-1gb

# Spaces is created in the control panel, then a key pair under API > Spaces Keys.
```

## Deploying to App Platform

Set the encrypted values the spec expects, then create the app:

```bash
# A key everyone has is not a key. Generate one per deployment.
export AEGIS_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
export AEGIS_BOOTSTRAP_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
export SPACES_KEY=...
export SPACES_SECRET=...

doctl apps create --spec .do/app.yaml
doctl apps list   # note the app id
```

Edit `.do/app.yaml` first to point `github.repo` at your fork and
`AEGIS_S3_BUCKET` at the bucket Terraform created. That one cannot ship with a
working default: Spaces bucket names are globally unique, so the value in the
file is a placeholder and will not exist in your account.

The API and worker build from the repository root (`source_dir: /`), not from
`apps/api`, because the image has to carry `packs/`. App Platform mounts no
volumes, so packs that arrive only through the compose bind mount are simply
absent in production, and the API comes up healthy with no evaluations,
scenarios or frameworks installed.

### Confirm the deployment

```bash
BASE=https://your-app.ondigitalocean.app

curl -s $BASE/health | jq
curl -s $BASE/health/storage | jq      # must report "ok"
```

`/health/storage` writes and deletes a probe object. Check it after every
deploy: an app that starts fine but cannot reach its Space will run campaigns
and fail to keep what they produce. The deploy workflow asserts this.

## Continuous deployment

`.github/workflows/deploy-digitalocean.yml` builds both images, pushes them to
the DigitalOcean Container Registry, rolls out, and verifies health and storage
before finishing. It runs only after CI passes on `main`, so a commit that fails
tests is never deployed.

Repository secrets: `DIGITALOCEAN_ACCESS_TOKEN`, `DO_APP_ID`, `DO_REGISTRY`.
Repository variable: `PUBLIC_API_BASE`.

The workflow checks all four before it does anything and names the ones that
are missing, because a missing secret otherwise surfaces as `doctl auth`
failing to parse an empty token, which names neither the secret nor the person
who has to set it.

### The registry

`terraform apply` creates it; `terraform output registry_name` is the value
`DO_REGISTRY` wants. It is a name rather than a credential, but the workflow
reads it from `secrets`, so that is where it goes.

Two things worth knowing before choosing a tier:

- **The free `starter` tier holds one repository, and this deployment pushes
  two** — `aegis-api` and `aegis-web`. The second push fails on quota *after*
  the first has succeeded, which reads like a flake and is not one. `basic`
  (~$5/month, 5 repositories, 5 GB) is the smallest tier that fits.
- **DigitalOcean allows one registry per account.** If this account already has
  one, set `create_registry = false` and put its existing name in `DO_REGISTRY`.

Without the registry the deploy workflow stops at its preflight and the
signing pipeline never runs, while App Platform's own `deploy_on_push` keeps
deploying the app from source regardless. That pair — a red workflow beside a
healthy app — is the confusing state the registry resolves.

Storage is not reclaimed automatically: every commit pushes two tagged images,
so run a registry garbage collection periodically or the 5 GB fills.

## Cost

Roughly, at list price:

| Component | Size | Monthly |
| --- | --- | --- |
| App Platform: api, web, worker | 3 × basic 1 vCPU / 1 GB | ~$15 |
| Managed Postgres | 1 node, 1 vCPU / 1 GB | ~$15 |
| Managed Valkey | 1 node, 1 vCPU / 1 GB | ~$15 |
| Spaces | 250 GB included | $5 |
| Container registry | basic: 5 repositories, 5 GB | $5 |
| **Total** | | **~$55–65** |

Evidence accumulates: a campaign stores one record per execution, so a project
running thousands of scenarios weekly will grow into the Spaces allowance over
months rather than years. Judge-model calls, if configured, are billed by the
provider and are usually the larger number.

## Scaling

The worker is the component to scale. Campaign execution runs there, not in the
API, so a long campaign never competes with request handling.

```bash
doctl apps update $APP_ID --spec .do/app.yaml   # after raising worker instance_count
```

Raise Postgres before the workers if results are being written faster than the
database accepts them. The evidence store needs no attention; object storage
absorbs the write rate.

## Operational notes

**Backups.** Managed Postgres takes daily backups with seven-day point-in-time
recovery. The evidence Space is versioned. Both matter: a restored database
whose evidence is missing cannot support any claim made from it.

**The audit chain survives a restore.** Events are chained by content hash, so
`GET /api/v1/audit/verify` after a restore reports whether the chain is intact.
Run it after any recovery, and treat a break as a finding.

**Secrets.** App Platform encrypts values marked `type: SECRET`. Rotating
`AEGIS_SECRET_KEY` invalidates every issued token, which signs everyone out;
that is the intended behaviour for a suspected compromise.

**Egress.** The default policy is `allow`, since evaluating commercial model
APIs is the point of a deployment here. Set `AEGIS_EGRESS_POLICY=deny` with
`AEGIS_EGRESS_ALLOWLIST` to restrict which model endpoints may be reached.

## Moving to an accredited environment later

Nothing in the platform is specific to DigitalOcean. The database is any
SQLAlchemy URL, the evidence store is any S3-compatible endpoint, and the queue
speaks the Redis protocol. Moving to a government cloud region or on premises
means repointing three environment variables and migrating the data — not a
rewrite. Raise `AEGIS_MAX_CLASSIFICATION` only once the destination is
accredited for the marking.
