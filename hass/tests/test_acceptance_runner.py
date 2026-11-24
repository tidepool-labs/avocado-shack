"""AVB-20 tests: drive acceptance.run(map, loader) with tiny temp modules.

Covers the frozen edge paths: pass/fail exit codes, reason strings, the
exit-2 bad-map cases (nothing run, proven by a counter module), import errors,
the --only subset, and test stdout never leaking into the runner output.
"""
import contextlib, importlib, io, json, os, shutil, sys, tempfile, textwrap, unittest
from unittest import mock

from hass import acceptance

_SEQ = [0]
OK = textwrap.dedent("""
    import unittest
    class T(unittest.TestCase):
        def test_a(self): self.assertTrue(True)
        def test_b(self): self.assertTrue(True)
""")
BAD = textwrap.dedent("""
    import unittest
    class T(unittest.TestCase):
        def test_a(self): self.assertTrue(True)
        def test_b(self): self.assertTrue(False)
""")
RAISES = "raise ImportError('boom at import')\n"
PRINTS = textwrap.dedent("""
    import unittest
    print('LEAK-MARKER')
    class T(unittest.TestCase):
        def test_a(self):
            print('LEAK-MARKER')
            self.assertTrue(True)
""")
COUNTER = textwrap.dedent("""
    import unittest
    RAN = []
    class T(unittest.TestCase):
        def test_a(self): RAN.append(1)
""")
EMPTY = "# no cases here\n"
HOOK_EMPTY = textwrap.dedent("""
    import unittest
    class T(unittest.TestCase):
        def test_a(self): self.assertTrue(True)
    def load_tests(loader, tests, pattern):
        return unittest.TestSuite()
""")


@contextlib.contextmanager
def temp_pkg(files):
    """Create a uniquely named throwaway package on sys.path; yield (name, dir)."""
    _SEQ[0] += 1
    parent = tempfile.mkdtemp(prefix="acc_parent_")
    name = "accpkg%d_%d" % (os.getpid(), _SEQ[0])
    pkgdir = os.path.join(parent, name)
    os.makedirs(pkgdir)
    for fn, src in dict(files, **{"__init__.py": ""}).items():
        with open(os.path.join(pkgdir, fn), "w") as fh:
            fh.write(src)
    sys.path.insert(0, parent)
    try:
        yield name, pkgdir
    finally:
        sys.path.remove(parent)
        shutil.rmtree(parent, ignore_errors=True)


def _full_map():
    return {i: ("test_ok",) for i in acceptance.ALL_IDS}


def _main(argv, name, pkgdir):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = acceptance.main(argv, map_=_full_map(), tests_pkg=name, tests_dir=pkgdir)
    return code, [ln for ln in buf.getvalue().splitlines() if ln.strip()]


