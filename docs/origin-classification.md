# Origin classification

How Ovrin decides where a file came from. The order is deliberate.

1. Submodule. If the path is registered in `.gitmodules`, it is a submodule, whatever else is true.
2. Vendored or installed. If the path sits under a vendor marker such as `node_modules`, `vendor`, `third_party`, `site-packages`, `.venv`, `Pods`, `go/pkg/mod`, or `.cargo/registry`, it came from outside the project. If it is tracked in git it was committed, so `vendored`. If it is not tracked it was installed, so `installed-dependency`.
3. Workspace. A tracked file under `packages/`, `apps/`, or `libs/` in a repo that declares workspaces is a workspace member.
4. Repo. A tracked file with none of the above is the project's own.
5. Untracked. On disk, not tracked, in a git repo.
6. Unknown. Not a git repository, so origin cannot be decided.

The `vendored` versus `installed-dependency` split matters for review. A
committed vendor tree appears in pull request diffs and can be gated. An
installed dependency never appears in a diff, so no amount of review discipline
covers it. Naming them separately keeps the review story honest.

For npm, the package identity is resolved from the nearest `package.json` to a
`name@version`. Other ecosystems report the container without inventing a
version.
