**UNCLASSIFIED**

# Acquisition Bench: Claude models on contract specialist questions (demonstration)

Generated 2026-09-26 06:08 UTC from campaign(s): Acquisition Bench -- criteria met (`c9157bc1-1b83-4593-a9df-9ed13b1f1ad4`), Acquisition Bench -- judge calibration (`933caee9-fa4a-4185-b249-8832d7d0b301`).

> **DEMONSTRATION DATA -- NOT A PUBLISHED BENCHMARK.**
>
> This report was produced to demonstrate the benchmark workflow end to end. Its figures are real measurements of recorded answers. How it differs from a published benchmark, and which steps were done by stand-ins rather than qualified people, is listed here.
> - Questions and criteria were drafted by a model and approved for this demonstration by 'Demo reviewer (simulated, not an expert)'. No acquisition expert has reviewed them.
> - The answering models (Claude Haiku 4.5, Claude Sonnet 5) were run through Claude Code rather than the API, closed-book, and their answers are replayed from recordings. Latency, token counts and cost were not recorded.
> - The judge (Claude Opus 5.5) graded each answer blind to which model wrote it, and judged all of one answer's criteria in a single pass rather than one call per criterion. Its verdicts are replayed one criterion at a time.
> - Calibration labels come from 'Demo reviewer (simulated, not an expert)', not a qualified expert. The labels were written by an instance of the same model as the judge, working from the answers without seeing the judge's verdicts, so agreement between the two is expected and shows how the measurement works, not how far to trust the judge.

## Key measurements

- **closed_book:** highest pass rate 70.7% (Claude Sonnet 5); lowest 32.0% (Claude Haiku 4.5); 2 models.
- **By phase:** from 38.3% (post-award) to 73.3% (pre-award), pooled over all models.
- **By task:** from 47.1% (knowledge) to 62.0% (boundary), pooled over all models.
- **Judge agreement with a simulated reviewer (not an expert):** 97.8% over 90 criterion verdicts. Agreement with qualified experts has not been measured.

## Results

Pass rate by model and condition, sorted by **closed_book**. A dash means the model did not run under that condition or had nothing judged.

| Model | closed_book |
| --- | ---: |
| Claude Sonnet 5 | 70.7% |
| Claude Haiku 4.5 | 32.0% |

### Detail

| Model | Condition | Pass rate | Criteria met / judged | Not judged | Questions | Cost per test | Median latency | Errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Claude Haiku 4.5 | closed_book | 32.0% | 48 / 150 | 0 | 30 | not recorded | not recorded | 0 |
| Claude Sonnet 5 | closed_book | 70.7% | 106 / 150 | 0 | 30 | not recorded | not recorded | 0 |

## Breakdowns

### By phase

Pooled over all models and conditions. Values with fewer than five questions are shown but marked, and are not read as findings.

| Phase | Questions | Criteria judged | Pass rate |
| --- | ---: | ---: | ---: |
| pre-award | 6 | 60 | 73.3% |
| solicitation | 6 | 60 | 56.7% |
| award | 6 | 60 | 45.0% |
| cross-cutting | 6 | 60 | 43.3% |
| post-award | 6 | 60 | 38.3% |

### By split

Pooled over all models and conditions. Values with fewer than five questions are shown but marked, and are not read as findings.

| Split | Questions | Criteria judged | Pass rate |
| --- | ---: | ---: | ---: |
| public | 30 | 300 | 51.3% |

### By task

Pooled over all models and conditions. Values with fewer than five questions are shown but marked, and are not read as findings.

| Task | Questions | Criteria judged | Pass rate |
| --- | ---: | ---: | ---: |
| boundary | 5 | 50 | 62.0% |
| document-review (too few questions) | 4 | 40 | 60.0% |
| knowledge | 21 | 210 | 47.1% |

## Grading

Each answer was checked against each of its criteria separately by a model judge (Claude Opus 5.5; mode: per_criterion). A criterion the judge could not decide is excluded from the pass rate and counted under *not judged*.

### Agreement with a simulated reviewer

**Simulated reviewer.** In this demonstration the labels below come from a stand-in reviewer, not a qualified expert. The table shows how the agreement measurement works; it is not evidence that the judge agrees with experts.

