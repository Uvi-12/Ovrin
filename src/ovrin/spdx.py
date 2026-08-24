"""Export a manifest as SPDX 3.0 JSON-LD.

The argument, not the format, is the point: instruction files are software
artifacts that ship with a project and change how it is built. They belong in
the same bill of materials as everything else. We call the output SPDX-aligned,
not SPDX-compliant, until it has been through the official validator.
"""

from __future__ import annotations

from typing import Any

CONTEXT = "https://spdx.org/rdf/3.0.1/spdx-context.jsonld"
NS = "urn:ovrin"


def _sid(path: str) -> str:
    return f"{NS}:file-" + path.replace("/", "-").replace(".", "_")


def to_spdx(manifest: dict[str, Any], name: str = "agent-instructions") -> dict[str, Any]:
    created = manifest.get("generatedAt", "1970-01-01T00:00:00+00:00")
    tool = f"{NS}:tool-ovrin"
    graph: list[dict[str, Any]] = [
        {"type": "Tool", "spdxId": tool, "name": "ovrin"},
        {"type": "CreationInfo", "@id": f"{NS}:creation", "specVersion": "3.0.1",
         "created": created, "createdBy": [tool]},
    ]
    file_ids = []
    for e in manifest["instructions"]:
        sid = _sid(e["path"])
        file_ids.append(sid)
        node: dict[str, Any] = {
            "type": "software_File", "spdxId": sid, "creationInfo": f"{NS}:creation",
            "name": e["path"], "software_primaryPurpose": "configuration",
            "comment": (f"origin={e['origin']['class']}; "
                        f"reviewEnforceable={e['review']['enforceable']}; "
                        f"reachableBy=" + ",".join(
                            h for h, r in e["reachability"].items() if r["verdict"] == "loaded")),
        }
        if e.get("digest"):
            algo, _, val = e["digest"].partition(":")
            node["verifiedUsing"] = [{"type": "Hash", "algorithm": algo, "hashValue": val}]
        graph.append(node)
    graph.append({"type": "software_Sbom", "spdxId": f"{NS}:sbom",
                  "creationInfo": f"{NS}:creation", "name": name,
                  "software_sbomType": ["build"], "rootElement": file_ids})
    return {"@context": CONTEXT, "@graph": graph}
