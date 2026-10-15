#!/usr/bin/env python3
"""Emit the byte-identical reproducibility manifest.

Writes a single JSON document listing every piece of evidence the paper
cites, with digests and provenance. The purpose is to give a reviewer
one file that names every input to every headline number and points at
where the raw evidence is committed.

Usage:  python research/reproducibility/manifest.py > MANIFEST.json
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha256_of(p: Path) -> str | None:
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def digest_dir(p: Path) -> dict[str, str]:
    out = {}
    if not p.is_dir():
        return out
    for f in sorted(p.rglob("*")):
        if f.is_file():
            rel = f.relative_to(p).as_posix()
            out[rel] = sha256_of(f) or ""
    return out


def survey_files() -> dict:
    return {
        rel: sha256_of(ROOT / "survey" / "out" / rel)
        for rel in [
            "records-active-go-final.jsonl",
            "records-active-java-final.jsonl",
            "records-active-javascript-final.jsonl",
            "records-active-python-final.jsonl",
            "records-active-rust-final.jsonl",
        ]
    }


def carriage_files() -> dict:
    d = ROOT / "research" / "carriage-study" / "results"
    return {p.name: sha256_of(p) for p in sorted(d.glob("*.jsonl"))}


def harness_case_summary() -> dict:
    """Digest of each harness_case directory."""
    d = ROOT / "tests" / "harness_cases"
    out = {}
    if not d.is_dir():
        return out
    for harness_dir in sorted(d.iterdir()):
        if not harness_dir.is_dir():
            continue
        for case_dir in sorted(harness_dir.iterdir()):
            if not case_dir.is_dir():
                continue
            key = f"{harness_dir.name}/{case_dir.name}"
            out[key] = digest_dir(case_dir)
    return out


def new_evidence_summary() -> dict:
    return {
        "delegation_matrix_report": sha256_of(
            ROOT / "research/harness-matrix/delegation_matrix_report.md"),
        "delegation_matrix_raw": sha256_of(
            ROOT / "research/harness-matrix/delegation_matrix_raw.jsonl"),
        "consequence_summary": sha256_of(
            ROOT / "research/harness-matrix/consequence_cases/SUMMARY.md"),
        "consequence_case_A_result": sha256_of(
            ROOT / "research/harness-matrix/consequence_cases/case_A/result.json"),
        "consequence_case_B_result": sha256_of(
            ROOT / "research/harness-matrix/consequence_cases/case_B/result.json"),
        "consequence_case_C_result": sha256_of(
            ROOT / "research/harness-matrix/consequence_cases/case_C/result.json"),
        "web_mediated_manifest": sha256_of(
            ROOT / "research/harness-matrix/web_mediated/manifest.json"),
        "web_mediated_report": sha256_of(
            ROOT / "research/harness-matrix/web_mediated/REPORT.md"),
    }


def main() -> int:
    payload = {
        "ovrin_version": "0.1.0-alpha",
        "reproducibility_frame": "offline recomputation from committed records",
        "runtime_seed_in_agent_campaign": 1729,
        "survey_seed": 20260811,
        "survey_snapshot": "2026-08-11",
        "activity_cutoff": "2026-05-13",
        "harnesses_measured": ["codex-cli 0.147.0", "claude-code 2.1.229",
                                "gemini-cli 0.60.0"],
        "models_recorded": ["gpt-5.6-sol", "claude-sonnet-5", "gemini-2.5-pro"],
        "counts": {
            "usable_repositories": 2470,
            "instruction_prevalence": "942/2470",
            "file_level_governance_gap": "424/1389",
            "repository_level_governance_gap": "71/256",
            "carriage_positive_carriers": 180,
            "carriage_carried_files": 431,
            "compound_exposure": "129/180",
        },
        "survey_records": survey_files(),
        "carriage_records": carriage_files(),
        "harness_case_directories": harness_case_summary(),
        "new_evidence": new_evidence_summary(),
        "notes": {
            "sim_vs_live": (
                "Consequence and Web-mediated cases carry SIM counts derived "
                "deterministically from Section 7 cell rates (seed=1729). LIVE "
                "runs against paid coding-agent APIs are not reproduced here; "
                "their raw per-trial logs are the harness_case directories."
            ),
            "delegation_gate_role": (
                "Ovrin's delegation-gate implements the paper's IAD "
                "definition IAD <=> A_h(x,c)=1 AND D(P(x),c)=0 directly. "
                "The static-gate is retained as a backward-compatible "
                "heuristic and used only when no policy is supplied."
            ),
        },
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
