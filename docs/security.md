# Security posture

Government authorisation is a customer and deployment process. Nothing here
implies an ATO; these are the controls the software provides.

## Data handling

Every artifact carries a classification marking, an owner, provenance and a
retention policy. The marking travels with the record through the API, and the
interface shows the highest marking of the content on screen as a banner top and
bottom.

Evaluation data and model outputs are never used to train any model. There is no
code path that exports them.

## Egress

`AEGIS_EGRESS_POLICY=deny` with `AEGIS_EGRESS_ALLOWLIST` refuses any connector
whose host is not listed, before the request leaves the process. Localhost is
always permitted so on-premises inference works under a deny policy. The offline
target declares `requires_egress = False` and is exempt.

The connector catalogue states for each adapter whether it reaches outside the
deployment, so an operator can see it before configuring a system.

## Secrets

Credentials are referenced, never stored. `credential_ref` names an environment
variable (`env:NAME`) or a mounted file (`file:/run/secrets/...`), so key material
lives in the deployment's secret manager and never lands in the database or in a
system-version snapshot.

## Authentication and access

Local accounts (bcrypt), OIDC and enterprise SSO are P0. CAC/PIV is accepted where
a terminating proxy validates the certificate chain against DoD PKI and forwards
the verified subject — the platform never validates certificates itself, because in
a DoD deployment that belongs to the proxy or the service mesh.

Eight roles ship with default permissions. The role-to-permission mapping lives in
the database per organization and is editable; it is not hard-coded at call sites.
Grants are organization-wide or project-scoped.

## Audit

Material actions are logged append-only and hash-chained: each event stores the
digest of its predecessor. `GET /audit/verify` recomputes the chain and reports the
sequence number where it breaks. Editing or deleting a row inside the application
is detectable.

Recorded actions include configuration changes, dataset and prompt changes,
evaluation execution, human scores, **threshold changes**, risk acceptance,
assurance-case acceptance and report generation. A risk acceptance records both the
named authority and the account that entered it.

## Evidence integrity

Datasets, scenarios, system configurations, results and reports are hashed with
SHA-256 over a canonical JSON encoding, so the same logical object always produces
the same digest. A report download carries its digest in `X-Content-SHA256`.

## Refusing an unsafe configuration

Outside `development`, the platform will not start if the signing key is the
shipped default or shorter than 32 bytes, if the bootstrap password is the shipped
default, or if demonstration seeding is enabled. The error names each problem.

## Telemetry

Off unless a customer sets `AEGIS_TELEMETRY_ENABLED` and points `AEGIS_OTLP_ENDPOINT`
at their own collector. `GET /health` states the current setting so an operator can
confirm it at a glance. The platform never phones home.

## Supply chain

The API image installs into a prefix and copies the result into a slim runtime with
no build toolchain. The web image uses Next.js standalone output. Both run as an
unprivileged user and carry a healthcheck. Both have been built and run: they
serve, and they drop to uid 10001.

**Bill of materials.** CI generates a CycloneDX SBOM for the API, the SDK and the
web app on every pull request, and the deploy job generates one per image.
`scripts/check_sbom.py` refuses a document that lists no components, that carries
components with no name, or whose contents say the scanner was aimed at the wrong
directory. An empty SBOM is the supply-chain version of a run that judged nothing,
and it does not pass for one.

**Signing.** The deploy job signs both images with cosign, keyless, using the
workflow's GitHub OIDC identity, and attaches the SBOM as a CycloneDX
attestation. Signing is by digest, never by tag: a tag is a mutable pointer, so a
signature over one says nothing about what it resolves to afterwards.

**Verification is the control.** Signing and then deploying without checking
proves nothing, so the job re-reads what the registry holds and verifies both the
signature and the attestation against a pinned certificate identity and issuer.
`cosign verify` with no identity constraint accepts a valid signature from anyone,
which is the usual way this check quietly stops meaning anything. Verification runs
before the rollout step, so a failure stops the deployment rather than reporting on
one already serving.

`scripts/validate_packs.py` fails CI if the signing, the attestation, the identity
pinning, the `id-token: write` permission or the verify-before-rollout ordering is
edited out. That was confirmed against four deliberate breakages rather than
assumed.

Two things it does not cover, which matter:

- **The running container is not what was signed.** `.do/app.yaml` builds from
  GitHub source, so App Platform runs its own build output. The signed images are
  an attested artifact of record for the commit. Pointing the spec at `image:`
  with the verified digest closes this, and needs a paid container registry.
- **No image has been signed against a real registry.** The pipeline's shape is
  asserted; its execution is not yet demonstrated.

## Not yet implemented

Stated plainly rather than omitted:

- Customer-managed encryption keys.
- Field-level encryption at rest (rely on volume or database encryption).
- SAML (OIDC is implemented; SAML is P1).
- Attribute-based access control beyond role and project scope.
