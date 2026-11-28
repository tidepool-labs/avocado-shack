"""AVB-11: one fail-closed, per-target approval gate. No credentials or I/O here.

Executors consume the binding, never resolve a target independently. Target identities
are non-secret descriptors (writer path / publish remote+branch / API host+merchant+role).
The host supplies descriptors; a missing descriptor is never replaced with a live one.
"""
import hashlib

import re

PACKS = frozenset(('site', 'front', 'till', 'reports', 'core'))
TARGETS = frozenset(('site', 'till', 'local'))
OFF = re.compile(r'[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?')
LOCK = re.compile(r'[a-z0-9][a-z0-9-]{0,31}')  # demoLock id; absent demoLock = off
TREE = re.compile(r'[0-9a-f]{40}|[0-9a-f]{64}')


class ModeError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def policy(raw):
    """Missing live means sandbox even when legacy approvals says live. Hold stays hold."""
    live, off, gen = raw.get('live', []), raw.get('off', []), raw.get('mode_gen', 0)
    if not isinstance(live, list) or any(not isinstance(t, str) or t not in TARGETS - {'local'} for t in live) or len(live) != len(set(live)):
        raise ModeError('live')
    if not isinstance(off, list) or any(not isinstance(s, str) or not OFF.fullmatch(s) for s in off) or len(off) != len(set(off)):
        raise ModeError('off')
    if type(gen) is not int or gen < 0:
        raise ModeError('mode_gen')
    if raw.get('approvals') not in ('hold', 'private', 'live'):
        raise ModeError('approvals')
    lock = raw.get('demoLock')  # {id, tree}: written only by `host.py demo-lock on`
    if lock is not None:
        if not (isinstance(lock, dict) and set(lock) == {'id', 'tree'} and all(isinstance(lock[k], str) for k in lock)
                and LOCK.fullmatch(lock['id']) and TREE.fullmatch(lock['tree'])):
            raise ModeError('demoLock')
        lock = lock['id']
    return {'live': sorted(live), 'off': sorted(off), 'mode_gen': gen, 'hold': raw['approvals'] == 'hold', 'lock': lock}


def identity(descriptor):
    if not isinstance(descriptor, str) or not descriptor:
        raise ModeError('policy')
    return hashlib.sha256(descriptor.encode()).hexdigest()[:12]


def _members_ok(members):
    """Shape and type admission before any hash/regex use, so bad input never raises TypeError."""
    return (isinstance(members, (list, tuple)) and bool(members)
            and all(isinstance(m, dict) and set(m) == {'pack', 'skill', 'target'}
                    and all(isinstance(m[k], str) for k in m)
                    and m['pack'] in PACKS and m['target'] in TARGETS and OFF.fullmatch(m['skill'])
                    for m in members))


class Gate:
    """source() -> host dict; identities() -> {(target, env): non-secret descriptor}.

    A member is {pack, skill, target}. All members share one environment. Reports/core
    use local; local does not downgrade a live bundle and cannot enable live writes.
    """
    def __init__(self, source, identities):
        self.source, self.identities = source, identities

    def allowed(self, pack, skill):
        cfg = policy(self.source())
        return pack in PACKS and pack not in cfg['off'] and skill not in cfg['off']

    def resolve(self, members, *, recorded=None):
        cfg = policy(self.source())
        if cfg['hold']:
            raise ModeError('stopped')
        if not _members_ok(members):
            raise ModeError('policy')
        members = sorted([dict(m) for m in members], key=lambda m: (m['target'], m['pack'], m['skill']))
        if any(m['pack'] in cfg['off'] or m['skill'] in cfg['off'] for m in members):
            raise ModeError('policy')
        targets = sorted({m['target'] for m in members})
        env = 'live' if any(t != 'local' for t in targets) and all(t in cfg['live'] for t in targets if t != 'local') else 'sandbox'
        if cfg['lock']:  # demo lock: every new draft is private; only this lock's own private drafts can be undone or recovered
            env = 'sandbox'
            if recorded is not None and (recorded.get('env') != 'sandbox' or recorded.get('lock') != cfg['lock']):
                raise ModeError('env-gone')
        if recorded is not None:
            env = recorded['env']
            if targets != sorted(recorded['targets']):
                raise ModeError('env-gone')
        descriptors = self.identities()
        ids = {}
        for target in targets:
            desc = descriptors.get((target, env))
            if not desc:
                raise ModeError('env-gone' if recorded is not None else 'policy')
            ids[target] = identity(desc)
        if recorded is not None and ids != recorded['targets']:
            raise ModeError('env-gone')
        return {'env': env, 'targets': ids, 'mode_gen': cfg['mode_gen'], 'members': members,
                'off': [x for x in cfg['off'] if any(x in (m['pack'], m['skill']) for m in members)],
                **({'lock': cfg['lock']} if cfg['lock'] else {})}

    def check(self, binding, *, recorded=False):
        if not isinstance(binding, dict):
            raise ModeError('env-changed')
        try:
            now = self.resolve(binding['members'], recorded=binding if recorded or binding.get('undo_of') else None)
            if not recorded and (now != {k: v for k, v in binding.items() if k != 'undo_of'}):
                raise ModeError('env-changed')
        except (KeyError, TypeError, ModeError) as exc:
            if recorded:
                raise ModeError('env-gone') from exc
            raise ModeError('env-changed') from exc
        return binding

    def execute(self, binding, calls, executors, *, recorded=False):
        """Preflight the COMPLETE bundle, then invoke only its recorded endpoints.

        Approval/journalling belong to callers (AVB-15). No partial bundle when an
        executor/identity is absent. Crash recovery passes recorded=True.
        """
        self.check(binding, recorded=recorded)
        if set(calls) != set(binding['targets']):
            raise ModeError('policy')
        keys = [(t, binding['env'], binding['targets'][t]) for t in calls]
        if any(k not in executors for k in keys):
            raise ModeError('env-gone' if recorded else 'policy')
        self.check(binding, recorded=recorded)  # immediately before the first target call
        return {t: executors[k](calls[t]) for t, k in zip(calls, keys)}


def site_members(ops, registry):
    """Only the installed site op registry is writable here; future till ops fail closed.

    The four-pack manifest belongs to AVB-09. Today all registered typed ops write
    site content; front-end templates and till writes have no installed ops yet.
    """
    if not ops or any(not isinstance(c, dict) or c.get('op') not in registry for c in ops):
        raise ModeError('policy')
    return [{'pack': 'site', 'skill': c['op'], 'target': 'site'} for c in ops]


def skill_pack(skill):
    # AVB-09's manifest may supply pack. Until then use the adopted existing groups.
    pack = getattr(skill, 'pack', None)
    if pack in PACKS:
        return pack
    return {'report': 'reports', 'social': 'reports', 'answer': 'core', 'backlog': 'core'}.get(
        skill.group, 'front' if skill.name == 'page.faq' else 'site')
