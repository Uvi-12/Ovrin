from ovrin.harness import Harness, Rules, reachability


def _h(**kw):
    base = dict(id="t", name="T", open_source=True, reads=["AGENTS.md"],
                walks_tree=True, walks_ancestors=False, respects_ignore="unknown",
                precedence="nearest-first", confidence="observed", source="test")
    base.update(kw)
    return Harness(**base)


def test_root_only_skips_subdir():
    v, _ = reachability(_h(walks_tree=False), "a/AGENTS.md", is_ignored=False, origin_cls="repo")
    assert v == "not-discovered"


def test_ignored_documented_is_skipped():
    v, _ = reachability(_h(respects_ignore="documented"), "node_modules/x/AGENTS.md",
                        is_ignored=True, origin_cls="installed-dependency")
    assert v == "ignored"


def test_ignored_unknown_is_unverified():
    v, _ = reachability(_h(respects_ignore="unknown"), "node_modules/x/AGENTS.md",
                        is_ignored=True, origin_cls="installed-dependency")
    assert v == "unverified"


def test_tracked_vendor_tree_reachable():
    v, _ = reachability(_h(), "vendor/acme/AGENTS.md", is_ignored=False, origin_cls="vendored")
    assert v == "loaded"


def test_shipped_rules_have_source_and_confidence():
    for h in Rules.load().harnesses:
        assert h.confidence in {"observed", "documented", "inferred", "unknown"}
        assert h.source


def test_claude_code_does_not_read_agents_md():
    cc = Rules.load()
    h = next(x for x in cc.harnesses if x.id == "claude-code")
    v, _ = reachability(h, "AGENTS.md", is_ignored=False, origin_cls="repo")
    assert v == "not-discovered"
