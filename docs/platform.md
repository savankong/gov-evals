# Platform design

This document answers the design feedback of 24 September 2026. It gives the
thesis, the top-level steps with one verb for each, a response to each
requirement in the feedback, and what is built, not built, and still undecided.

## Thesis

> The Aegis platform captures expert reasoning for government problems that
> improves our customers' (frontier labs') models on the needs of government
> customers.

The goal is narrower than "get any data". It is **get the data the model is
bad at**, and predict which of that data a frontier lab will pay the most for.
The platform is built on that goal:

- Do not spend expert hours until you know where the model fails.
- Put the problems the model gets wrong, and most of all the ones it gets
  wrong with high confidence, in front of experts first.
- Deliver the result in bins, so that the valuable data is not sold at the
  bulk rate.

## The steps

Six verbs. The feedback proposed four (Ingest, Store, Capture, Evaluate). This
design adds **Target** at the start and **Deliver** at the end. The goal needs
a step that decides where expert time goes. Packaging is in the requirements
but had no verb.

| # | Verb | What it does | In the product |
| - | --- | --- | --- |
| 1 | **Target** | Choose where expert hours go. Per knowledge area: what the model got wrong, how confident it was, and how much of that is already captured. | Weakness map (`/weakness`, `GET /weakness-map`) |
| 2 | **Ingest** | Take in source material: a provider's zip, public records, problems written by experts. | Datasets, with zip upload |
| 3 | **Store** | Keep problems and known answers versioned, hashed and marked for classification. | Library and datasets |
| 4 | **Capture** | Get expert reasoning onto the record. | Solve, Review queue, Experts |
| 5 | **Evaluate** | Run the customer's model against the problems and judge each answer. | Projects, campaigns (the existing engine) |
| 6 | **Deliver** | Package qualified, releasable data and send it to the customer's ingest pipeline. | Packages (`/packages`, `POST /data-packages`) |

The list is a loop. Evaluate produces the results that Target reads. After a
delivery, running the lab's next model again shows whether the data fixed the
weakness. That is the measure of whether the data was worth its price.

```
   ┌──────────────────────────────────────────────────────────┐
   ▼                                                          │
 Target ──▶ Ingest ──▶ Store ──▶ Capture ──▶ Deliver          │
   ▲                               │                          │
   │                               ▼                          │
   └─────────────────────────── Evaluate ◀── the lab's next model
```

### Capture subheadings

| Subheading | What the expert does | State |
| --- | --- | --- |
| **Solve** | Works the problem blind. Records each step, what the step rests on (for example "FAR 15.305(a)"), the answer, and the sources used. | Built |
| **Score** | Grades a model answer against a rubric. | Built (review queue) |
| **Correct** | Opens the model's wrong answer, then writes the right reasoning. The trace records that the expert saw the model's answer. | Built, as a Solve that opened the answer |
| **Adjudicate** | A second expert settles a disagreement between two traces or two scores. | Not built |

Solve and Correct are kept separate on purpose. An expert who reads the wrong
answer first is anchored to it. The model's answer stays closed on the Solve
screen until the expert opens it, and the delivered record carries
`shown_model_answer` so the lab knows which kind of trace each record is. The
expert never sees the reference answer.

## Response to each requirement

**1. Identify which knowledge areas the LLM is weak in.**
Agreed that this comes first. Neither method listed identifies weakness,
though:

- *Collecting real contracting workflows and preparing the reasoning steps
  for training* is Ingest, Capture and Deliver. It produces training data. It
  shows where the model is weak only if the model is run against that data.
- *An RL environment built from acquisition rules and a known public contract
  outcome* is a product the lab could buy, not a way to find weakness. It is a
  strong idea: a public outcome gives a reward that can be checked, which is
  what RL post-training needs. Treat it as a delivery format (see "Not built").

