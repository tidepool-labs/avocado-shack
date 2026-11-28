"""Host adapter for AVB-11's gate; the existing site writer/releaser remain sole executors."""
from pathlib import Path
from datetime import datetime, timezone

from hass import conversation, editor, sandbox
from hass.ops import load_registry


class SiteEditor(conversation.Editor):
    routes_chat = True

    def __init__(self, state, gate, live_factory, registry=None, clock=lambda: datetime.now(timezone.utc)):
        super().__init__(state, registry)
        self.gate, self.live_factory = gate, live_factory
        self.clock = clock
        self.conv, self._live = None, None

    def _draft(self, cid):
        if not editor.CHANGE_ID_RE.fullmatch(str(cid)):
            raise sandbox.ModeError('env-gone')
        try:
            draft = editor._read(Path(self.state) / 'drafts' / f'{cid}.json')
        except (OSError, ValueError):
            raise sandbox.ModeError('env-gone') from None
        if not isinstance(draft, dict):  # valid JSON of another root type is as unusable as a missing draft
            raise sandbox.ModeError('env-gone')
        return draft

    def _members(self, ops, skills):
        members = sandbox.site_members(ops, self.registry or load_registry())
        for skill in skills:
            if isinstance(skill, str):
                from hass.skills import load_skills
                skill = load_skills().get(skill)
            if skill is None: raise sandbox.ModeError('policy')
            members.append({'pack': sandbox.skill_pack(skill), 'skill': skill.name, 'target': 'site'})
        return members

    def skill_allowed(self, skill):
        try:
            return self.gate.allowed(sandbox.skill_pack(skill), skill.name)
        except (ValueError, OSError):
            return False

    def sync_settings(self, settings):
        try:
            cfg = sandbox.policy(self.gate.source())
            live = 'site' in cfg['live'] and not cfg['hold'] and not cfg['lock']
        except (ValueError, OSError):
            live = False
        if live:
            settings['liveSite'] = 'theavocadoman.com'
        else:
            settings.pop('liveSite', None)

    def prepare(self, ops, *, skills=(), members=None):
        return self._build(editor.prepare, ops, skills, members)

    def candidate(self, ops, *, skills=(), members=None):
        return self._build(editor.candidate, ops, skills, members)

    def _build(self, build, ops, skills, members):
        try:
            members = members or self._members(ops, skills)
            undos = [c['args']['changeId'] for c in ops if c['op'] == 'history.revert']
            if undos:
                if len(ops) != 1:
                    raise sandbox.ModeError('policy')
                original = self._draft(undos[0]).get('environment')
                self.gate.check(original, recorded=True)
                binding = self.gate.resolve(members, recorded=original)
                binding['undo_of'] = undos[0]
            else:
                binding = self.gate.resolve(members)
            return build({'ops': ops}, state=self.state, registry=self.registry, environment=binding, now=self.clock())
        except (OSError, ValueError, KeyError) as exc:
            return self._unavailable(exc)

    @staticmethod
    def _unavailable(exc):
        return {'result': 'env-gone' if isinstance(exc, sandbox.ModeError) and exc.code == 'env-gone' else 'refused',
                'reason': 'sandbox target unavailable or switched off'}

    def _check_candidate(self, draft):
        if not editor.bound_hash_valid(draft):
            raise sandbox.ModeError('env-changed')
        self.gate.check(draft['environment'])

    def render_candidate(self, draft):
        try:
            self._check_candidate(draft)
            return editor.render_candidate(draft, state=self.state, registry=self.registry, now=self.clock())
        except (OSError, ValueError, KeyError) as exc:
            return self._unavailable(exc)

    def persist_candidate(self, draft):
        try:
            self._check_candidate(draft)
            return editor.persist_candidate(draft, state=self.state, guard=lambda: self._check_candidate(draft))
        except (OSError, ValueError, KeyError) as exc:
            return self._unavailable(exc)

    def check_environment(self, cid, *, recorded=False):
        try:
            draft = self._draft(cid)
            if not editor.bound_hash_valid(draft): raise sandbox.ModeError('env-gone' if recorded else 'env-changed')
            self.gate.check(draft.get('environment'), recorded=recorded)
        except (sandbox.ModeError, OSError, ValueError) as exc:
            return {'result': getattr(exc, 'code', 'env-gone' if recorded else 'env-changed')}
        return None

    def _locked(self):
        return sandbox.policy(self.gate.source())['lock'] is not None

    def live(self):
        if self._locked():  # demo lock: the release engine is never constructed (went_live of a live change is already False)
            raise sandbox.ModeError('env-changed')
        self._live = self.live_factory()
        self._live.environment_guard = self.check_environment
        self._live.conv = self.conv
        return self._live

    def reprepare(self, cid, ops):
        try:
            members = self._draft(cid)['environment']['members']
            return self.prepare(ops, members=members)
        except (OSError, ValueError, KeyError):
            return {'result': 'refused', 'reason': 'sandbox target unavailable or switched off'}

    def apply(self, change_id, draft_hash, chat=None):
        cid = change_id
        if problem := self.check_environment(cid):
            return problem
        binding = self._draft(cid)['environment']
        if binding['env'] == 'live':
            try: live = self.live()
            except sandbox.ModeError as exc: return {'result': exc.code}
            return live.apply(cid, draft_hash, chat=chat)
        return editor.apply(cid, draft_hash, state=self.state, registry=self.registry,
                            guard=lambda: self.check_environment(cid), now=self.clock(),
                            recovery_guard=lambda cid: self.check_environment(cid, recorded=True))

    def recover(self):
        # The private writer only settles its existing local journal, never publishes.
        return editor.recover(state=self.state, now=self.clock(), guard=lambda cid: self.check_environment(cid, recorded=True))

    def render_draft(self, change_id):
        return editor.render_draft(change_id, state=self.state, registry=self.registry, now=self.clock())

    def reconcile(self):
        # Only an existing release journal can need publication recovery. Its identity
        # is checked by LiveEditor before any remote call; never infer it from mode.
        # Demo lock: no release recovery at all (no fetch, reset or push of the site checkout);
        # host.py only turns the lock on when every release journal is settled.
        source = self.gate.source()
        if sandbox.policy(source)['lock'] is not None:
            return
        root = Path(source['hostDir'])
        if (root / 'releases').is_dir():
            self.live().reconcile()

    def went_live(self, cid):
        try:
            if self._draft(cid).get('environment', {}).get('env') != 'live':
                return False
            if self.check_environment(cid, recorded=True):
                return False
            return self.live().went_live(cid)
        except (OSError, ValueError):
            return False