1 reviewer(s) labelled 90 criteria (90 comparisons). Only reviews that counted as qualified under the platform's expertise rules are compared.

| | Reviewer: pass | Reviewer: fail |
| --- | ---: | ---: |
| **Judge: pass** | 46 | 0 |
| **Judge: fail** | 2 | 42 |

- Agreement: **97.8%**
- False passes (judge passed what the reviewer failed), as a share of reviewer fails: **0.0%**. These inflate scores.

## Example

**Market research for a help-desk services requirement** — Claude Haiku 4.5 under closed_book. 2 of 5 criteria met. Result `5c17dbcf-2ab5-488c-831c-589a5454e460`, SHA-256 `8399e28219ccc285270e99e7d7d93aac94331ae76235de78450d52271a7e44f1`.

**Question**

> I'm a contract specialist starting on a new requirement: IT help-desk support for about 1,200 users at one installation, estimated at $6 million over five years. The program office wants to "just use the incumbent". What market research should I do before we decide how to buy this, and what do I need to have on paper at the end of it?

**Answer**

> Before making a sole-source determination, conduct thorough market research to document alternatives. Start by identifying: (1) comparable IT support services available from other contractors—at least three potential competitors; (2) the incumbent's current performance using measurable data (uptime, ticket response times, customer satisfaction); (3) cost reasonableness through benchmarking against industry rates for similar work; (4) technical capabilities needed that might differentiate bidders; (5) any barriers to entry (certifications, security clearances, facility requirements). You must document findings in a market research report showing you considered full and open competition and why—if economically practical. If three capable competitors exist, the rule of two applies and you're headed toward competitive procurement. Document SAM registrations, past performance records, and capability statements. Conclude with a clear recommendation: competitive solicitation vs. justification for the incumbent. This supports your acquisition strategy and withstands GAO protest scrutiny.

| Criterion | Verdict | Judge's reason |
| --- | --- | --- |
| Recommends publishing a sources-sought notice or RFI on SAM.gov to identify capable sources, including small businesses. | fail | Does not recommend a sources-sought notice or RFI on SAM.gov. |
| States that the results of market research must be documented in the contract file (a market research report or memo). | pass | States findings must be documented in a market research report. |
| Connects the market research to the small business set-aside decision (whether two or more capable small businesses exist). | fail | Mentions the rule of two but does not connect it to small business capability or a set-aside. |
| Recommends checking existing contract vehicles or required sources, such as GSA schedules, GWACs or agency IDIQs. | fail | Does not mention existing contract vehicles or required sources. |
| Does not treat the program office's preference for the incumbent as a sufficient basis for the acquisition approach. | pass | Requires research into alternatives before any sole-source decision rather than accepting the preference. |

## Methodology

### Dataset

- **30 questions**, **150 criteria** (5.0 per question).
- Split: public 30.
- Packs: `bench-acquisition-questions 0.1.0`.
- Expertise required to judge: acquisition.
- Approved for use by: Demo reviewer (simulated, not an expert).
- 30 question(s) were drafted by a model. For this demonstration they were approved by the stand-in named above, not by an expert.

### Conditions

Each model ran under each condition listed below as a separate system version, with the same questions. The exact configuration of each is the system version's snapshot, identified in the detail table by model and condition.

- closed_book

### Scoring

Pass rate = criteria met ÷ criteria judged, pooled over every question the model answered under that condition. Criteria the judge did not decide are excluded from both and reported separately. Cost per test is computed from recorded token counts and the prices declared on the system version; where either is missing it is reported as not recorded, not as zero.

## Limitations

- Demonstration data. The stand-ins listed at the top of this report replace steps a published benchmark gives to people; none of these figures is a finding.
- Too few questions to read as findings: task = document-review (4).
- Cost is not recorded for 2 model/condition pair(s): no declared prices, or no token counts from the connector.
- Judge agreement rests on 90 comparisons; treat the agreement figure as indicative.

## How to read this

The pass rate is the share of judged criteria that answers met on this question set. It is a measurement on these questions under these conditions. It is not a trust score, and it does not stand for performance on any other task.

This report states measurements only. Interpretation and recommendations are the publishing program's, and are published alongside it.

---

**UNCLASSIFIED**