The method this design uses: run the lab's model on problems with known
answers, and count failures by knowledge area and by the model's confidence.
This is built. Each scenario declares a `knowledge_area` (for example "Source
selection (FAR 15.3)"). A knowledge area that nobody declared is reported as
"Not declared". The platform does not guess it from tags.

**On a confidence score from the lab.**
The platform records confidence for each answer, together with its source.
The sources are listed from most to least trustworthy:

1. `logprob`: token probabilities from the API. The OpenAI-compatible
   connector reads these when `logprobs` is set. This is a rough signal: it
   measures how predictable the wording was, not whether the claim is true.
2. `sample_agreement`: the same question asked N times, and the share of
   answers that agree. This needs nothing from the lab, which makes it the
   answer to "or we'd have to figure out a way". Set `repetitions` on the
   evaluation.
3. `reported`: the model states its own confidence. This is the easiest to
   get and the worst calibrated.

A wrong answer with no confidence is counted as **unknown**. It is never
counted as confident or as unsure. The weakness map splits wrong answers into
confidently wrong, unsure and unknown, at a threshold the reader sets.
Confidently wrong is the bin to capture first. A model that is wrong and
unsure already hedges. A model that is wrong and confident gives a contracting
officer a wrong answer in the tone of a right one.

**2. Store data / 3. Ingest data.**
These are in the reverse order. Ingest comes first. Providers usually send one
large zip and let the receiver sort it out, so dataset upload now accepts a
zip:

- Structured files inside the zip expand row by row.
- Each other file becomes one row.
- A file that is not text (a PDF, a scan) is kept by name and SHA-256, and the
  quality report counts it. Extracting text from PDFs is not built.
- Expansion is limited by the bytes actually read, not by the sizes the
  archive declares.

**4. Capture reasoning traces from experts solving a government problem, for
example a contract bid.**
This is built (see Solve above). One risk needs a decision before any real
workflow is ingested:

- Source selection information and contractor bid or proposal information
  from a live procurement are protected under the Procurement Integrity Act
  (FAR 3.104). Much of that material is also marked CUI.
- A real bid is the vendor's proprietary data.

None of this can be sold to a lab. Use material that is safe to sell:

- Closed and public records, such as GAO bid protest decisions, FPDS award
  data, and SAM.gov notices.
- Problems written by experts and modeled on real cases, with the details
  changed.

The software enforces its part. A package contains only records marked
exactly `UNCLASSIFIED`, with no PII flag. A trace is marked at least as
strictly as the problem it answers.

**5. Present generated responses to reviewers for scoring.**
This exists (the review queue). Reviews and traces follow the same
qualification rule. Work from someone outside the required discipline is
recorded as an opinion, and it is never delivered as expert data.

**6. Package data and send it to the customer's ingest pipeline.**
This is built as the first version. Each package:

- Is built once, stored, and hashed. Every record carries its own SHA-256.
- Is checked against its recorded digest before each download. A file that
  changed after it was built is refused.
- Identifies experts by pseudonym, discipline and verification status, never
  by name.
- Has a manifest that counts every bin, and counts every left-out record by
  reason:
  - The author was not qualified for the problem.
  - The record is marked anything other than `UNCLASSIFIED`.
  - The record is flagged as containing PII.
  - No judgement was ever made (the result is pending, not evaluated, or an
    error).
  - The answer was reviewed, but by nobody qualified to judge it.

## Binning and price

Bulk rates apply to data sold as one undifferentiated zip. The package
manifest bins every record by:

- **knowledge area**: what the data teaches.
- **model outcome**: whether the lab's model got this problem wrong, got it
  right, or was never tested on it.
- **kind**: a reasoning trace or a scored model answer.

Each trace also carries `model_confidently_wrong`. These are the axes a price
list can use. A trace on a problem the model gets confidently wrong, in an
area the lab cares about, is the top tier. A trace on a problem the model
already gets right is close to worthless to that lab.

The cost side is recorded too. Every trace records the expert's time, and the
weakness map totals expert time per area. That time multiplied by an expert's
rate is the acquisition cost Josh raised.

The product does **not** compute a price, an ROI or a priority score. This
follows the rule that has held since the first commit, "no magic number". A
single figure would hide the inputs that a commercial decision needs. The
product shows the counts and the cost, and the owner decides the price.

## The people side

The feedback says most of the company is the people side, and compares it to
a discovery mission at DDS. That is the right comparison, and it applies to
the software too. The expensive part of this business is finding contracting
officers, protest attorneys and program managers, getting their time, and
keeping them.

The platform instruments what it can:

- Time on each problem, taken automatically from when the page opens.
- Whether the expert saw the model's answer.
- How sure the expert was.
- Whether their expertise was verified, and by whom.

What it cannot tell you is why an expert stops, or which workflow matches how
a contracting officer thinks. Do five discovery interviews with working
contracting officers before building more capture interface. Ask them to talk
through one real decision out loud, and compare what they say with what the
step editor asks for.

## Not built

- **Adjudication.** A second expert settling a disagreement.
- **Public-record ingest.** Connectors for GAO decisions, FPDS and SAM.gov.
  These are the best source of problems with a checkable outcome.
- **RL environment delivery.** Packaging problems with a checkable reward as
  an environment a lab can train against, rather than as static records.
- **Per-lab delivery formats.** SFT pairs, preference pairs (a wrong model
  answer beside the expert's correction is one already), and each lab's own
  schema. Today there is one JSONL schema, `aegis.delivery/1`.
- **Text extraction** from PDFs and scans in an ingested zip.
- **Price lists.** Deliberately left to the owner (see above).

## Open questions

1. Which knowledge areas does the first customer care about? The areas in the
   shipped acquisition pack (source selection and describing agency needs)
   are a starting point, not a market view.
2. Will the lab run our problems through its model and return the answers,
   or does the lab give us API access? This decides whether `logprob` is
   available, or whether sample agreement is the only honest confidence.
3. Which source material is safe to sell, and who signs off on that? The
   software enforces a marking. It cannot decide what the marking should be.
4. Is an unverified expert's trace sellable at a lower tier, or not at all?
   Today it is delivered if the expert qualifies, with `verified: false` on
   the record.