class RunnerTest(unittest.TestCase):
    def _run(self, name, pkgdir, map_, ids=None):
        return acceptance.run(map_, unittest.TestLoader(), tests_pkg=name,
                              tests_dir=pkgdir, expected_ids=ids or tuple(map_))

    def test_pass_exit_zero_and_fail_exit_one(self):
        with temp_pkg({"test_ok.py": OK, "test_bad.py": BAD}) as (n, d):
            rows, code, probs = self._run(n, d, {"H01": ("test_ok",)})
            self.assertEqual((code, probs), (0, []))
            self.assertEqual(rows, [{"id": "H01", "result": "pass", "tests": 2,
                                     "failures": 0, "note": ""}])
            rows, code, _ = self._run(n, d, {"H01": ("test_bad",)})
            self.assertEqual(code, 1)
            self.assertEqual((rows[0]["result"], rows[0]["failures"]), ("fail", 1))

    def test_reason_string_is_not_covered_never_pass(self):
        with temp_pkg({"test_ok.py": OK}) as (n, d):
            rows, code, _ = self._run(n, d, {"H07": "needs Michael's devices"})
            self.assertEqual(code, 0)
            self.assertEqual(rows, [{"id": "H07", "result": "not covered", "tests": 0,
                                     "failures": 0, "note": "needs Michael's devices"}])

    def test_bad_map_exit_two_and_nothing_runs(self):
        with temp_pkg({"test_counter.py": COUNTER, "test_ok.py": OK}) as (n, d):
            cases = [({"H01": ("test_counter",), "H02": ("test_ghost",)},
                      ("H01", "H02"), "missing module: test_ghost"),
                     (dict(_full_map(), H26=("test_counter",)), acceptance.ALL_IDS,
                      "map: H26"),
                     ({i: ("test_counter",) for i in acceptance.ALL_IDS[1:]},
                      acceptance.ALL_IDS, "map: H01")]
            for map_, ids, problem in cases:
                rows, code, probs = self._run(n, d, map_, ids)
                self.assertEqual((code, rows), (2, []), problem)
                self.assertIn(problem, probs)
            # the counter module was never run (nor even imported)
            self.assertNotIn(n + ".test_counter", sys.modules)
            self.assertEqual(importlib.import_module(n + ".test_counter").RAN, [])

    def test_import_error_names_module_others_still_run(self):
        with temp_pkg({"test_ok.py": OK, "test_raises.py": RAISES}) as (n, d):
            rows, code, _ = self._run(n, d, {"H01": ("test_ok",), "H02": ("test_raises",),
                                             "H03": ("test_ok",)})
            by = {r["id"]: r for r in rows}
            self.assertEqual(code, 1)
            self.assertEqual((by["H02"]["result"], by["H02"]["note"]),
                             ("fail", "import error: test_raises"))
            for ok in ("H01", "H03"):
                self.assertEqual((by[ok]["result"], by[ok]["tests"]), ("pass", 2))

    def test_only_subset_and_unknown_id(self):
        with temp_pkg({"test_ok.py": OK}) as (n, d):
            self.assertEqual(_main(["--only", "H99"], n, d), (2, ["map: H99"]))
            self.assertEqual(_main(["--only", "H02,H99"], n, d)[0], 2)
            code, lines = _main(["--only", "H02"], n, d)
            self.assertEqual((code, len(lines)), (0, 2))
            self.assertEqual(json.loads(lines[0])["id"], "H02")
            self.assertEqual(json.loads(lines[1])["summary"]["ids"], 1)

    def test_test_stdout_does_not_leak(self):
        with temp_pkg({"test_prints.py": PRINTS}) as (n, d):
            outer = io.StringIO()
            with contextlib.redirect_stdout(outer):
                rows, code, _ = self._run(n, d, {"H01": ("test_prints",)})
            self.assertEqual((code, rows[0]["result"]), (0, "pass"))
            self.assertNotIn("LEAK-MARKER", outer.getvalue())

    def test_empty_covering_entry_is_bad_map_before_import(self):
        with temp_pkg({"test_counter.py": COUNTER}) as (n, d):
            for empty in ((), []):
                rows, code, probs = self._run(n, d, {"H01": ("test_counter",), "H02": empty},
                                              ("H01", "H02"))
                self.assertEqual((rows, code, probs), ([], 2, ["map: H02"]))
            # the counter module was never run (nor even imported)
            self.assertNotIn(n + ".test_counter", sys.modules)
            self.assertEqual(importlib.import_module(n + ".test_counter").RAN, [])

    def test_importable_empty_module_fails_with_zero_tests(self):
        with temp_pkg({"test_empty.py": EMPTY}) as (n, d):
            rows, code, probs = self._run(n, d, {"H01": ("test_empty",)})
            self.assertEqual((code, probs), (1, []))
            self.assertEqual(rows, [{"id": "H01", "result": "fail", "tests": 0,
                                     "failures": 1, "note": "no tests: test_empty"}])

    def test_empty_load_tests_hook_is_not_evidence(self):
        with temp_pkg({"test_hook.py": HOOK_EMPTY}) as (n, d):
            rows, code, _ = self._run(n, d, {"H01": ("test_hook",)})
            self.assertEqual(code, 1)
            self.assertEqual(rows, [{"id": "H01", "result": "fail", "tests": 0,
                                     "failures": 1, "note": "no tests: test_hook"}])

    def test_empty_module_is_not_masked_by_passing_sibling(self):
        files = {"test_empty.py": EMPTY, "test_counter.py": COUNTER, "test_ok.py": OK}
        for order in (("test_empty", "test_ok"), ("test_ok", "test_empty")):
            with temp_pkg(files) as (n, d):
                rows, code, _ = self._run(n, d, {"H01": order, "H02": ("test_counter",)})
                self.assertEqual(code, 1)
                self.assertEqual(rows[0], {"id": "H01", "result": "fail", "tests": 2,
                                           "failures": 1, "note": "no tests: test_empty"})
                self.assertEqual((rows[1]["result"], rows[1]["tests"]), ("pass", 1))
                self.assertEqual(importlib.import_module(n + ".test_counter").RAN, [1])

    def test_multiple_empty_modules_and_import_error_accounting(self):
        files = {"test_empty.py": EMPTY, "test_hook.py": HOOK_EMPTY, "test_bad.py": BAD,
                 "test_raises.py": RAISES, "test_ok.py": OK}
        with temp_pkg(files) as (n, d):
            rows, code, _ = self._run(n, d, {
                "H01": ("test_ok", "test_hook", "test_empty"),
                "H02": ("test_empty", "test_raises", "test_bad", "test_hook")})
            self.assertEqual(code, 1)
            self.assertEqual(rows[0], {"id": "H01", "result": "fail", "tests": 2,
                                       "failures": 2, "note": "no tests: test_hook"})
            # import-error note wins; 1 import error + 2 empty + 1 failed case
            self.assertEqual(rows[1], {"id": "H02", "result": "fail", "tests": 2,
                                       "failures": 4, "note": "import error: test_raises"})

    def test_reason_rows_and_nonempty_suites_preserve_contract(self):
        with temp_pkg({"test_ok.py": OK, "test_bad.py": BAD, "test_prints.py": PRINTS}) as (n, d):
            map_ = {"H07": "needs Michael's devices", "H18": "needs Michael's devices",
                    "H25": "release step", "H01": ("test_ok", "test_prints"),
                    "H02": ("test_bad",)}
            outer = io.StringIO()
            with contextlib.redirect_stdout(outer):
                rows, code, _ = self._run(n, d, map_)
            self.assertEqual(code, 1)
            self.assertNotIn("LEAK-MARKER", outer.getvalue())
            by = {r["id"]: r for r in rows}
            for id_, reason in (("H07", "needs Michael's devices"),
                                ("H18", "needs Michael's devices"), ("H25", "release step")):
                self.assertEqual(by[id_], {"id": id_, "result": "not covered", "tests": 0,
                                           "failures": 0, "note": reason})
            self.assertEqual(by["H01"], {"id": "H01", "result": "pass", "tests": 3,
                                         "failures": 0, "note": ""})
            self.assertEqual((by["H02"]["result"], by["H02"]["failures"], by["H02"]["note"]),
                             ("fail", 1, ""))

    def test_real_map_is_valid_on_disk(self):
        self.assertEqual(acceptance._validate(acceptance.MAP, acceptance._TESTS_DIR,
                                              acceptance.ALL_IDS), [])
        self.assertEqual({acceptance.MAP[i] for i in ("H07", "H18", "H25")},
                         {"needs Michael's devices", "release step"})
        self.assertEqual((acceptance.MAP["H23"], acceptance.MAP["H24"][0]),
                         (("test_auto_policy",), "test_design_check"))
        self.assertEqual(acceptance.MAP["H01"], ("test_content", "test_content_read_errors",
                         "test_browser_freshness", "test_publish"))
        self.assertEqual(acceptance.MAP["H02"], ("test_editor", "test_maker_product_batch"))
        self.assertEqual(acceptance.MAP["H03"][:7], ("test_catalog_ops", "test_clear_availability",
                         "test_product_new", "test_maker_hide_products", "test_maker_optional_url",
                         "test_product_default_brand", "test_maker_optional_story"))
        self.assertEqual(acceptance.MAP["H12"][:7], ("test_attachment_reply", "test_photo_draft",
                         "test_photo_on_product", "test_photo_new_product", "test_photo_home_image",
                         "test_photo_batch", "test_media_batch"))
        self.assertEqual(acceptance.MAP["H22"], ("test_interpreter_cap", "test_interpreter_prompt"))
        self.assertEqual(acceptance.MAP["H17"][:7], ("test_status_pause", "test_help",
                         "test_status_photos", "test_listing_command", "test_status_notice",
                         "test_social_draft_maker", "test_post_maker_command"))
        self.assertEqual(acceptance.MAP["H25"], "release step")
        self.assertEqual(acceptance.MAP["H04"][:9], ("test_hike_ops", "test_route_add",
                         "test_route_edit", "test_route_hide", "test_hike_samples",
                         "test_hike_repeat", "test_hike_ics", "test_hike_cancel_note",
                         "test_preview_cancel_note"))
        self.assertEqual(acceptance.MAP["H05"][:19], ("test_conversation", "test_near_approval",
                         "test_unknown_approval_code", "test_again", "test_interpreter_prompt_shelf_maker",
                         "test_interpreter_prompt_descriptions", "test_claims_health_awards",
                         "test_interpreter_no_undo", "test_field_words", "test_question_missing_fields",
                         "test_named_records", "test_interpreter_aliases", "test_social_message",
                         "test_interpret_check_enum", "test_shelf_labels",
                         "test_interpret_check_prices", "test_interpreter_prompt_design",
                         "test_proposal_notice_words", "test_shelf_check_flow"))
        self.assertEqual(acceptance.MAP["H06"], ("test_preview", "test_undo", "test_history_search",
                         "test_store_field_undo", "test_history_times",
                         "test_undo_cancel_phrases"))
        self.assertEqual(acceptance.MAP["H10"], ("test_label_reader", "test_label_reader_amounts",
                         "test_label_question_brand", "test_photos_to_take", "test_commands_doc",
                         "test_social_draft", "test_social_draft_inputs", "test_social_draft_text",
                         "test_social_draft_tags", "test_social_draft_fullwidth",
                         "test_social_draft_shapes", "test_post_command"))
        self.assertEqual(acceptance.MAP["H15"], ("test_memory", "test_memory_source",
                         "test_memory_alias", "test_memory_listing", "test_memory_unchanged",
                         "test_memory_chat", "test_limits_doc", "test_design_notes",
                         "test_interpreter_notes"))
        self.assertEqual(acceptance.MAP["H13"][:8], ("test_store_ops", "test_store_intro",
                         "test_store_headline", "test_store_story",
                         "test_store_home_image", "test_store_clear_home_image", "test_notice_start",
                         "test_club_intro"))
        for id_ in ("H03", "H04", "H05", "H06", "H10", "H12", "H13", "H15"):
            self.assertEqual(len(acceptance.MAP[id_]), len(set(acceptance.MAP[id_])))
        # AV2007-20: each module a unit added sits at the end of exactly its H row, and in no other row.
        # Contract: a later MAP edit must not silently drop or move an AV2007 module out of the standing run.
        added = {"H03": ("test_stock_product_choice", "test_plain_shelf_check", "test_shelf_check_except"),
                 "H04": ("test_nl_prep_calendar", "test_weekday_date_mismatch", "test_nl_prep_ordinal_words"),
                 "H05": ("test_repeat_outcome", "test_non_hike_question_turns", "test_second_question"),
                 "H12": ("test_qa1_new_item_chat",), "H13": ("test_phone_wording",),
                 "H14": ("test_hike_change_words", "test_chat_dead_end_reasons"),
                 "H17": ("test_qa1_waiting_reminders",)}
        appended = {"H03": 6, "H04": 2, "H05": 2, "H13": 4, "H17": 7}  # AV1052-17 and AV1352-12 tails follow these
        for id_, mods in added.items():
            row = acceptance.MAP[id_]
            row = row[:len(row) - appended.get(id_, 0)]
            self.assertEqual(row[-len(mods):], mods, id_)
            for m in mods:
                self.assertTrue(os.path.exists(os.path.join(acceptance._TESTS_DIR, m + ".py")), m)
                self.assertEqual([k for k, v in acceptance.MAP.items() if m in v], [id_], m)

    def test_av1622_modules_selected_once(self):
        class Recorder(unittest.TestLoader):
            def __init__(self):
                super().__init__()
                self.names = []

            def loadTestsFromName(self, name, module=None):
                self.names.append(name)
                return unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])

        want = {"H01": ("test_browser_freshness", "test_publish"),
                "H03": ("test_clear_availability", "test_product_new"),
                "H17": ("test_listing_command",)}
        for id_, mods in want.items():
            rec = Recorder()
            rows, code, probs = acceptance.run({id_: acceptance.MAP[id_]}, rec, expected_ids=(id_,))
            self.assertEqual((code, probs), (0, []))
            self.assertEqual(len(rec.names), len(set(rec.names)))
            for m in mods:
                self.assertEqual(rec.names.count("hass.tests." + m), 1)
        rows, code, _ = acceptance.run({"H25": acceptance.MAP["H25"]}, Recorder(), expected_ids=("H25",))
        self.assertEqual((code, rows[0]["result"], rows[0]["note"]),
                         (0, "not covered", "release step"))

    def test_av1937_modules_selected_once_in_order(self):
        class Recorder(unittest.TestLoader):
            def __init__(self):
                super().__init__()
                self.names = []

            def loadTestsFromName(self, name, module=None):
                self.names.append(name)
                return unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])

        want = {"H02": ("test_maker_product_batch",),
                "H03": ("test_maker_hide_products", "test_maker_optional_url"),
                "H04": ("test_hike_repeat", "test_hike_ics"),
                "H12": ("test_photo_home_image",), "H22": ("test_interpreter_prompt",),
                "H17": ("test_status_notice", "test_social_draft_maker", "test_post_maker_command")}
        for id_, mods in want.items():
            rec = Recorder()
            rows, code, probs = acceptance.run({id_: acceptance.MAP[id_]}, rec, expected_ids=(id_,))
            self.assertEqual((code, probs), (0, []))
            self.assertEqual(rec.names, ["hass.tests." + m for m in acceptance.MAP[id_]])
            self.assertEqual(len(rec.names), len(set(rec.names)))
            self.assertEqual([n for n in rec.names if n[len("hass.tests."):] in mods],
                             ["hass.tests." + m for m in mods])
        rows, code, _ = acceptance.run({"H25": acceptance.MAP["H25"]}, Recorder(), expected_ids=("H25",))
        self.assertEqual((code, rows[0]["result"], rows[0]["tests"], rows[0]["note"]),
                         (0, "not covered", 0, "release step"))

    def test_av2152_modules_selected_once_in_order(self):
        class Recorder(unittest.TestLoader):
            def __init__(self):
                super().__init__()
                self.names = []

            def loadTestsFromName(self, name, module=None):
                self.names.append(name)
                return unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])

        want = {"H04": ("test_hike_cancel_note", "test_preview_cancel_note"),
                "H05": ("test_unknown_approval_code", "test_again", "test_interpreter_prompt_shelf_maker",
                        "test_interpreter_prompt_descriptions", "test_claims_health_awards"),
                "H06": ("test_history_search", "test_store_field_undo"),
                "H12": ("test_photo_batch", "test_media_batch"),
                "H13": ("test_notice_start", "test_club_intro")}
        for id_, mods in want.items():
            rec = Recorder()
            rows, code, probs = acceptance.run({id_: acceptance.MAP[id_]}, rec, expected_ids=(id_,))
            self.assertEqual((code, probs), (0, []))
            self.assertEqual(rec.names, ["hass.tests." + m for m in acceptance.MAP[id_]])
            self.assertEqual(len(rec.names), len(set(rec.names)))
            self.assertEqual([n for n in rec.names if n[len("hass.tests."):] in mods],
                             ["hass.tests." + m for m in mods])

    def test_av0007_modules_selected_once_in_order(self):
        class Recorder(unittest.TestLoader):
            def __init__(self):
                super().__init__()
                self.names = []

            def loadTestsFromName(self, name, module=None):
                self.names.append(name)
                return unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])

        want = {"H03": ("test_product_default_brand",),
                "H05": ("test_interpreter_no_undo", "test_field_words", "test_question_missing_fields",
                        "test_named_records", "test_interpreter_aliases", "test_social_message")}
        for id_, mods in want.items():
            rec = Recorder()
            rows, code, probs = acceptance.run({id_: acceptance.MAP[id_]}, rec, expected_ids=(id_,))
            self.assertEqual((code, probs), (0, []))
            self.assertEqual(rec.names, ["hass.tests." + m for m in acceptance.MAP[id_]])
            self.assertEqual(len(rec.names), len(set(rec.names)))
            self.assertEqual([n for n in rec.names if n[len("hass.tests."):] in mods],
                             ["hass.tests." + m for m in mods])

    def test_av0222_modules_selected_once_in_order(self):
        class Recorder(unittest.TestLoader):
            def __init__(self):
                super().__init__()
                self.names = []

            def loadTestsFromName(self, name, module=None):
                self.names.append(name)
                return unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])

        want = {"H03": ("test_maker_optional_story",),
                "H05": ("test_interpret_check_enum", "test_shelf_labels",
                        "test_interpret_check_prices", "test_interpreter_prompt_design",
                        "test_proposal_notice_words", "test_shelf_check_flow"),
                "H06": ("test_history_times", "test_undo_cancel_phrases"),
                "H10": ("test_photos_to_take", "test_commands_doc"),
                "H15": ("test_memory_alias", "test_memory_listing", "test_memory_unchanged",
                        "test_memory_chat", "test_limits_doc")}
        for id_, mods in want.items():
            rec = Recorder()
            rows, code, probs = acceptance.run({id_: acceptance.MAP[id_]}, rec, expected_ids=(id_,))
            self.assertEqual((code, probs), (0, []))
            self.assertEqual(rec.names, ["hass.tests." + m for m in acceptance.MAP[id_]])
            self.assertEqual([n for n in rec.names if n[len("hass.tests."):] in mods],
                             ["hass.tests." + m for m in mods])
        # omission of a new member is detected by the pinned tuple
        self.assertEqual(acceptance.MAP["H10"][:5], ("test_label_reader",
                         "test_label_reader_amounts", "test_label_question_brand",
                         "test_photos_to_take", "test_commands_doc"))
        # a missing module file is a bad map (exit 2) before anything runs
        rec = Recorder()
        rows, code, probs = acceptance.run({"H10": ("test_photos_to_take", "test_no_such_av0222")},
                                           rec, expected_ids=("H10",))
        self.assertEqual((rows, code, rec.names), ([], 2, []))
        self.assertIn("missing module: test_no_such_av0222", probs)
        # H25 stays a release step even beside feature rows
        rec = Recorder()
        rows, code, _ = acceptance.run({i: acceptance.MAP[i] for i in ("H10", "H25")}, rec,
                                       expected_ids=("H10", "H25"))
        self.assertEqual(code, 0)
        self.assertEqual((rows[1]["id"], rows[1]["result"], rows[1]["note"]),
                         ("H25", "not covered", "release step"))
        self.assertNotIn("H25", [r["id"] for r in rows if r["result"] == "pass"])

    # AV1052-17 contract: the standing run covers the AV1052-03..12 modules in the five rows
    # below. Bug caught: a dropped, duplicated, moved or mis-rowed module (e.g. test_cancel_all
    # left out of H05) silently shrinks the acceptance evidence. Literals are written out
    # independently of MAP.
    AV1052 = {
        "H03": ("test_catalog_ops", "test_clear_availability", "test_product_new",
                "test_maker_hide_products", "test_maker_optional_url", "test_product_default_brand",
                "test_maker_optional_story", "test_stock_product_choice", "test_plain_shelf_check",
                "test_shelf_check_except", "test_set_availability_all", "test_interpreter_prompt_design",
                "test_interpret_check_count", "test_post_by_name", "test_listing_by_name",
                "test_post_command"),
        "H05": ("test_conversation", "test_near_approval", "test_unknown_approval_code", "test_again",
                "test_interpreter_prompt_shelf_maker", "test_interpreter_prompt_descriptions",
                "test_claims_health_awards", "test_interpreter_no_undo", "test_field_words",
                "test_question_missing_fields", "test_named_records", "test_interpreter_aliases",
                "test_social_message", "test_interpret_check_enum", "test_shelf_labels",
                "test_interpret_check_prices", "test_interpreter_prompt_design",
                "test_proposal_notice_words", "test_shelf_check_flow", "test_repeat_outcome",
                "test_non_hike_question_turns", "test_second_question", "test_cancel_all"),
        "H13": ("test_store_ops", "test_store_intro", "test_store_headline", "test_store_story",
                "test_store_home_image", "test_store_clear_home_image", "test_notice_start",
                "test_club_intro", "test_phone_wording", "test_publish_csp", "test_publish",
                "test_store_notice", "test_listing_store"),
        "H15": ("test_memory", "test_memory_source", "test_memory_alias", "test_memory_listing",
                "test_memory_unchanged", "test_memory_chat", "test_limits_doc",
                "test_design_notes", "test_interpreter_notes"),
        "H17": ("test_status_pause", "test_help", "test_status_photos", "test_listing_command",
                "test_status_notice", "test_social_draft_maker", "test_post_maker_command",
                "test_qa1_waiting_reminders", "test_shelf_command", "test_command_typo",
                "test_status_reader_failed", "test_commands_doc"),
    }
    # AV1352-12 contract: complete final tuples of the five rows AV1352-03..09 registered into.
    # Each is the inherited tuple (AV1052 / AV2007 / earlier pins above) plus the appended
    # modules in dependency order. Written out independently of MAP; H15 gains nothing new
    # (test_memory_chat, test_memory_alias, test_limits_doc, test_interpreter_notes already there).
    AV1352 = {
        "H04": ("test_hike_ops", "test_route_add", "test_route_edit", "test_route_hide",
                "test_hike_samples", "test_hike_repeat", "test_hike_ics", "test_hike_cancel_note",
                "test_preview_cancel_note", "test_nl_prep_calendar", "test_weekday_date_mismatch",
                "test_nl_prep_ordinal_words", "test_interpreter_local", "test_interpreter_today"),
        "H05": AV1052["H05"] + ("test_phone_answers",),
        "H10": ("test_label_reader", "test_label_reader_amounts", "test_label_question_brand",
                "test_photos_to_take", "test_commands_doc", "test_social_draft",
                "test_social_draft_inputs", "test_social_draft_text", "test_social_draft_tags",
                "test_social_draft_fullwidth", "test_social_draft_shapes", "test_post_command"),
        "H15": AV1052["H15"],
        "H17": AV1052["H17"] + ("test_readonly_questions", "test_margin_chat", "test_purchase_cost"),
    }
    UNAFFECTED = {
        "H01": ("test_content", "test_content_read_errors", "test_browser_freshness", "test_publish"),
        "H02": ("test_editor", "test_maker_product_batch"),
        "H06": ("test_preview", "test_undo", "test_history_search", "test_store_field_undo",
                "test_history_times", "test_undo_cancel_phrases"),
        "H07": "needs Michael's devices",
        "H08": ("test_bridge", "test_owner_sender_match", "test_host", "test_relay"),
        "H09": ("test_demo_transcript", "test_demo_negative", "test_demo_browser",
                "test_demo_transcript_photo"),
        "H11": ("test_media_audio",),
        "H12": ("test_attachment_reply", "test_photo_draft", "test_photo_on_product",
                "test_photo_new_product", "test_photo_home_image", "test_photo_batch",
                "test_media_batch", "test_npp_acceptance", "test_qa1_new_item_chat"),
        "H14": ("test_hike_capacity_ceiling", "test_hike_capacity_rsvp_off", "test_hike_change_words",
                "test_chat_dead_end_reasons"),
        "H16": ("test_outbox_delayed", "test_late_yes", "test_writer_lock_entry"),
        "H18": "needs Michael's devices",
        "H19": ("test_health", "test_health_host"),
        "H20": ("test_statebackup_drill", "test_statebackup", "test_statebackup_bundle"),
        "H21": ("test_retention",), "H22": ("test_interpreter_cap", "test_interpreter_prompt"),
        "H23": ("test_auto_policy",),
        "H24": ("test_design_check", "test_design_check_modes", "test_design_check_merge_base"),
        "H25": "release step",
    }

    FINAL = {**UNAFFECTED, **AV1052, **AV1352}

    @staticmethod
    def _recording(names, imports):
        class Recorder(unittest.TestLoader):
            def loadTestsFromName(self, name, module=None):
                names.append(name)
                return unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])
        return Recorder(), mock.patch.object(acceptance.importlib, "import_module",
                                             side_effect=imports.append)

    def test_av1052_complete_tuples_and_preservation(self):
        final = dict(self.UNAFFECTED, **dict(self.AV1052, **self.AV1352))
        self.assertEqual(final, acceptance.MAP)
        for id_, row in self.AV1052.items():
            # inherited tuple is preserved in order as the prefix of the final row
            self.assertEqual(acceptance.MAP[id_][:len(row)], row, id_)
            self.assertEqual(len(row), len(set(row)), id_)
            self.assertFalse([m for m in row if not m.startswith("test_") or "." in m], id_)
        # test_interpreter_prompt_design is deliberately in H03 (AV1052-04) and H05 (inherited)
        self.assertEqual([k for k, v in acceptance.MAP.items() if "test_cancel_all" in v], ["H05"])

    def test_av1052_selected_modules_once_in_order(self):
        names, imports = [], []
        rec, patched = self._recording(names, imports)
        with patched:
            for id_ in self.AV1052:
                del names[:], imports[:]
                rows, code, probs = acceptance.run({id_: acceptance.MAP[id_]}, rec,
                                                   expected_ids=(id_,))
                self.assertEqual((code, probs, rows[0]["result"]), (0, [], "pass"), id_)
                want = ["hass.tests." + m for m in self.FINAL[id_]]
                self.assertEqual((names, imports), (want, want), id_)
            # mixed selection: only the selected rows load, H25 stays not covered, never a pass
            del names[:], imports[:]
            ids = ("H13", "H17", "H25")
            rows, code, _ = acceptance.run({i: acceptance.MAP[i] for i in ids}, rec, expected_ids=ids)
        want = ["hass.tests." + m for i in ids[:2] for m in self.FINAL[i]]
        self.assertEqual((code, names, imports), (0, want, want))
        self.assertEqual([(r["id"], r["result"]) for r in rows],
                         [("H13", "pass"), ("H17", "pass"), ("H25", "not covered")])

    def test_av1052_missing_module_fails_before_loading(self):
        names, imports = [], []
        rec, patched = self._recording(names, imports)
        # a row naming a module that does not exist: exit 2 naming it, nothing imported or loaded
        with patched:
            rows, code, probs = acceptance.run(
                {"H15": acceptance.MAP["H15"] + ("test_no_such_av1052",), "H25": "release step"},
                rec, expected_ids=("H15", "H25"))
        self.assertEqual((rows, code, names, imports), ([], 2, [], []))
        self.assertEqual(probs, ["missing module: test_no_such_av1052"])
        # real filesystem check, unmocked: every registered module exists
        self.assertEqual(acceptance._validate(acceptance.MAP, acceptance._TESTS_DIR,
                                              acceptance.ALL_IDS), [])

    def test_av1052_h25_never_becomes_fixture_pass(self):
        names, imports = [], []
        rec, patched = self._recording(names, imports)
        out = io.StringIO()
        with patched, contextlib.redirect_stdout(out):
            code = acceptance.main(["--only", "H25"])
        self.assertEqual((code, names, imports), (0, [], []))
        self.assertEqual(out.getvalue().splitlines(), [
            '{"id": "H25", "result": "not covered", "tests": 0, "failures": 0, "note": "release step"}',
            '{"summary": {"ids": 1, "pass": 0, "fail": 0, "not covered": 1}}'])
        self.assertIsInstance(acceptance.MAP["H25"], str)

    def test_av1352_complete_tuples_and_preservation(self):
        # Bug caught: a dropped, reordered or duplicated AV1352 module, or a row that loses
        # an inherited member, silently shrinks the standing acceptance evidence.
        for id_, row in self.AV1352.items():
            self.assertEqual(acceptance.MAP[id_], row, id_)
            self.assertEqual(len(row), len(set(row)), id_)
        self.assertEqual(self.FINAL, acceptance.MAP)
        self.assertEqual(sorted(self.FINAL), list(acceptance.ALL_IDS))
        # every table-designated module sits in its designated row
        for id_, mods in {"H04": ("test_interpreter_local", "test_interpreter_today"),
                          "H05": ("test_phone_answers",),
                          "H10": ("test_social_draft", "test_social_draft_inputs",
                                  "test_social_draft_text", "test_social_draft_tags",
                                  "test_social_draft_fullwidth", "test_social_draft_shapes",
                                  "test_post_command"),
                          "H15": ("test_memory_chat", "test_memory_alias", "test_limits_doc",
                                  "test_interpreter_notes"),
                          "H17": ("test_readonly_questions", "test_margin_chat",
                                  "test_purchase_cost", "test_help", "test_commands_doc")}.items():
            self.assertEqual([m for m in mods if m not in acceptance.MAP[id_]], [], id_)
        # shared modules are not copied into extra rows; none of the new ones is in H25
        self.assertEqual([k for k, v in acceptance.MAP.items() if "test_purchase_cost" in v], ["H17"])
        self.assertEqual([k for k, v in acceptance.MAP.items() if "test_phone_answers" in v], ["H05"])
        self.assertEqual([k for k, v in acceptance.MAP.items() if "test_post_command" in v], ["H03", "H10"])
        self.assertEqual(acceptance.MAP["H15"], self.AV1052["H15"])
        # a tuple with a required member removed, or doubled, is not the pinned one
        self.assertNotEqual(acceptance.MAP["H17"][:-1], self.AV1352["H17"])
        self.assertNotEqual(acceptance.MAP["H17"] + ("test_margin_chat",), self.AV1352["H17"])

    def test_av1352_selected_modules_once_in_order(self):
        names, imports = [], []
        rec, patched = self._recording(names, imports)
        with patched:
            for id_ in self.AV1352:
                del names[:], imports[:]
                rows, code, probs = acceptance.run({id_: acceptance.MAP[id_]}, rec,
                                                   expected_ids=(id_,))
                self.assertEqual((code, probs, rows[0]["result"]), (0, [], "pass"), id_)
                want = ["hass.tests." + m for m in self.AV1352[id_]]
                self.assertEqual((names, imports), (want, want), id_)
                self.assertEqual(len(names), len(set(names)), id_)
            # mixed selection: only the selected rows load, in selection order
            del names[:], imports[:]
            ids = ("H05", "H10", "H25")
            rows, code, _ = acceptance.run({i: acceptance.MAP[i] for i in ids}, rec, expected_ids=ids)
        want = ["hass.tests." + m for i in ids[:2] for m in self.AV1352[i]]
        self.assertEqual((code, names, imports), (0, want, want))
        self.assertEqual([(r["id"], r["result"]) for r in rows],
                         [("H05", "pass"), ("H10", "pass"), ("H25", "not covered")])

    def test_av1352_missing_module_stops_before_loading(self):
        names, imports = [], []
        rec, patched = self._recording(names, imports)
        with patched:
            rows, code, probs = acceptance.run(
                {"H05": acceptance.MAP["H05"], "H17": acceptance.MAP["H17"] + ("test_no_such_av1352",),
                 "H25": "release step"}, rec, expected_ids=("H05", "H17", "H25"))
        self.assertEqual((rows, code, names, imports), ([], 2, [], []))
        self.assertEqual(probs, ["missing module: test_no_such_av1352"])
        # unmocked, real disk: every registered module (including the new ones) exists
        self.assertEqual(acceptance._validate(acceptance.MAP, acceptance._TESTS_DIR,
                                              acceptance.ALL_IDS), [])

    def test_av1352_h25_remains_release_step(self):
        names, imports = [], []
        rec, patched = self._recording(names, imports)
        out = io.StringIO()
        with patched, contextlib.redirect_stdout(out):
            code = acceptance.main(["--only", "H25"])
        self.assertEqual((code, names, imports), (0, [], []))
        self.assertEqual(out.getvalue().splitlines(), [
            '{"id": "H25", "result": "not covered", "tests": 0, "failures": 0, "note": "release step"}',
            '{"summary": {"ids": 1, "pass": 0, "fail": 0, "not covered": 1}}'])
        # mixed selection keeps H25 not covered; H07/H18 reasons unchanged
        ids = ("H05", "H07", "H18", "H25")
        with patched:
            rows, code, _ = acceptance.run({i: acceptance.MAP[i] for i in ids}, rec, expected_ids=ids)
        self.assertEqual([(r["id"], r["result"], r["note"]) for r in rows], [
            ("H05", "pass", ""), ("H07", "not covered", "needs Michael's devices"),
            ("H18", "not covered", "needs Michael's devices"), ("H25", "not covered", "release step")])
        self.assertEqual(acceptance.MAP["H25"], "release step")

    def test_h25_stays_release_step(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = acceptance.main(["--only", "H25"])
        lines = out.getvalue().splitlines()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(lines[0]), {"id": "H25", "result": "not covered", "tests": 0,
                                                "failures": 0, "note": "release step"})
        self.assertEqual(json.loads(lines[1]), {"summary": {"ids": 1, "pass": 0, "fail": 0, "not covered": 1}})


