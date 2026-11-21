# AVO1520-01 — Clover module imports

| Question | Result on main |
| --- | --- |
| What imports what? (R1) | 23 Python files, including `__init__.py` (22 named submodules); 53 distinct internal dependency edges. |
| Are any imports circular? (R2) | No cycle found in the direct internal import graph, including imports inside functions. |
| Which modules have only test imports from outside the package? (R3) | 14. Ten of those are imported inside Clover; three have no sibling importer (`bundle`, `checks`, and `qty_words`), and `cli` has a command entry point. `__init__.py` has no explicit imports targeting the initializer itself. |
| Which imported name is unused? (R3) | One static finding: `Request` at `hass/clover/transport.py:14`. |
| What should change? (R4) | No build unit recommended from this audit alone. An absent direct import does not establish that a module is dead. |

Source: `tidepool-labs/avocado-shack` `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, checked 2026-11-21. This matched the requested baseline. Source was parsed locally; no Hass modules were imported or executed, and no live system or state was checked. The historical `commerce/` and `storefront-mockup/archive/` trees are outside scope (`AGENTS.md:3–5`).

## R1. Direct imports by module

Internal arrows run **from** the row module **to** the modules listed in the middle column. The last column counts **distinct files**, not import statements; “test” includes helpers and replay tools under `hass/tests/`. Counts are for explicit Python imports, including local and conditional imports; multiple names on one line can point to different submodules. Each external example is a source line, not evidence that the line ran. The package initializer is loaded implicitly with submodule imports; that implicit load is not counted as a separate explicit edge.

| `hass/clover/` module | Imports from within Clover (source anchors) | Outside Clover: distinct direct importers (non-test, test); example |
| --- | --- | --- |
| `__init__` | none found | none found |
| `apply` | `drafts` (`hass/clover/apply.py:8`); `credential` (`hass/clover/apply.py:9`); `journal` (`hass/clover/apply.py:10`); `mapper` (`hass/clover/apply.py:11`) | 5 (0, 5); `hass/tests/test_clover_apply.py:10` |
| `approvals` | none found | 2 (1, 1); `hass/conversation.py:26` |
| `bundle` | `drafts` (`hass/clover/bundle.py:16`); `cache` (`hass/clover/bundle.py:17`); `chat` (`hass/clover/bundle.py:18`); `mapper` (`hass/clover/bundle.py:19`) | 1 (0, 1); `hass/tests/test_item_both.py:11` |
| `cache` | `mapper` (`hass/clover/cache.py:28`); `reads` (`hass/clover/cache.py:29`) | 16 (3, 13); `hass/health.py:266` |
| `chat` | `cache`, `drafts`, `links`, `reads` (`hass/clover/chat.py:18`); `reports` (`hass/clover/chat.py:18`, `hass/clover/chat.py:198`); `apply` (`hass/clover/chat.py:19`); `config` (`hass/clover/chat.py:20`); `mapper` (`hass/clover/chat.py:21`) | 16 (3, 13); `hass/host.py:477` |
| `checks` | `mapper`, `reads` (`hass/clover/checks.py:6`) | 1 (0, 1); `hass/tests/test_clover_checks.py:6` |
| `cli` | `cache`, `client`, `credential`, `sync` (`hass/clover/cli.py:35`); `config` (`hass/clover/cli.py:36`); `transport` (`hass/clover/cli.py:99`); `reports` (`hass/clover/cli.py:185`, `hass/clover/cli.py:225`); `pos` (`hass/clover/cli.py:210`); `links` (`hass/clover/cli.py:225`) | 5 (0, 5); `hass/tests/test_clover_cli.py:22` |
| `client` | none found | 14 (0, 14); `hass/tests/clover_fake.py:6` |
| `config` | `mapper` (`hass/clover/config.py:11`) | 15 (3, 12); `hass/host.py:120` |
| `credential` | none found in the import-only scan | 14 (3, 11); `hass/health.py:267` |
| `drafts` | `sku` (`hass/clover/drafts.py:17`); `mapper` (`hass/clover/drafts.py:18`) | 7 (0, 7); `hass/tests/test_clover_apply.py:9` |
| `dryrun` | `chat`, `credential`, `drafts` (`hass/clover/dryrun.py:5`); `client` (`hass/clover/dryrun.py:6`); `mapper` (`hass/clover/dryrun.py:7`); `transport` (`hass/clover/dryrun.py:8`) | 3 (1, 2); `hass/host.py:480` |
| `journal` | `cache` (`hass/clover/journal.py:10`) | 3 (1, 2); `scripts/hass/clover_write_readiness.py:18` |
| `links` | `cache`, `reports` (`hass/clover/links.py:13`); `mapper` (`hass/clover/links.py:14`) | 1 (0, 1); `hass/tests/test_clover_links.py:12` |
| `mapper` | none found | 9 (0, 9); `hass/tests/test_clover_apply.py:14` |
| `pos` | `cache`, `reads`, `reports` (`hass/clover/pos.py:15`); `mapper` (`hass/clover/pos.py:16`) | 1 (0, 1); `hass/tests/test_clover_pos.py:15` |
| `qty_words` | none found | 2 (0, 2); `hass/tests/test_clover_qty_words.py:7` |
| `reads` | `mapper` (`hass/clover/reads.py:16`) | 6 (0, 6); `hass/tests/test_clover_checks.py:8` |
| `reports` | `cache`, `reads` (`hass/clover/reports.py:15`); `mapper` (`hass/clover/reports.py:16`) | 4 (1, 3); `hass/stock_site.py:19` |
| `sku` | `mapper` (`hass/clover/sku.py:16`) | 4 (0, 4); `hass/tests/test_clover_sku.py:9` |
| `sync` | `mapper` (`hass/clover/sync.py:13`) | 4 (0, 4); `hass/tests/test_clover_cache.py:17` |
| `transport` | `client` (`hass/clover/transport.py:14`) | 4 (0, 4); `hass/tests/clover_fake.py:7` |

The 50 unique outside files include seven non-test files: `hass/cloud_codex.py:8`, `hass/conversation.py:26`, `hass/health.py:266`, `hass/host.py:120`, `hass/stock_site.py:19`, `scripts/hass/clover_write_readiness.py:16`, and `scripts/hass/demo_rehearsal.py:257`. No direct imports were found in the named `hass/chat/`, `hass/skills/`, or `hass/ops/` trees. The literal scan also found test mock targets that can resolve a module by name: `apply` has one additional file (`hass/tests/test_clover_dryrun.py:170`); `credential` has two (`hass/tests/test_clover_chat.py:215`, `hass/tests/test_demo_rehearsal.py:73`). The other mock references are in already-counted files (`hass/tests/test_item_both.py:62`, `hass/tests/test_item_both.py:205`, `hass/tests/test_clover_dryrun.py:187`). An embedded child import also duplicates already-counted `cache` and `reports` imports (`hass/tests/test_clover_report_source_file.py:11`, `hass/tests/test_clover_report_source_file.py:17`). None of these adds a non-test importer.

## R2. Circular imports

None found **inside the package**. The offline checker resolved absolute and relative `Import`/`ImportFrom` nodes at every nesting level and ran Python's `graphlib.TopologicalSorter` on the internal edges above. The import-only check for `credential` found no internal dependency. The 2026-11-21 checker receipt was `FILES 23 EDGES 53 SITES 55`; all nodes sorted successfully, dependencies first:

`__init__`, `credential`, `mapper`, `approvals`, `client`, `qty_words`, `config`, `reads`, `sku`, `sync`, `transport`, `cache`, `checks`, `drafts`, `journal`, `reports`, `apply`, `links`, `pos`, `chat`, `cli`, `bundle`, `dryrun`.

This is not a check for cycles via another package or for run-time imports assembled from strings. The literal text at `hass/clover/cache.py:58` and the logger name at `hass/clover/client.py:19` do not add import edges.

## R3. Test-only imports and unused bindings

| Finding | Modules and evidence |
| --- | --- |
| Only test files import them from outside Clover, but other Clover modules import them | `apply`, `client`, `drafts`, `links`, `mapper`, `pos`, `reads`, `sku`, `sync`, `transport` (R1 table: test-only inbound counts; each also appears in another row's internal imports). |
| All direct importers are tests; no inbound import inside Clover | `bundle` (`hass/tests/test_item_both.py:11`), `checks` (`hass/tests/test_clover_checks.py:6`), and `qty_words` (`hass/tests/test_clover_qty_words.py:7`, `hass/tests/test_clover_count_phrases.py:10`). These are candidates for a reachability check, not proven dead. |
| Test-only *imports*, but explicit command entry point | `cli` has no sibling importer. Its `main` and `__main__` guard (`hass/clover/cli.py:235`, `hass/clover/cli.py:272`) mean that absence of a non-test import does not rule out direct invocation. |
| No explicit importer at all | `__init__` (`hass/clover/__init__.py:1–5`, R1); ordinary submodule imports still load the package initializer. No named submodule had zero outside direct importers when tests are included. |

Unused binding at `hass/clover/transport.py:14`:

> `from hass.clover.client import BODY_LIMIT, HOSTS, Request, Response`

Only **`Request`** is unused in this file, not the whole line. The 2026-11-21 static scan found no load of that name, no type-annotation use and no explicit `__all__` use; the other text hit is a docstring at `hass/clover/transport.py:35`. This is a conservative name-use scan, not proof against dynamic lookup, shadowing, an implicit re-export to outside callers, or import side effects. No other unused binding was found by this scan in the 22 fully parsed package files. Unused bindings in `credential` were not assessed; only package import names were checked there.

## R4. Ranked gaps

1. **Reachability of the three test-only modules.** `bundle`, `checks`, and `qty_words` have no direct non-test or sibling import edges (R3). Check intended entry points before drawing a removal conclusion. The `cli` entry point is a concrete reason not to use import counts alone.
2. **Import hygiene.** `Request` is not used in `transport` (R3); an unused binding alone is not evidence of a broken path or assurance that removing the name would be compatible.

**No build unit needed on the evidence here.** No cycle or failure was reproduced, and this report does not authorize deleting a module, changing runtime behavior, or making an owner decision.

## Read-only checks and limits

The 2026-11-21 checker parsed 1,156 tracked Python source files: the package, `hass/`, `scripts/hass/`, and other current-tree Python files with a case-insensitive `clover` text hit, with sensitive-looking filenames excluded from full parsing. The two module-specific test files were counted from restricted import matches only. The other two excluded test sources had no import-name hits in a restricted check. `credential` was never parsed or executed. No repository data or configuration files were inspected for this scan. Counts do not cover untracked or installed code, external consumers, non-Python or computed dispatch, or other branches.

From the clone, these checks replay the inventory and textual cross-checks on the audited main (searches use the pinned `origin/main`; `git grep` exit 1 with no output means no match):

```text
git rev-parse origin/main
git ls-tree -r --name-only origin/main -- hass/clover
git grep -l -i clover origin/main -- '*.py' ':!commerce/**' ':!storefront-mockup/archive/**' ':!*credential*' ':!*token*'
git grep -n -o -E '^[[:space:]]*(from (hass\.clover([.]|[[:space:]])|[.])|import .*hass\.clover)' origin/main -- hass/clover/credential.py
git grep -n -o -E 'from hass\.clover(\.credential)? import|import hass\.clover\.credential' origin/main -- hass/tests/test_clover_credential.py hass/tests/test_clover_credential_parent.py
git grep -n -o -w Request origin/main -- hass/clover/transport.py
```

The grep checks are spot checks, not the source of the import counts. To reproduce the graph, parse the selected source with `ast.parse`, walk `Import` and `ImportFrom` and resolve relative imports against each file's package. For `from hass.clover import x`, count the named submodule rather than a separate implicit initializer edge. Group edges by source/target module with line numbers and group outside hits by target/distinct file; then topologically sort the 23 internal rows (including empty rows). For the unused-name check, compare imported bindings with AST name loads, string annotations and explicit exports; disregard `__future__` directives. No integration or runtime tests were run.
