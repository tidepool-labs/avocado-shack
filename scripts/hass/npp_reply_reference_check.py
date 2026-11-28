#!/usr/bin/env python3
"""Check literal NPP reply references; refuse lookup forms this scan cannot prove."""

import argparse
import ast
from glob import glob
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCES = str(ROOT / "hass/npp/*.py")
sys.path.insert(0, str(ROOT))
from hass import npp

EDIT_SCHEMA = "hass-listing-edit/edit.schema.json"
HELPERS = {"compose", "question", "ready_line", "guard"}
KEYWORDS = {"ask": "questions", "reply": "edits"}
AMBIGUOUS = object()
MISSING = object()


def literal(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def key_text(key):
    # A source literal can contain line breaks or terminal controls.
    return "".join(c if c.isprintable() else ascii(c)[1:-1] for c in key)


class LocalNames(ast.NodeVisitor):
    """Find local binders before visiting a function body (including late stores)."""

    def __init__(self, body):
        self.names = set()
        for statement in body:
            self.visit(statement)

    def visit_Name(self, node):
        if not isinstance(node.ctx, ast.Load):
            self.names.add(node.id)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        self.names.add(node.name)

    visit_AsyncFunctionDef = visit_ClassDef = visit_FunctionDef

    def visit_ExceptHandler(self, node):
        self.names.add(node.name)
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs | ast.MatchStar):
        self.names.add(node.name)
        self.generic_visit(node)

    visit_MatchStar = visit_MatchAs

    def visit_MatchMapping(self, node):
        self.names.add(node.rest)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import | ast.ImportFrom):
        self.names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)

    visit_ImportFrom = visit_Import

    def visit_comprehension(self, node):
        # Iteration targets have their own scope, unlike walrus stores.
        self.visit(node.iter)
        for test in node.ifs:
            self.visit(test)


