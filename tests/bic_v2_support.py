import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_bic_cli import CLI, CURRENT_DRAFT, HISTORY_DRAFT, REPOSITORY_ROOT


def write_v1(project, revision=3, pending=True):
    state = project / '.brainstorming-intent'
    record = state / 'records/BIC-0001'
    record.mkdir(parents=True)
    for name, draft in [('current', CURRENT_DRAFT), ('history', HISTORY_DRAFT)]:
        (record / f'{name}.md').write_text(draft.replace('{{RECORD_ID}}', 'BIC-0001').replace('{{REVISION}}', str(revision)))
    manifest = {
        'schema_version': 1, 'writer_version': '1.0.1',
        'compatibility_state': 'compatible', 'project_state': 'active',
        'commit_pending': pending, 'next_record_number': 2,
        'records': {'BIC-0001': {
            'revision': revision, 'commit_pending': pending,
            'current_path': 'records/BIC-0001/current.md',
            'history_path': 'records/BIC-0001/history.md',
        }},
    }
    (state / 'manifest.json').write_text(json.dumps(manifest))
    return manifest


class BicV2Case(unittest.TestCase):
    def setUp(self):
        base = REPOSITORY_ROOT / '.tmp'
        base.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / 'project'
        self.scratch = self.project / '.tmp'
        self.scratch.mkdir(parents=True)
        self.current = self.scratch / 'current.md'
        self.history = self.scratch / 'history.md'
        self.current.write_text(CURRENT_DRAFT)
        self.history.write_text(HISTORY_DRAFT)
        self.env = dict(os.environ, TMPDIR=str(self.scratch), PYTHONDONTWRITEBYTECODE='1')
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True, env=self.env)

    def rpc(self, *args, error=None):
        result = subprocess.run([sys.executable, str(CLI), *map(str, args)],
                                cwd=self.project, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2 if error else 0, result.stderr or result.stdout)
        self.assertTrue(result.stdout.strip(), result.stderr or 'CLI returned no JSON')
        value = json.loads(result.stdout)
        if error:
            self.assertFalse(value['ok'])
            self.assertEqual(value['state'], error)
        return value

    def apply(self, expected=0, record=None, update=None):
        args = ['apply', '--project', self.project, '--expected-revision', expected,
                '--current-draft', self.current, '--history-draft', self.history]
        if record:
            args += ['--record-id', record]
        if update is not None:
            path = self.scratch / 'update.json'
            path.write_text(json.dumps(update))
            args += ['--update-draft', path]
        return self.rpc(*args)

    def read(self, revision=None):
        target = ['--current'] if revision is None else ['--revision', revision]
        return self.rpc('read', '--project', self.project, '--record-id', 'BIC-0001', *target)


def load_bic():
    import importlib.util
    spec = importlib.util.spec_from_file_location('bic_under_test', CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rendered_pair(revision):
    return {name: draft.replace('{{RECORD_ID}}', 'BIC-0001').replace('{{REVISION}}', str(revision))
            for name, draft in [('current', CURRENT_DRAFT), ('history', HISTORY_DRAFT)]} | {'update': {}}
