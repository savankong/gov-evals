"""Aegis Eval command line.

Built for CI (PRD section 66) and for disconnected work where a browser is not
available. The exit codes are the contract:

    0  the requested check passed
    1  the check failed -- a gate blocked, or a regression was detected
    2  usage or configuration error
    3  the check could not be determined

Exit 3 exists on purpose. "Could not determine" is a different answer from
"passed", and a pipeline should be able to treat it differently.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from .client import Aegis, AegisError, Campaign

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_UNDETERMINED = 3

STATUS_LABEL = {
    "pass": "PASS",
    "warning": "WARNING",
    "fail": "FAIL",
    "error": "ERROR",
    "not_evaluated": "NOT EVALUATED",
    "pending_human": "AWAITING REVIEW",
}


def out(message: str = "") -> None:
    print(message, file=sys.stdout)


def err(message: str) -> None:
    print(message, file=sys.stderr)


def client_from(args: argparse.Namespace) -> Aegis:
    return Aegis(
        base_url=args.url,
        token=args.token,
        email=getattr(args, "email", None),
        password=getattr(args, "password", None),
    )


def emit(value: Any, as_json: bool) -> None:
    if as_json:
        out(json.dumps(value, indent=2, default=str))


# -- commands ---------------------------------------------------------------


def cmd_health(args: argparse.Namespace) -> int:
    client = client_from(args)
    body = client.health()
    if args.json:
        emit(body, True)
    else:
        out(f"status           {body.get('status')}")
        out(f"version          {body.get('version')}")
        out(f"queue            {body.get('queue', {}).get('backend')}")
        out(f"evidence backend {body.get('evidence_backend')}")
        out(f"egress policy    {body.get('egress_policy')}")
        out(f"telemetry        {'enabled' if body.get('telemetry_enabled') else 'disabled'}")
    return EXIT_OK


def cmd_projects(args: argparse.Namespace) -> int:
    client = client_from(args)
    projects = client.projects.list()
    if args.json:
        emit(projects, True)
        return EXIT_OK
    if not projects:
        out("No projects.")
        return EXIT_OK
    for project in projects:
        out(f"{project['id']}  {project['classification']:<14} {project['name']}")
    return EXIT_OK


def cmd_packs(args: argparse.Namespace) -> int:
    client = client_from(args)
    packs = client.get("/packs")["packs"]
    if args.json:
        emit(packs, True)
        return EXIT_OK
    for pack in packs:
        out(f"{pack['kind']:<11} {pack['key']:<26} v{pack['version']}  {pack['name']}")
    return EXIT_OK


def render_campaign(campaign: Campaign) -> None:
    summary = campaign.summary()
    out(f"\nCampaign {campaign.raw.get('name')}  [{campaign.status}]")
    out(
        f"  {summary.get('executed', 0)} executions across {summary.get('runs', 0)} runs: "
        f"{summary.get('passed', 0)} passed, {summary.get('warning', 0)} warning, "
        f"{summary.get('failed', 0)} failed, {summary.get('errors', 0)} errored, "
        f"{summary.get('pending_human', 0)} awaiting human review"
    )

    out("\n  By dimension")
    for domain, bucket in sorted((summary.get("domains") or {}).items()):
        label = STATUS_LABEL.get(bucket["status"], bucket["status"])
        out(f"    {domain.replace('_', ' '):<24} {label:<16} {bucket['passed']}/{bucket['executed']} passed")

    findings = {k: v for k, v in (summary.get("findings") or {}).items() if v}
    if findings:
        out("\n  Findings opened: " + ", ".join(f"{v} {k}" for k, v in findings.items()))

    if campaign.unevaluated_runs:
        out(
            f"\n  {len(campaign.unevaluated_runs)} evaluation(s) reached no judgement. "
            "These are not passes:"
        )
        for run in campaign.unevaluated_runs[:8]:
            reason = "no threshold set" if not run.raw.get("threshold") else "nothing scoreable"
            out(f"    - {run.evaluation} ({reason})")

    if campaign.failed_runs:
        out(f"\n  {len(campaign.failed_runs)} evaluation(s) failed:")
        for run in campaign.failed_runs[:12]:
            out(f"    - {run.evaluation}: {run.raw.get('failed')}/{run.raw.get('scenario_count')} failed")


def cmd_evaluate(args: argparse.Namespace) -> int:
    client = client_from(args)

    thresholds = {}
    if args.threshold:
        for item in args.threshold:
            if "=" not in item:
                err(f"Malformed --threshold {item!r}. Expected evaluation_key=json")
                return EXIT_USAGE
            key, raw = item.split("=", 1)
            try:
                thresholds[key] = json.loads(raw)
            except json.JSONDecodeError as exc:
                err(f"Malformed threshold JSON for {key!r}: {exc}")
                return EXIT_USAGE

    try:
        campaign = client.evaluate(
            project_id=args.project,
            system_version_ids=args.system_version,
            name=args.name,
            suite=args.suite,
            evaluation_keys=args.evaluation or None,
            plan_id=args.plan,
            thresholds=thresholds,
            wait=not args.no_wait,
            timeout_seconds=args.timeout,
        )
    except AegisError as exc:
        err(f"Evaluation failed: {exc}")
        return EXIT_USAGE

    if args.no_wait:
        out(campaign.id)
        return EXIT_OK

    if args.json:
        emit({"campaign": campaign.raw, "runs": [r.raw for r in campaign.runs]}, True)
    else:
        render_campaign(campaign)

    if args.fail_on_finding and campaign.failed_runs:
        return EXIT_FAILED
    return EXIT_OK


def cmd_gate(args: argparse.Namespace) -> int:
    """Check a deployment gate. Intended as the last step of a pipeline."""
    client = client_from(args)
    try:
        result = client.gates.check(args.gate, args.campaign)
    except AegisError as exc:
        err(f"Gate check failed: {exc}")
        return EXIT_USAGE

    if args.json:
        emit(result.raw, True)
    else:
        out(result.explain())

    if result.passed:
        return EXIT_OK
    if result.status == "not_evaluated":
        err(
            "\nThe gate could not be determined: at least one criterion was not measured. "
            "This is not a pass."
        )
        return EXIT_UNDETERMINED
    return EXIT_FAILED


def cmd_regression(args: argparse.Namespace) -> int:
    client = client_from(args)
    try:
        diff = client.campaigns.regression(args.campaign, args.baseline)
    except AegisError as exc:
        err(f"Regression comparison failed: {exc}")
        return EXIT_USAGE

    if args.json:
        emit(diff, True)
    else:
        totals = diff["totals"]
        out(
            f"{diff['candidate_campaign']['name']} vs {diff['baseline_campaign']['name']}\n"
            f"  new failures {totals['new_failures']}   degraded {totals['degraded']}   "
            f"resolved {totals['resolved']}   improved {totals['improved']}"
        )
        for comparison in diff["comparisons"]:
            for failure in comparison.get("new_failures", [])[:5]:
                out(
                    f"    NEW FAILURE  {comparison.get('evaluation_key')}: "
                    f"{failure['scenario_key']}"
                )

    return EXIT_FAILED if diff["regression_detected"] else EXIT_OK


def cmd_findings(args: argparse.Namespace) -> int:
    client = client_from(args)
    findings = client.findings.list(args.project, severity=args.severity)
    if args.json:
        emit(findings, True)
        return EXIT_OK
    if not findings:
        out("No findings.")
        return EXIT_OK
    for finding in findings:
        out(f"{finding['key']}  {finding['severity']:<9} {finding['status']:<16} {finding['title']}")
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    client = client_from(args)
    try:
        report = client.reports.generate(
            args.project, args.kind, campaign_id=args.campaign
        )
    except AegisError as exc:
        err(f"Report generation failed: {exc}")
        return EXIT_USAGE

    if args.output:
        with open(args.output, "w") as handle:
            handle.write(report["body"])
        out(f"Wrote {args.output}  (sha256 {report['sha256']})")
    else:
        out(report["body"])
    return EXIT_OK


# -- parser -----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aegis",
        description="Aegis Eval command line. Evaluate AI systems against mission requirements.",
        epilog=(
            "Exit codes: 0 passed, 1 failed, 2 usage error, 3 could not be determined. "
            "Code 3 is deliberate: an unmeasured check is not a passed check."
        ),
    )
    parser.add_argument("--url", default=os.getenv("AEGIS_URL"), help="API base URL")
    parser.add_argument("--token", default=os.getenv("AEGIS_TOKEN"), help="Bearer token")
    parser.add_argument("--email", default=os.getenv("AEGIS_EMAIL"), help=argparse.SUPPRESS)
    parser.add_argument("--password", default=os.getenv("AEGIS_PASSWORD"), help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="Show deployment status").set_defaults(func=cmd_health)
    sub.add_parser("projects", help="List projects").set_defaults(func=cmd_projects)
    sub.add_parser("packs", help="List installed evaluation packs").set_defaults(func=cmd_packs)

    evaluate = sub.add_parser("evaluate", help="Run an evaluation campaign")
    evaluate.add_argument("--project", required=True, help="Project id")
    evaluate.add_argument(
        "--system-version", required=True, action="append",
        help="System version id. Repeat to compare several under identical conditions.",
    )
    evaluate.add_argument("--suite", help="Evaluation pack key, e.g. genai-baseline")
    evaluate.add_argument("--evaluation", action="append", help="Evaluation key. Repeatable.")
    evaluate.add_argument("--plan", help="Approved evaluation plan id")
    evaluate.add_argument("--name", help="Campaign name")
    evaluate.add_argument(
        "--threshold", action="append", metavar="KEY=JSON",
        help='Threshold per evaluation, e.g. --threshold citation-accuracy=\'{"min_pass_rate":0.98}\'',
    )
    evaluate.add_argument("--no-wait", action="store_true", help="Queue and print the campaign id")
    evaluate.add_argument("--timeout", type=float, default=1800.0, help="Seconds to wait")
    evaluate.add_argument(
        "--fail-on-finding", action="store_true", help="Exit 1 if any evaluation failed"
    )
    evaluate.set_defaults(func=cmd_evaluate)

    gate = sub.add_parser("gate", help="Check a deployment gate")
    gate.add_argument("--gate", required=True, help="Gate id")
    gate.add_argument("--campaign", required=True, help="Campaign id to check against")
    gate.set_defaults(func=cmd_gate)

    regression = sub.add_parser("regression", help="Compare a campaign against a baseline")
    regression.add_argument("--campaign", required=True)
    regression.add_argument("--baseline", help="Baseline campaign id")
    regression.set_defaults(func=cmd_regression)

    findings = sub.add_parser("findings", help="List findings")
    findings.add_argument("--project", required=True)
    findings.add_argument("--severity", choices=["critical", "high", "medium", "low", "info"])
    findings.set_defaults(func=cmd_findings)

    report = sub.add_parser("report", help="Generate a report")
    report.add_argument("--project", required=True)
    report.add_argument(
        "--kind", default="executive_summary",
        choices=["executive_summary", "findings", "comparison", "evaluation_plan", "assurance_case"],
    )
    report.add_argument("--campaign", help="Campaign id, where the report needs one")
    report.add_argument("--output", "-o", help="Write to a file instead of stdout")
    report.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except AegisError as exc:
        err(f"error: {exc}")
        return EXIT_USAGE
    except KeyboardInterrupt:
        err("interrupted")
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