class ReferenceScan(ast.NodeVisitor):
    def __init__(self, filename, templates):
        self.filename = filename
        self.templates = templates
        self.bindings = {}
        self.exception_edges = []
        self.sections = self.references = self.dynamic = 0
        self.findings = []

    def path(self, node):
        if isinstance(node, ast.Name):
            return self.bindings.get(node.id, () if node.id == "replies" else None)
        if (isinstance(node, ast.Attribute) and node.attr == "replies"
                and isinstance(node.value, ast.Name) and node.value.id == "self"):
            return ()
        if isinstance(node, ast.Subscript):
            base = self.path(node.value)
            if isinstance(base, tuple):
                return (*base, literal(node.slice))
            return base
        return None

    def resolve(self, path):
        value = self.templates
        for part in path:
            if part is None or not isinstance(value, dict) or part not in value:
                return MISSING
            value = value[part]
        return value

    def is_table(self, node):
        path = self.path(node)
        return ((path is AMBIGUOUS and not isinstance(node, ast.Subscript))
                or (isinstance(path, tuple) and isinstance(self.resolve(path), dict)))

    def fail(self, node, reason):
        self.findings.append((node.lineno, node.col_offset, f"FAIL {reason}"))

    def unresolved(self, node):
        self.dynamic += 1
        self.fail(node, f"reply-key-unresolved {self.filename} {node.lineno}")

    def check_key(self, node, path, *, keyword=False):
        section, *parts = map(key_text, path)
        parent = self.resolve(path[:-1])
        # A subscript's ancestor is checked at its own site (including an alias's
        # binding site). Keywords have no separate section lookup.
        if len(path) == 1:
            if path[0] not in self.templates:
                self.fail(node, f"reply-section-missing {self.filename} {section}")
        elif (keyword or parent is not MISSING) and (
                not isinstance(parent, dict) or path[-1] not in parent):
            self.fail(node, f"reply-ref-missing {self.filename} {section} {'.'.join(parts)}")

    def visit_Subscript(self, node):
        self.visit(node.value)
        self.use(node.slice)
        parent = self.path(node.value)
        if parent is None:
            return
        key = literal(node.slice)
        if parent is AMBIGUOUS or key is None or not isinstance(node.ctx, ast.Load):
            self.unresolved(node)
        elif None not in parent:
            if parent:
                self.references += 1
            else:
                self.sections += 1
            self.check_key(node, (*parent, key))

    def use(self, node):
        """Visit a child in a context that does not support passing a table."""
        self.visit(node)
        if self.is_table(node):
            self.unresolved(node)

    def generic_visit(self, node):
        for child in ast.iter_child_nodes(node):
            self.use(child)

    def visit_Compare(self, node):
        self.use(node.left)
        for op, right in zip(node.ops, node.comparators):
            if isinstance(op, (ast.In, ast.NotIn)):
                self.visit(right)  # Membership alone doesn't fetch a reply.
            else:
                self.use(right)

    def visit_Call(self, node):
        self.use(node.func)
        positional_helper = isinstance(node.func, ast.Name) and node.func.id in HELPERS
        for i, arg in enumerate(node.args):
            if positional_helper and i == 0 and self.path(arg) == ():
                self.visit(arg)
            else:
                self.use(arg)
        for kw in node.keywords:
            key = literal(kw.value)
            if kw.arg in KEYWORDS and key is not None:
                self.references += 1
                self.check_key(kw, (KEYWORDS[kw.arg], key), keyword=True)
            if positional_helper and kw.arg == "replies" and self.path(kw.value) == ():
                self.visit(kw.value)
            else:
                self.use(kw.value)

    def assignments(self, targets, value):
        if (isinstance(value, (ast.Tuple, ast.List)) and all(
                isinstance(t, (ast.Tuple, ast.List)) and len(t.elts) == len(value.elts)
                and not any(isinstance(e, ast.Starred) for e in t.elts) for t in targets)):
            for i, elt in enumerate(value.elts):
                yield from self.assignments([t.elts[i] for t in targets], elt)
            return
        self.visit(value)
        path = self.path(value)
        is_table = self.is_table(value)
        for target in targets:
            yield target, path, is_table

    def bind(self, targets, value):
        # Resolve all RHS expressions before overwriting any aliases on the LHS.
        for target, path, is_table in list(self.assignments(targets, value)):
            if isinstance(target, ast.Name):
                self.set_binding(target.id, path)
            else:
                if is_table:
                    self.unresolved(target)
                self.clear_target(target)

    def set_binding(self, name, path):
        self.bindings[name] = path
        # Each write in a protected suite may be the last one before an
        # exception, including writes inside branches or unpacking targets.
        for edge in self.exception_edges:
            if edge.get(name, () if name == "replies" else None) != path:
                edge[name] = AMBIGUOUS

    def clear_target(self, target):
        if isinstance(target, ast.Name):
            self.set_binding(target.id, None)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self.clear_target(elt)
        elif isinstance(target, ast.Starred):
            self.clear_target(target.value)
        else:
            self.visit(target)

    def visit_Assign(self, node):
        self.bind(node.targets, node.value)

    def visit_AnnAssign(self, node):
        self.use(node.annotation)
        if node.value is not None:
            self.bind([node.target], node.value)

    def visit_NamedExpr(self, node):
        self.use(node.value)  # Aliasing through a walrus is outside this scan.
        self.clear_target(node.target)

    def visit_AugAssign(self, node):
        self.use(node.target)
        self.use(node.value)
        if isinstance(node.target, ast.Name):
            self.clear_target(node.target)

    def visit_Delete(self, node):
        for target in node.targets:
            self.clear_target(target)

    def suite(self, statements):
        for statement in statements:
            self.visit(statement)

    @staticmethod
    def join_bindings(*outcomes):
        joined = {}
        for name in set().union(*outcomes):
            values = {env.get(name, () if name == "replies" else None) for env in outcomes}
            joined[name] = values.pop() if len(values) == 1 else AMBIGUOUS
        return joined

    def alternatives(self, *suites):
        initial = self.bindings
        outcomes = []
        for suite in suites:
            self.bindings = initial.copy()
            suite()
            outcomes.append(self.bindings)
        self.bindings = self.join_bindings(*outcomes)

    def visit_If(self, node):
        self.use(node.test)
        self.alternatives(lambda: self.suite(node.body), lambda: self.suite(node.orelse))

    def visit_While(self, node):
        self.use(node.test)
        self.alternatives(lambda: self.suite(node.body), lambda: None)
        self.suite(node.orelse)

    def visit_For(self, node: ast.For | ast.AsyncFor):
        self.use(node.iter)

        def body():
            self.clear_target(node.target)
            self.suite(node.body)

        self.alternatives(body, lambda: None)
        self.suite(node.orelse)

    visit_AsyncFor = visit_For

    def visit_Try(self, node: ast.Try | ast.TryStar):
        # The RHS of an assignment can raise before it overwrites the old
        # alias. Join the entry state and all writes, not just suite exits.
        edge = self.bindings.copy()
        self.exception_edges.append(edge)
        self.suite(node.body)
        normal = self.bindings
        handler_entry = edge.copy()
        handled = []
        for handler in node.handlers:
            # Unlike except, multiple except* handlers can run in sequence.
            self.bindings = (edge if isinstance(node, ast.TryStar) else handler_entry).copy()
            self.visit(handler)
            handled.append(self.bindings)
        self.bindings = normal
        self.suite(node.orelse)
        self.exception_edges.pop()
        self.bindings = self.join_bindings(self.bindings, *handled)
        if node.finalbody:
            # Finally can also run after an unhandled exception in any suite.
            self.bindings = self.join_bindings(self.bindings, edge)
            self.suite(node.finalbody)

    visit_TryStar = visit_Try

    def visit_ExceptHandler(self, node):
        if node.type is not None:
            self.use(node.type)
        if node.name is not None:
            self.set_binding(node.name, None)
        self.suite(node.body)
        if node.name is not None:
            self.set_binding(node.name, None)

    def scoped(self, bindings, scan):
        outer, edges = self.bindings, self.exception_edges
        self.bindings, self.exception_edges = bindings, []
        scan()
        self.bindings, self.exception_edges = outer, edges

    def function_scope(self, args, body, scan):
        outer = self.bindings
        params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        params.extend(arg for arg in (args.vararg, args.kwarg) if arg is not None)
        self.use(args)  # Defaults and annotations run in the enclosing scope.
        locals_ = dict.fromkeys(LocalNames(body).names | {p.arg for p in params})
        if any(p.arg == "replies" for p in params):
            locals_["replies"] = ()
        self.scoped(outer | locals_, scan)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        for expr in (*node.decorator_list, node.returns):
            if expr is not None:
                self.use(expr)
        self.function_scope(node.args, node.body, lambda: self.suite(node.body))
        self.set_binding(node.name, None)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node):
        self.function_scope(node.args, (node.body,), lambda: self.use(node.body))

    def visit_ClassDef(self, node):
        for expr in (*node.decorator_list, *node.bases, *node.keywords):
            self.use(expr)
        self.scoped(self.bindings.copy(), lambda: self.suite(node.body))
        self.set_binding(node.name, None)

    def comprehension(self, node, *results):
        def scan():
            for gen in node.generators:
                self.use(gen.iter)
                self.clear_target(gen.target)
                for expr in gen.ifs:
                    self.use(expr)
            for result in results:
                self.use(result)

        self.scoped(self.bindings.copy(), scan)

    def visit_ListComp(self, node: ast.ListComp | ast.SetComp | ast.GeneratorExp):
        self.comprehension(node, node.elt)

    visit_SetComp = visit_GeneratorExp = visit_ListComp

    def visit_DictComp(self, node):
        self.comprehension(node, node.key, node.value)


