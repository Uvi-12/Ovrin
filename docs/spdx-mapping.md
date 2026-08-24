# SPDX mapping

## The argument

A bill of materials answers "what ships with this software?" Agent instruction
files ship with the software and change how it is built and modified. They
belong in the answer. Today they are invisible to every SBOM generator, because
generators enumerate packages and these are loose files with no package
identity.

## The mapping

| Ovrin | SPDX 3.0 |
| --- | --- |
| an instruction file | `software_File` element |
| `digest` | `verifiedUsing` with a `Hash`, algorithm `sha256` |
| `path` | `name` |
| configuration role | `software_primaryPurpose: configuration` |
| origin, review, reachability | `comment`, in 0.1.0 |
| the whole scan | `software_Sbom` with a `rootElement` list |

## What "aligned" means, and the honest limitation

We call the output SPDX 3.0-aligned, not SPDX-compliant, because it has not yet
been through the official SPDX validator. Do not claim compliance until the
validator output is in the repository.

Origin and reachability are serialised into `comment`, which is honest but not
queryable. The right home is either a set of relationships from the instruction
file to the package that carried it, or an extension profile. That is a question
for the SPDX community rather than something to decide alone, and it is the
concrete upstream proposal this project intends to bring: should an agent
instruction file be a first-class element, and what relationship expresses that
one package contributed a file to another project?

## Generating it

```
ovrin scan . -f spdx -o instructions.spdx.json
```
