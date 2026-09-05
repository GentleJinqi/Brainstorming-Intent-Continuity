from bic_v2_support import BicV2Case


class StorageTests(BicV2Case):
    def test_current_view_is_one_revision(self):
        self.apply()
        self.current.write_text(self.current.read_text().replace('Keep the approved direction', 'Keep revised direction'))
        self.apply(1, 'BIC-0001')
        view = self.read()
        self.assertEqual(view['revision'], 2)
        self.assertIn('Revision: 2', view['current']['text'])
        self.assertIn('Revision: 2', view['history']['text'])
        self.assertIn('Keep revised direction', view['current']['text'])

    def test_schema2_working_slots_do_not_create_history_versions(self):
        import json
        self.apply()
        manifest_path = self.project / '.brainstorming-intent/manifest.json'
        self.assertEqual(json.loads(manifest_path.read_text())['schema_version'], 2)
        for revision in range(1, 6):
            self.apply(revision, 'BIC-0001')
        state = self.project / '.brainstorming-intent'
        bodies = list((state / 'records/BIC-0001').rglob('*.md'))
        self.assertLessEqual(len(bodies), 4)
        self.assertFalse((state / 'versions').exists())
        self.assertEqual(self.read(6)['source_kind'], 'current')
        self.rpc('read', '--project', self.project, '--record-id', 'BIC-0001',
                 '--revision', 1, error='version_unavailable')

    def test_read_and_validate_do_not_enroll_an_absent_project(self):
        for command, extra in [('read', ['--record-id', 'BIC-0001', '--current']),
                               ('validate', [])]:
            self.rpc(command, '--project', self.project, *extra, error='not_enrolled')
        self.assertFalse((self.project / '.brainstorming-intent').exists())

    def test_v1_reads_and_migration_preserve_original_content_revision_and_pending(self):
        from bic_v2_support import write_v1
        import json
        write_v1(self.project, revision=3, pending=False)
        before = self.read()
        self.assertEqual(before['round'], {'state': 'unknown'})
        self.assertEqual(before['revision'], 3)
        self.assertEqual(self.rpc('status', '--project', self.project)['schema_version'], 1)
        self.rpc('validate', '--project', self.project)
        state = self.project / '.brainstorming-intent'
        original = {str(p.relative_to(state)): p.read_bytes() for p in state.rglob('*') if p.is_file()}
        self.rpc('apply', '--project', self.project, '--record-id', 'BIC-0001',
                 '--expected-revision', 3, '--current-draft', self.current,
                 '--history-draft', self.history, error='migration_required')
        self.assertEqual({str(p.relative_to(state)): p.read_bytes() for p in state.rglob('*') if p.is_file()}, original)
        self.rpc('migrate', '--project', self.project, '--expected-schema', 1)
        after = self.read()
        self.assertEqual(after['current']['text'], before['current']['text'])
        self.assertEqual(after['history']['text'], before['history']['text'])
        self.assertEqual(after['round'], {'state': 'unknown'})
        self.assertEqual(after['revision'], 3)
        manifest = json.loads((state / 'manifest.json').read_text())
        self.assertEqual(manifest['schema_version'], 2)
        self.assertFalse(manifest['commit_pending'])
        self.assertFalse(manifest['records']['BIC-0001']['commit_pending'])
        self.apply(3, 'BIC-0001')
        self.assertEqual(self.read()['revision'], 4)

    def test_draft_alias_outside_project_is_rejected_without_state(self):
        from pathlib import Path
        outside = Path(self.temp.name) / 'outside.md'
        outside.write_text(self.current.read_text())
        self.current.unlink()
        self.current.symlink_to(outside)
        self.rpc('apply', '--project', self.project, '--expected-revision', 0,
                 '--current-draft', self.current, '--history-draft', self.history,
                 error='invalid_draft')
        self.assertFalse((self.project / '.brainstorming-intent').exists())

    def test_registry_alias_outside_project_is_rejected_without_external_write(self):
        from pathlib import Path
        outside = Path(self.temp.name) / 'outside-state'
        outside.mkdir()
        (self.project / '.brainstorming-intent').symlink_to(outside, target_is_directory=True)
        self.rpc('apply', '--project', self.project, '--expected-revision', 0,
                 '--current-draft', self.current, '--history-draft', self.history,
                 error='invalid_project')
        self.assertEqual(list(outside.iterdir()), [])

    def test_prepublication_failures_leave_the_previous_pair_readable(self):
        from bic_v2_support import load_bic, rendered_pair
        from unittest.mock import patch
        bic = load_bic()
        self.apply()
        before = self.read()
        for stage in ['current.md', 'history.md', 'manifest.json']:
            with self.subTest(stage=stage):
                real_write = bic.atomic_write
                def interrupted(path, text):
                    if path.name == 'manifest.json':
                        if stage == path.name:
                            raise OSError('injected before manifest publication')
                    real_write(path, text)
                    if path.name == stage:
                        raise OSError('injected after body preparation')
                with patch.object(bic, 'atomic_write', interrupted):
                    with self.assertRaises(OSError):
                        bic.publish_update(self.project, 'BIC-0001', 1, rendered_pair(2))
                self.assertEqual(self.read(), before)
        self.apply(1, 'BIC-0001')
        view = self.read()
        self.assertIn('Revision: 2', view['current']['text'])
        self.assertIn('Revision: 2', view['history']['text'])

    def test_retirement_failure_cannot_undo_publication_and_only_registered_paths_are_cleaned(self):
        from bic_v2_support import load_bic, rendered_pair
        from pathlib import Path
        from unittest.mock import patch
        import json
        bic = load_bic()
        self.apply()
        before = self.read()
        retired_current = Path(before['current']['path'])
        unrelated = retired_current.parent / 'user-note.md'
        unrelated.write_text('not owned by BIC')
        real_unlink = Path.unlink
        def interrupted(path, *args, **kwargs):
            if path == retired_current:
                raise PermissionError('injected retirement interruption')
            return real_unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', interrupted):
            bic.publish_update(self.project, 'BIC-0001', 1, rendered_pair(2))
        self.assertEqual(self.read()['revision'], 2)
        self.assertTrue(retired_current.exists())
        manifest = json.loads((self.project / '.brainstorming-intent/manifest.json').read_text())
        self.assertIn(str(retired_current.relative_to(self.project)), manifest['retired_paths'])
        self.apply(2, 'BIC-0001')
        self.assertIn('Revision: 3', self.read()['current']['text'])
        self.assertEqual(unrelated.read_text(), 'not owned by BIC')

    def test_old_writer_holds_schema2_read_only(self):
        import json
        import subprocess
        import sys
        from bic_v2_support import CLI
        self.apply()
        state = self.project / '.brainstorming-intent'
        before = {str(p.relative_to(state)): p.read_bytes() for p in state.rglob('*') if p.is_file()}
        # The historical writer is supplied by the execution's immutable baseline.
        old_cli = self.scratch / 'old-bic.py'
        result = subprocess.run(['git', 'show', 'v0.1.4:' + str(CLI.relative_to(CLI.parents[5]))],
                                cwd=CLI.parents[5], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        old_cli.write_text(result.stdout)
        result = subprocess.run([sys.executable, str(old_cli), 'apply', '--project', str(self.project),
                                 '--record-id', 'BIC-0001', '--expected-revision', '1',
                                 '--current-draft', str(self.current), '--history-draft', str(self.history)],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stdout)['state'], 'compatibility_hold')
        self.assertEqual({str(p.relative_to(state)): p.read_bytes() for p in state.rglob('*') if p.is_file()}, before)

    def test_readers_share_the_writer_lock_until_complete_publication(self):
        import json
        import select
        import subprocess
        import sys
        from bic_v2_support import CLI
        self.apply()
        writer_code = '''
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('bic', sys.argv[1])
bic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bic)
real_write = bic.atomic_write
def paused_write(path, text):
    real_write(path, text)
    if path.name == 'current.md':
        print('prepared', flush=True)
        sys.stdin.readline()
bic.atomic_write = paused_write
sys.argv = sys.argv[1:]
raise SystemExit(bic.main())
'''
        reader_code = '''
import importlib.util, sys
spec = importlib.util.spec_from_file_location('bic', sys.argv[1])
bic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bic)
real_flock = bic.fcntl.flock
def observed_flock(fd, mode):
    try:
        real_flock(fd, mode | bic.fcntl.LOCK_NB)
    except BlockingIOError:
        print('blocked', flush=True)
        real_flock(fd, mode)
bic.fcntl.flock = observed_flock
sys.argv = sys.argv[1:]
raise SystemExit(bic.main())
'''
        for revision, command in enumerate(['read', 'status', 'validate'], start=1):
            with self.subTest(command=command):
                writer = subprocess.Popen([sys.executable, '-c', writer_code, str(CLI), 'apply',
                                           '--project', str(self.project), '--record-id', 'BIC-0001',
                                           '--expected-revision', str(revision),
                                           '--current-draft', str(self.current), '--history-draft', str(self.history)],
                                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          text=True, env=self.env)
                reader = None
                try:
                    self.assertTrue(select.select([writer.stdout], [], [], 5)[0], 'writer did not prepare a body')
                    self.assertEqual(writer.stdout.readline().strip(), 'prepared')
                    args = [command, '--project', str(self.project)]
                    if command == 'read':
                        args += ['--record-id', 'BIC-0001', '--current']
                    reader = subprocess.Popen([sys.executable, '-c', reader_code, str(CLI), *args],
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env)
                    self.assertTrue(select.select([reader.stdout], [], [], 5)[0], 'reader did not report its lock attempt')
                    self.assertEqual(reader.stdout.readline().strip(), 'blocked')
                    writer_output, writer_error = writer.communicate('\n', timeout=5)
                    self.assertEqual(writer.returncode, 0, writer_error or writer_output)
                    reader_output, reader_error = reader.communicate(timeout=5)
                    self.assertEqual(reader.returncode, 0, reader_error or reader_output)
                    result = json.loads(reader_output)
                    if command == 'read':
                        self.assertEqual(result['revision'], 2)
                        self.assertIn('Revision: 2', result['current']['text'])
                        self.assertIn('Revision: 2', result['history']['text'])
                finally:
                    for process in [writer, reader]:
                        if process is not None:
                            if process.poll() is None:
                                process.kill()
                            process.communicate()

    def test_inactive_slot_alias_cannot_overwrite_the_active_pair(self):
        self.apply()
        before = self.read()
        slot_root = self.project / '.brainstorming-intent/records/BIC-0001/slots'
        (slot_root / 'b').symlink_to(slot_root / 'a', target_is_directory=True)
        self.rpc('apply', '--project', self.project, '--record-id', 'BIC-0001',
                 '--expected-revision', 1, '--current-draft', self.current,
                 '--history-draft', self.history, error='invalid_record')
        self.assertEqual(self.read(), before)

    def test_migration_preserves_v1_bytes_and_failed_preparation_leaves_v1_readable(self):
        from bic_v2_support import load_bic, write_v1
        from unittest.mock import patch
        import json
        bic = load_bic()
        write_v1(self.project, revision=3)
        state = self.project / '.brainstorming-intent'
        original = {}
        for kind in ['current', 'history']:
            path = state / f'records/BIC-0001/{kind}.md'
            path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
            original[kind] = path.read_bytes()
        before_manifest = (state / 'manifest.json').read_bytes()
        real_write = bic.atomic_write
        def interrupted(path, text):
            if path.name == 'manifest.json':
                raise OSError('injected before migration publication')
            real_write(path, text)
        with patch.object(bic, 'atomic_write', interrupted):
            with self.assertRaises(OSError):
                bic.migrate_project(self.project, 1)
        self.assertEqual((state / 'manifest.json').read_bytes(), before_manifest)
        self.assertEqual(self.read()['revision'], 3)
        for kind in ['current', 'history']:
            self.assertEqual((state / f'records/BIC-0001/{kind}.md').read_bytes(), original[kind])
        self.rpc('migrate', '--project', self.project, '--expected-schema', 1)
        manifest = json.loads((state / 'manifest.json').read_text())
        for kind in ['current', 'history']:
            self.assertEqual((state / manifest['records']['BIC-0001'][f'{kind}_path']).read_bytes(), original[kind])

    def test_schema2_manifest_rejects_mixed_slot_paths_and_unsafe_retirement(self):
        import copy
        import json
        self.apply()
        path = self.project / '.brainstorming-intent/manifest.json'
        original = json.loads(path.read_text())
        for change in ['slot', 'retirement']:
            with self.subTest(change=change):
                manifest = copy.deepcopy(original)
                if change == 'slot':
                    manifest['records']['BIC-0001']['history_path'] = 'records/BIC-0001/slots/b/history.md'
                else:
                    manifest['retired_paths'] = ['.tmp/current.md']
                path.write_text(json.dumps(manifest))
                self.rpc('read', '--project', self.project, '--record-id', 'BIC-0001',
                         '--current', error='invalid_manifest')
                self.assertTrue(self.current.exists())

    def test_migrate_requires_the_actual_expected_old_schema(self):
        self.apply()
        self.rpc('migrate', '--project', self.project, '--expected-schema', 1,
                 error='schema_conflict')
        self.assertEqual(self.read()['revision'], 1)

    def test_filesystem_publication_error_returns_json_and_keeps_old_view(self):
        self.apply()
        before = self.read()
        blocked_history = self.project / '.brainstorming-intent/records/BIC-0001/slots/b/history.md'
        blocked_history.mkdir(parents=True)
        self.rpc('apply', '--project', self.project, '--record-id', 'BIC-0001',
                 '--expected-revision', 1, '--current-draft', self.current,
                 '--history-draft', self.history, error='io_error')
        self.assertEqual(self.read(), before)