def load_assets():
    _, files, templates = npp.assets()
    asks = json.loads(files[EDIT_SCHEMA])["properties"]["ask_id"]["enum"]
    if not isinstance(templates, dict) or not isinstance(asks, list) or any(
            key is not None and not isinstance(key, str) for key in asks):
        raise ValueError("invalid reply reference inputs")
    return templates, [key for key in asks if key is not None]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    if args:
        parser.error("no arguments accepted")

    findings = []
    asks = []
    templates = None
    try:
        templates, asks = load_assets()
    except Exception:  # npp.assets() may raise; never emit its exception text.
        findings.append("FAIL assets-unreadable")

    paths = sorted(map(Path, glob(SOURCES)), key=lambda path: (path.name, str(path)))
    sections = references = dynamic = 0
    source_error = not paths
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, SyntaxError, RecursionError):
            source_error = True
            continue
        if templates is not None:
            scan = ReferenceScan(key_text(path.name), templates)
            scan.visit(tree)
            sections += scan.sections
            references += scan.references
            dynamic += scan.dynamic
            findings.extend(line for _, _, line in sorted(scan.findings, key=lambda row: row[:2]))
    if source_error:
        findings.append("FAIL source-unreadable")
    if templates is not None:
        questions = templates.get("questions")
        for key in asks:
            if not isinstance(questions, dict) or key not in questions:
                findings.append(f"FAIL ask-untemplated {key_text(key)}")

    print(f"refs files={len(paths)} sections={sections} references={references} dynamic={dynamic} asks={len(asks)}")
    for finding in findings:
        print(finding)
    print(f"{'FAIL' if findings else 'PASS'} npp_reply_reference_check")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