UNEXP = textwrap.dedent("""
    import unittest
    class T(unittest.TestCase):
        @unittest.expectedFailure
        def test_a(self): self.assertTrue(True)
""")
UNEXP2 = textwrap.dedent("""
    import unittest
    print('LEAK-MARKER')
    class T(unittest.TestCase):
        @unittest.expectedFailure
        def test_a(self): print('LEAK-MARKER')
        @unittest.expectedFailure
        def test_b(self): pass
        def test_c(self): self.assertTrue(True)
""")
EXPECTED = textwrap.dedent("""
    import unittest
    class T(unittest.TestCase):
        @unittest.expectedFailure
        def test_a(self): self.assertTrue(False)
        @unittest.skip("x")
        def test_b(self): pass
        def test_c(self): self.assertTrue(True)
""")
ERRS = textwrap.dedent("""
    import unittest
    class T(unittest.TestCase):
        def test_a(self): raise RuntimeError('x')
""")


class UnexpectedSuccessTest(unittest.TestCase):
    _run = RunnerTest._run

    def test_unexpected_success_fails_acceptance(self):
        with temp_pkg({"test_unexp.py": UNEXP}) as (n, d):
            rows, code, probs = self._run(n, d, {"H01": ("test_unexp",)})
            self.assertEqual((code, probs), (1, []))
            self.assertEqual(rows, [{"id": "H01", "result": "fail", "tests": 1,
                                     "failures": 1, "note": ""}])
            res = unittest.TextTestRunner(stream=io.StringIO()).run(
                unittest.TestLoader().loadTestsFromName(n + ".test_unexp"))
            self.assertFalse(res.wasSuccessful())

    def test_multiple_unexpected_successes_counted_each(self):
        with temp_pkg({"test_unexp2.py": UNEXP2, "test_ok.py": OK}) as (n, d):
            for order in (("test_unexp2", "test_ok"), ("test_ok", "test_unexp2")):
                rows, code, _ = self._run(n, d, {"H01": order})
                self.assertEqual(code, 1)
                self.assertEqual(rows[0], {"id": "H01", "result": "fail", "tests": 5,
                                           "failures": 2, "note": ""})

    def test_unexpected_success_adds_to_assertion_error_and_import_counts(self):
        files = {"test_unexp.py": UNEXP, "test_bad.py": BAD, "test_errs.py": ERRS,
                 "test_raises.py": RAISES}
        with temp_pkg(files) as (n, d):
            rows, _, _ = self._run(n, d, {
                "H01": ("test_unexp", "test_bad"), "H02": ("test_unexp", "test_errs"),
                "H03": ("test_unexp", "test_raises"),
                "H04": ("test_unexp", "test_bad", "test_raises")})
            self.assertEqual([(r["tests"], r["failures"], r["note"]) for r in rows],
                             [(3, 2, ""), (2, 2, ""),
                              (1, 2, "import error: test_raises"),
                              (3, 3, "import error: test_raises")])

    def test_expected_failures_and_skips_keep_existing_outcomes(self):
        with temp_pkg({"test_expected.py": EXPECTED}) as (n, d):
            rows, code, _ = self._run(n, d, {"H01": ("test_expected",)})
            self.assertEqual(code, 0)
            self.assertEqual(rows, [{"id": "H01", "result": "pass", "tests": 3,
                                     "failures": 0, "note": ""}])

    def test_unexpected_success_does_not_stop_later_rows(self):
        with temp_pkg({"test_unexp.py": UNEXP, "test_ok.py": OK}) as (n, d):
            rows, code, _ = self._run(n, d, {"H01": ("test_unexp",), "H02": ("test_ok",),
                                             "H25": "release step"})
            self.assertEqual(code, 1)
            self.assertEqual([(r["id"], r["result"]) for r in rows],
                             [("H01", "fail"), ("H02", "pass"), ("H25", "not covered")])

    def test_cli_unexpected_success_summary_and_output_isolation(self):
        with temp_pkg({"test_ok.py": UNEXP2}) as (n, d):
            code, lines = _main(["--only", "H01"], n, d)
            self.assertEqual(code, 1)
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0]), {"id": "H01", "result": "fail",
                             "tests": 3, "failures": 2, "note": ""})
            self.assertEqual(json.loads(lines[1])["summary"],
                             {"ids": 1, "pass": 0, "fail": 1, "not covered": 0})
            self.assertNotIn("LEAK-MARKER", "".join(lines))


