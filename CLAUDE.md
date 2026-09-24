# Working agreements

## Shipping

**Always default to opening a pull request.** Work is not delivered by being
pushed to a branch. Finish a change, push it, and open the PR without being
asked. Merging and deploying are still the owner's call unless they say
otherwise.

## Guards

Every guard in this repository is verified against deliberate breakage, not
merely observed passing. A check that has never failed has not been shown to
work. Break the thing it is meant to catch, watch it catch it, restore, and say
in the commit message which breakages were tried.

The validators live in `scripts/validate_packs.py`; the API's own guards live
in `apps/api/tests/`.

## What the product refuses to do

These are enforced in code and should not be softened:

- **No magic number.** There is no composite trust score. A reader is given the
  evidence, not a single figure that stands in for it.
- **Unknown is a valid result.** `NOT EVALUATED` and `pending_human` never
  resolve to a pass. An empty state is a claim about the data, so a view that
  failed to load says so rather than reporting "none".
- **Evidence over claims.** Every result resolves to a request, a response, a
  trace, the judgements made on it, and a SHA-256.

## Interface

- Monochrome by construction. A saturated colour is a verdict about the system
  under evaluation, read off small status squares in dense tables.
- Asides are marked by a glyph that names what they are, coloured by how much
  they matter -- `Note` and `ErrorNote` in `apps/web/src/components/ui.tsx`.
  Never flag a block with a heavier or coloured rule down one of its sides;
  `validate_no_accent_rules()` refuses it.
- Corners are square (2px is the largest radius) and nothing casts a shadow.
  Depth is borders and surface value, not elevation.

## Database

The schema is changed by a migration in `apps/api/aegis/migrations/versions/`,
never by `create_all`. `create_all` does not alter a table that already exists,
which is how the deployed database once sat seven columns behind the models and
returned 500 on every endpoint that selected one of them.
`tests/test_migrations.py` fails if a model changes without a revision.

## Expert program

Current government employees may take part in the expert benchmark program
under the [Federal Employee Participation Policy](https://wiki.yourrosterapp.com/doc/federal-employee-participation-policy-JJGDdYgKPJ).
Each expert's clearance is one field, **Ethics clearance**, in the roster on
the [Expert Benchmark Program](https://wiki.yourrosterapp.com/doc/expert-benchmark-program-MaArHzOCKN)
page. An expert whose clearance reads `On file` is cleared: do not raise ethics
or eligibility again. Flag only an expert marked `Pending` who is being given
item-writing, reviewing or grading work, and say it once.
