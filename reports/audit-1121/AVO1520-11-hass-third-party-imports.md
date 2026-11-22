# Hass and storefront Python dependency inventory

| Check | Finding |
| --- | --- |
| R1. Module-scope third-party imports | Only `PIL` (Pillow): 4 unguarded files and 17 more with module-scope `try` imports. CI pins Pillow to `12.0.0` in the quick job and Hass shards; there is no tracked Python requirements file or `pyproject.toml`. |
| R2. Deferred or guarded imports | `PIL` occurs inside functions or `try` blocks in 28 files. `httpx` and three Hermes-supplied module roots (`agent`, `hermes_bootstrap`, `plugins`) appear only in the two deferred Hermes adapters; no repo CI install step names them. |
| R3. Declared but not imported | None. The host note names Pillow, which the code imports as `PIL`. |
| R4. Main gap | CI pins and checks Pillow, but its install steps do not establish that the separately supplied Hermes runtime can load its adapters. No build or install change recommended from this static audit alone. |

Base: `37feae1dc5efa6968f90d17a1eda6daed29afd4a` (`origin/main` at checkout). All line references below are at that base.

## R1. Module-scope imports

| Python import root → distribution | Distinct files and source examples | Named in requirements? | Named in CI install? |
| --- | --- | --- | --- |
| `PIL` → Pillow | **21 total:** 4 unguarded (`hass/newitem_demo.py:14`, `hass/tests/chaos/make_photos.py:11`, `hass/tests/npp/make_npp_photos.py:24`, `hass/tests/test_npp_photo.py:11`) and 17 within a module-scope `try` (all listed in R2). Counting every scope: 44 import statements in 32 files. | No tracked `requirements*.txt` or `pyproject.toml` anywhere in the tree (see replay below). | Yes: `.github/workflows/check.yml:51` pins `12.0.0`; quick installs at lines 85–89 and verifies at lines 91–92; Hass shards install at lines 164–168. No Pillow install in the site job (lines 198–218; the shared action's installs are browser tooling, `.github/actions/test-env/action.yml:14–26`). |

`hass`, `mac`, `scripts`, and the bare `house_style` look non-stdlib but are repository code, not external packages. Examples: `hass/answer_reader.py:13`, `hass/tests/test_attach.py:13` (`mac/hass_forwarder.py`), `hass/tests/test_install_acceptance_receipt.py:11` (the tracked `scripts/hass/` namespace), and `hass/tests/test_house_style_cli_errors.py:14–15` (adds the `hass/` directory before importing `hass/house_style.py`). The scan found no third-party imports at any scope in `scripts/hass/*.py` or the three `storefront-mockup/*.py` files. The workflow's additional `tests/test_pillow_ci.py:12,16–20` imports Pillow and checks its version; it is outside the inventory paths and is not counted. Playwright in the shared action is a Node package, not a Python import (`.github/actions/test-env/install-playwright.sh:37–38`).

## R2. Function-local and try-scoped external imports

A function-local import defers the dependency; it does not make the feature work without it. For example, `hass/house_style.py:44–53` turns a missing Pillow import into `PillowMissing`. The test-level guards are not evidence that CI can omit the package: the separate CI check requires it (`tests/test_pillow_ci.py:1–4,12`).

| Import root | Context | All sites in that context |
| --- | --- | --- |
| `PIL` | Function, outside `try` (20 statements) | `hass/newitem_preview.py:113`, `hass/newitem_render.py:59`, `hass/newitem_synthetic.py:100,135`, `hass/photo_polish.py:412`, `hass/tests/chaos/run_chaos.py:321`, `hass/tests/test_item_intake_priced_text.py:52`, `hass/tests/test_newitem_synthetic_format.py:44,55`, `hass/tests/test_newitem_synthetic_orientation.py:39`, `hass/tests/test_photo_polish.py:79,226,244,296,333`, `hass/tests/test_publish_gate.py:253,332,407,445,531`. |
| `PIL` | Function and `try` (2 statements) | `hass/house_style.py:50`, `hass/tests/test_skills_acceptance_offline.py:354`. |
| `PIL` | Module-scope `try` (18 statements in 17 files) | `hass/tests/test_house_render_seam.py:26`, `hass/tests/test_newitem.py:24–25`, `hass/tests/test_newitem_demo.py:12`, `hass/tests/test_newitem_demo_alpha.py:10`, `hass/tests/test_newitem_render_16bit.py:14`, `hass/tests/test_newitem_render_alpha.py:8`, `hass/tests/test_newitem_render_gradient.py:8`, `hass/tests/test_newitem_render_holes.py:11`, `hass/tests/test_newitem_render_scale_warning.py:7`, `hass/tests/test_newitem_render_shadow_continuity.py:10`, `hass/tests/test_newitem_render_translucent_luma.py:17`, `hass/tests/test_newitem_synthetic.py:11`, `hass/tests/test_newitem_synthetic_alpha.py:15`, `hass/tests/test_newitem_synthetic_gps.py:8`, `hass/tests/test_newitem_synthetic_selectors.py:11`, `hass/tests/test_photo_polish.py:30`, `hass/tests/test_photo_polish_ocr_tsv.py:8`. |
| `httpx` → `httpx` | Function (1 file) | `hass/cloud_codex_hermes.py:62`. The function explicitly uses the separate Hermes installation (lines 56–63). No requirements or CI install step names `httpx`. |
| `hermes_bootstrap` | Function; also `try` at the second site (2 files) | `hass/cloud_codex_hermes.py:61`, `hass/photo_polish_hermes.py:45`. Both load from the Hermes environment; no requirements or CI install step names this module. |
| `agent.auxiliary_client` | Function (1 file) | `hass/cloud_codex_hermes.py:63`. This is a Hermes module, not evidence for installing a distribution named `agent`; no requirements or CI install step names it. |
| `plugins.image_gen.openai-codex` | Dynamic import inside a function and `try` (1 file) | `hass/photo_polish_hermes.py:41–47`. This is a Hermes plugin, not evidence for installing a distribution named `plugins`; no requirements or CI install step names it. |

`hass/skills/item_picture.py:385` also checks whether `PIL` is discoverable with `find_spec`; that is not an import and does not add a file to the import count.

## R3. Named but unused packages

**None in scope.** `docs/hass/PILLOW-HOST.md:3–6,14,33–41` names Pillow and links it to `PIL`; R1/R2 show actual consumers. No requirements files or `pyproject.toml` were found. `pip` and `venv` in the note are install tooling, not declared application dependencies (`docs/hass/PILLOW-HOST.md:10–15`).

## R4. Ranked gaps

1. **Separate Hermes runtime, not verified by the repo's install steps.** The two adapters expect Hermes-supplied modules and `httpx`; a missing import can surface when an adapter is invoked, not when the ordinary module is imported (`hass/cloud_codex_hermes.py:56–63,71–77`; `hass/photo_polish_hermes.py:41–53`). Nothing in the tracked CI install steps establishes that runtime's dependency availability. That is not evidence of a missing package on any actual host.
2. **Pillow is pinned in CI but host setup is separate.** CI and the operator note agree on `12.0.0`; the note is an instruction, not an install receipt, and says the Mac attachment relay does not need Pillow (`.github/workflows/check.yml:49–51,85–92,164–168`; `docs/hass/PILLOW-HOST.md:3–6,49–52`). No missing Pillow declaration in CI and no demonstrated Mac dependency gap.

**Buildable unit: none recommended from this evidence.** Adding Pillow to a new requirements file would duplicate the existing CI and operator pins without proving host setup. Adding `httpx` alone would not supply the separately loaded Hermes modules (R2). No runtime or policy changes were made.

## Offline replay and limits

On 2026-11-21, the scratch command `python3 audit_imports.py avocado-shack origin/main --nested` parsed **1,164 tracked Python files** with Python 3.12.3: `hass/` recursively (1,076), `scripts/hass/` directly (85), and `storefront-mockup/` directly (3). The scratch script is not committed. To reconstruct it: enumerate paths with `git ls-tree -r --name-only -z`, read each selected blob with `git show REV:PATH`, run `ast.parse`, and walk the tree while keeping ancestors. For `Import`, split each alias name at its first dot; for absolute `ImportFrom`, split the source module at its first dot. Treat relative imports and the repository-local roots listed in R1 separately; subtract `sys.stdlib_module_names` from the absolute roots. Group by root, source line and presence of `FunctionDef`, `AsyncFunctionDef`, `Lambda`, `Try` or `TryStar` ancestors; deduplicate paths for file counts. The full scratch output includes 484 function/try import statements before filtering out stdlib and local imports. Review literal dynamic-load calls separately; computed imports, imports in generated source, and transitive dependencies of external code are not resolved by this inventory.

From a clean checkout of the audited base, these read-only commands cross-check the external import rows and install declarations. The grep uses single ERE escapes for literal punctuation; the commit ID keeps replay independent of later `origin/main` changes:

```sh
git ls-tree -r --name-only 37feae1dc5efa6968f90d17a1eda6daed29afd4a -- .github/workflows .github/actions
# In a clean checkout of the audited tree, expected output: none.
git ls-files ':(glob)**/requirements*.txt' ':(glob)**/pyproject.toml'
git grep -n -E '(^|[[:space:]])(from PIL|import PIL|import httpx|import hermes_bootstrap|from agent\.auxiliary_client)|import_module\("plugins\.' 37feae1dc5efa6968f90d17a1eda6daed29afd4a -- ':(glob)hass/**/*.py' ':(glob)scripts/hass/*.py' ':(glob)storefront-mockup/*.py'
git grep -n -E 'pip[[:space:]]+install|npm[[:space:]]+install|install-deps|PILLOW_VERSION' 37feae1dc5efa6968f90d17a1eda6daed29afd4a -- .github/workflows .github/actions/test-env
```

This was a source and install-step audit, not a CI run or an installation test. No project Python, package install, browser, site, host service or adapter was run. Archived storefront/commerce files and other Python paths were not scanned for imports (`AGENTS.md:3–5`; scope above).