class SelectedMissingTest(unittest.TestCase):
    def _main_map(self, argv, map_, n, d):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = acceptance.main(argv, map_=map_, tests_pkg=n, tests_dir=d)
        return code, out.getvalue(), err.getvalue()

    def test_selected_missing_id_returns_bad_map_not_keyerror(self):
        with temp_pkg({"test_counter.py": COUNTER}) as (n, d):
            m = {"H02": ("test_counter",)}
            self.assertEqual(self._main_map(["--only", "H01"], m, n, d),
                             (2, "map: H01\n", ""))
            self.assertEqual(m, {"H02": ("test_counter",)})
            self.assertNotIn(n + ".test_counter", sys.modules)

    def test_missing_selected_id_blocks_valid_counter_prefix(self):
        with temp_pkg({"test_counter.py": COUNTER}) as (n, d):
            m = {"H02": ("test_counter",)}
            self.assertEqual(self._main_map(["--only", "H02,H01"], m, n, d),
                             (2, "map: H01\n", ""))
            self.assertNotIn(n + ".test_counter", sys.modules)
            self.assertEqual(importlib.import_module(n + ".test_counter").RAN, [])

    def test_multiple_missing_selected_ids_keep_requested_order(self):
        with temp_pkg({"test_counter.py": COUNTER}) as (n, d):
            m = {"H02": ("test_counter",)}
            code, out, err = self._main_map(["--only", "H03,H01,H02"], m, n, d)
            self.assertEqual((code, out, err), (2, "map: H03\nmap: H01\n", ""))
            self.assertNotIn(n + ".test_counter", sys.modules)

    def test_partial_map_with_complete_selection_remains_valid(self):
        with temp_pkg({"test_ok.py": OK}) as (n, d):
            code, out, err = self._main_map(["--only", "H01"], {"H01": ("test_ok",)}, n, d)
            self.assertEqual((code, err), (0, ""))
            lines = out.splitlines()
            self.assertEqual(json.loads(lines[0]), {"id": "H01", "result": "pass",
                             "tests": 2, "failures": 0, "note": ""})
            self.assertEqual(json.loads(lines[1])["summary"],
                             {"ids": 1, "pass": 1, "fail": 0, "not covered": 0})

    def test_unknown_id_precedes_missing_map_validation(self):
        with temp_pkg({"test_counter.py": COUNTER}) as (n, d):
            m = {"H02": ("test_counter",)}
            self.assertEqual(self._main_map(["--only", "H01,H99"], m, n, d),
                             (2, "map: H99\n", ""))
            self.assertNotIn(n + ".test_counter", sys.modules)

    def test_full_map_and_runtime_failure_semantics_unchanged(self):
        with temp_pkg({"test_bad.py": BAD, "test_ok.py": OK}) as (n, d):
            m = {i: ("test_ok",) for i in acceptance.ALL_IDS if i != "H05"}
            code, out, _ = self._main_map([], m, n, d)
            self.assertEqual((code, out), (2, "map: H05\n"))
            m = {"H01": ("test_bad",)}
            code, out, _ = self._main_map(["--only", "H01"], m, n, d)
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(out.splitlines()[0])["result"], "fail")
            self.assertEqual(m, {"H01": ("test_bad",)})


if __name__ == "__main__":
    unittest.main()
