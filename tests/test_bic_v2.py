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


class LifecycleTests(BicV2Case):
    END = {'round': {'action': 'end', 'evidence': {
        'asked': 'May we deliver and end this round?', 'answer': 'Yes, end it.',
        'source': 'fixture-turn-2'}}}
    REOPEN = {'round': {'action': 'reopen', 'evidence': {
        'original_promise': 'preserve approved intent', 'defect': 'omitted an accepted constraint',
        'scope': 'that omitted constraint', 'source': 'fixture-turn-3'}}}

    def bad_apply(self, update, error='invalid_update', expected=1):
        import json
        path = self.scratch / 'update.json'
        path.write_text(json.dumps(update))
        return self.rpc('apply', '--project', self.project, '--record-id', 'BIC-0001',
                        '--expected-revision', expected, '--current-draft', self.current,
                        '--history-draft', self.history, '--update-draft', path, error=error)

    def test_end_version_survives_limited_reopening_and_second_confirmation(self):
        self.apply()
        ended = self.apply(1, 'BIC-0001', self.END)
        self.assertEqual(ended['revision'], 2)
        original = self.read(2)
        self.assertEqual(original['source_kind'], 'saved')
        self.assertEqual(original['round']['state'], 'completed')
        self.current.write_text(self.current.read_text().replace('Keep the approved direction', 'Repair the original promise'))
        self.apply(2, 'BIC-0001', self.REOPEN)
        self.assertEqual(self.read()['round']['state'], 'open')
        self.apply(3, 'BIC-0001', self.END)
        self.assertEqual(self.read(2)['current']['text'], original['current']['text'])
        self.assertIn('Repair the original promise', self.read(4)['current']['text'])
        self.assertEqual(self.read(4)['round']['evidence']['source'], 'fixture-turn-2')

    def test_saved_open_version_is_exact_idempotent_and_not_completed(self):
        from pathlib import Path
        self.apply()
        for _ in range(2):
            result = self.rpc('save-version', '--project', self.project, '--record-id', 'BIC-0001', '--revision', 1)
            self.assertEqual(result['revision'], 1)
        original = self.read(1)
        self.assertEqual(original['round']['state'], 'open')
        self.assertIn('/versions/BIC-0001/r1/', original['current']['path'])
        self.assertEqual(self.read()['revision'], 1)
        self.apply(1, 'BIC-0001')
        self.assertEqual(self.read(1)['current'], original['current'])
        Path(original['current']['path']).write_text('corrupted saved input')
        self.rpc('save-version', '--project', self.project, '--record-id', 'BIC-0001', '--revision', 1, error='version_conflict')

    def test_missing_saved_body_never_falls_back_to_current(self):
        from pathlib import Path
        self.apply()
        self.rpc('save-version', '--project', self.project, '--record-id', 'BIC-0001', '--revision', 1)
        Path(self.read(1)['current']['path']).unlink()
        self.rpc('read', '--project', self.project, '--record-id', 'BIC-0001', '--revision', 1, error='version_unavailable')

    def test_completed_rejects_ordinary_apply_and_incomplete_reopening(self):
        self.apply(update=self.END)
        self.bad_apply({}, 'round_closed')
        self.bad_apply({'round': {'action': 'reopen', 'evidence': {'scope': 'everything'}}})
        self.assertEqual(self.read()['revision'], 1)
        self.assertEqual(self.read()['round']['state'], 'completed')

    def test_end_requires_exact_nonempty_evidence_and_unknown_fields_reject(self):
        self.apply()
        for update in [
            {'round': {'action': 'end'}},
            {'round': {'action': 'end', 'evidence': {'asked': 'End?', 'answer': '', 'source': 'turn'}}},
            {'round': {'action': 'end', 'evidence': {'asked': 'End?', 'answer': 'Yes', 'source': 'turn', 'extra': 'no'}}},
            {'round': {'action': 'end', 'evidence': self.END['round']['evidence'], 'extra': True}},
            {'finished': True},
            {'round': None},
        ]:
            with self.subTest(update=update):
                self.bad_apply(update)
        self.assertEqual(self.read()['round']['state'], 'open')
        self.assertEqual(self.read()['revision'], 1)

    def test_explicit_pause_resume_cancel_and_replacement_preserve_distinct_facts(self):
        self.apply()
        self.apply(1, 'BIC-0001', {'round': {'action': 'pause', 'evidence': {'source': 'fixture pause'}}})
        self.assertEqual(self.read()['round']['state'], 'paused')
        self.apply(2, 'BIC-0001', {'round': {'action': 'resume', 'evidence': {'source': 'fixture resume'}}})
        self.assertEqual(self.read()['round']['state'], 'open')
        self.apply(3, 'BIC-0001', {'round': {'action': 'cancel', 'evidence': {'source': 'fixture cancel'}}})
        self.assertEqual(self.read()['round']['state'], 'cancelled')
        self.bad_apply({'round': {'action': 'resume', 'evidence': {'source': 'fixture'}}}, 'invalid_transition', expected=4)
        self.apply()
        self.apply(1, 'BIC-0002', {'round': {'action': 'replace', 'evidence': {'successor_record_id': 'BIC-0001', 'source': 'fixture replacement'}}})
        replacement = self.rpc('read', '--project', self.project, '--record-id', 'BIC-0002', '--current')
        self.assertEqual(replacement['round']['state'], 'replaced')
        self.assertEqual(replacement['round']['evidence']['successor_record_id'], 'BIC-0001')
        self.assertEqual(self.read()['round']['state'], 'cancelled')

    def test_independent_records_do_not_change_existing_rounds_or_infer_completion(self):
        self.apply()
        self.apply()
        self.assertEqual(self.read()['round']['state'], 'open')
        self.apply(1, 'BIC-0001', self.END)
        old = self.read(2)
        self.apply()
        self.assertEqual(self.read(2), old)
        self.assertEqual(self.rpc('status', '--project', self.project)['records'], ['BIC-0001', 'BIC-0002', 'BIC-0003'])

    def test_same_id_in_another_project_cannot_resolve_this_saved_version(self):
        from pathlib import Path
        other = Path(self.temp.name) / 'other'
        other.mkdir()
        self.apply(update=self.END)
        self.rpc('read', '--project', other, '--record-id', 'BIC-0001', '--revision', 1, error='not_enrolled')

    def test_end_failure_prepares_no_published_partial_version_and_retry_reuses_it(self):
        from bic_v2_support import load_bic, rendered_pair
        from unittest.mock import patch
        bic = load_bic()
        self.apply()
        before = self.read()
        real_write = bic.atomic_write
        def interrupted(path, text):
            if path.name == 'manifest.json':
                raise OSError('stop before publication')
            real_write(path, text)
        pair = rendered_pair(2)
        pair['update'] = self.END
        with patch.object(bic, 'atomic_write', interrupted):
            with self.assertRaises(OSError):
                bic.publish_update(self.project, 'BIC-0001', 1, pair)
        self.assertEqual(self.read(), before)
        self.rpc('read', '--project', self.project, '--record-id', 'BIC-0001', '--revision', 2, error='version_unavailable')
        self.apply(1, 'BIC-0001', self.END)
        self.assertEqual(self.read(2)['round']['state'], 'completed')

    def test_saved_descriptor_cannot_redirect_to_another_record_or_working_slot(self):
        import copy
        import json
        self.apply(update=self.END)
        self.apply()
        path = self.project / '.brainstorming-intent/manifest.json'
        original = json.loads(path.read_text())
        for field, value in [('record_id', 'BIC-0002'), ('revision', 2),
                             ('current_path', '.brainstorming-intent/records/BIC-0001/slots/a/current.md')]:
            with self.subTest(field=field):
                changed = copy.deepcopy(original)
                changed['versions']['BIC-0001']['1'][field] = value
                path.write_text(json.dumps(changed))
                self.rpc('status', '--project', self.project, error='invalid_manifest')
        path.write_text(json.dumps(original))

    def test_interrupted_version_body_is_not_registered_and_conflicting_retry_is_rejected(self):
        from bic_v2_support import load_bic, rendered_pair
        from unittest.mock import patch
        bic = load_bic()
        self.apply()
        before = self.read()
        pair = rendered_pair(2)
        pair['update'] = self.END
        real_write = bic.atomic_write
        def interrupted(path, text):
            real_write(path, text)
            if 'versions' in path.parts and path.name == 'current.md':
                raise OSError('stop after first saved body')
        with patch.object(bic, 'atomic_write', interrupted):
            with self.assertRaises(OSError):
                bic.publish_update(self.project, 'BIC-0001', 1, pair)
        self.assertEqual(self.read(), before)
        pair['current'] = pair['current'].replace('Keep the approved direction', 'Different proposed ending')
        with self.assertRaises(bic.BicError) as caught:
            bic.publish_update(self.project, 'BIC-0001', 1, pair)
        self.assertEqual(caught.exception.state, 'version_conflict')
        self.assertEqual(self.read(), before)


class PartsTests(BicV2Case):
    def part(self, name, text):
        path = self.scratch / f'{name}.md'
        path.write_text(text)
        return {'id': name, 'kind': 'history', 'draft': str(path)}

    def event(self, event_id='E1', part_id='H1'):
        return {'id': event_id, 'part_id': part_id, 'anchor': 'original-record',
                'title': 'spec input role', 'conditions': 'native spec design'}

    def test_old_event_read_preserves_original_and_discovers_current_recording_error(self):
        original = self.part('H1', '## Original record\nThis old entry misstates the approval.\n')
        self.apply(update={'parts': [original], 'events': [self.event()]})
        self.rpc('save-version', '--project', self.project, '--record-id', 'BIC-0001', '--revision', 1)
        correction = self.part('C1', 'The approved role was supplementary; the old entry was wrong.\n')
        self.apply(1, 'BIC-0001', {'parts': [correction], 'corrections': [
            {'target_event': 'E1', 'part_id': 'C1', 'kind': 'recording_error'}]})
        old = self.rpc('read', '--project', self.project, '--record-id', 'BIC-0001', '--revision', 1, '--event', 'E1')
        self.assertIn('misstates', old['parts']['H1']['text'])
        self.assertEqual(old['revision'], 1)
        self.assertEqual(old['corrections'][0]['kind'], 'recording_error')
        self.assertEqual(old['corrections'][0]['original_revision'], 1)
        self.assertEqual(old['corrections'][0]['source_revision'], 2)
        self.assertIn('supplementary', old['corrections'][0]['text'])
        self.assertIn('BIC-0001', old['parts']['H1']['text'])
        self.assertIn('--current --event E1', old['parts']['H1']['text'])
        self.assertIn(str(self.project), old['parts']['H1']['text'])
        self.assertEqual(self.read(1)['parts'], {})
        self.assertEqual(self.read()['parts'], {})
        self.assertEqual(self.read()['events']['E1']['part_id'], 'H1')

    def test_topic_updates_preserve_exact_saved_dependencies_and_full_effective_text(self):
        long_text = 'Accepted topic requirement remains necessary.\n' * 700
        topic = self.part('T1', long_text)
        topic['kind'] = 'topic'
        self.apply(update={'parts': [topic]})
        self.rpc('save-version', '--project', self.project, '--record-id', 'BIC-0001', '--revision', 1)
        old = self.read(1)
        self.assertIn(long_text, old['parts']['T1']['text'])
        self.assertIn('T1', old['current']['text'])
        self.assertIn(old['part_index']['T1']['relative_path'], old['current']['text'])
        topic = self.part('T1', 'Revised effective topic text.\n')
        topic['kind'] = 'topic'
        self.apply(1, 'BIC-0001', {'parts': [topic]})
        self.assertEqual(self.read(1)['parts'], old['parts'])
        new = self.read()
        self.assertIn('Revised effective', new['parts']['T1']['text'])
        self.assertNotEqual(new['parts']['T1']['path'], old['parts']['T1']['path'])

    def test_large_event_is_complete_and_does_not_end_or_renumber_round(self):
        import json
        text = '## Original record\n' + ('A whole historical event with necessary context.\n' * 700)
        self.apply(update={'parts': [self.part('H1', text)], 'events': [self.event()]})
        for revision in range(1, 5):
            self.apply(revision, 'BIC-0001')
        current = self.read()
        self.assertEqual(current['revision'], 5)
        self.assertEqual(current['round']['state'], 'open')
        self.assertEqual(current['parts'], {})
        selected = self.rpc('read', '--project', self.project, '--record-id', 'BIC-0001', '--current', '--event', 'E1')
        self.assertIn(text, selected['parts']['H1']['text'])
        self.assertEqual(current['history']['text'].count('A[Transcript authority]'), 1)
        self.assertFalse((self.project / '.brainstorming-intent/versions').exists())
        self.assertEqual(json.loads((self.project / '.brainstorming-intent/manifest.json').read_text())['next_record_number'], 2)

    def test_cross_part_supersession_is_distinct_from_recording_error(self):
        self.apply(update={'parts': [self.part('H1', '## Original record\nPreviously accepted choice.\n')], 'events': [self.event()]})
        self.apply(1, 'BIC-0001', {'parts': [self.part('H2', 'A later accepted direction replaces the former choice.\n')],
                                 'corrections': [{'target_event': 'E1', 'part_id': 'H2', 'kind': 'superseded'}]})
        selected = self.rpc('read', '--project', self.project, '--record-id', 'BIC-0001', '--current', '--event', 'E1')
        self.assertEqual(selected['corrections'][0]['kind'], 'superseded')
        self.assertIn('later accepted direction', selected['corrections'][0]['text'])
        self.assertIn('E1', selected['history']['text'])

    def test_registration_rejects_unknown_event_bad_anchor_duplicate_or_unsafe_ids(self):
        import json
        part = self.part('H1', '## Original record\nHistoric discussion.\n')
        invalid_updates = [
            {'parts': [part, part]},
            {'parts': [dict(part, id='../escape')]},
            {'parts': [dict(part, kind='unknown')]},
            {'parts': [part], 'events': [dict(self.event(), anchor='absent-heading')]},
            {'parts': [part], 'events': [dict(self.event(), part_id='unknown')]},
            {'parts': [part], 'events': [self.event(), self.event()]},
            {'parts': [part], 'corrections': [{'target_event': 'unknown', 'part_id': 'H1', 'kind': 'recording_error'}]},
            {'parts': [part], 'events': [dict(self.event(), extra='unrecognized')]},
        ]
        for update in invalid_updates:
            with self.subTest(update=update):
                path = self.scratch / 'bad-update.json'
                path.write_text(json.dumps(update))
                self.rpc('apply', '--project', self.project, '--expected-revision', 0,
                         '--current-draft', self.current, '--history-draft', self.history,
                         '--update-draft', path, error='invalid_update')
                self.assertFalse((self.project / '.brainstorming-intent/manifest.json').exists())
        self.apply(update={'parts': [part], 'events': [self.event()]})
        self.rpc('read', '--project', self.project, '--record-id', 'BIC-0001', '--current', '--event', 'missing', error='event_not_found')

    def test_saved_archive_dependencies_survive_without_default_body_expansion(self):
        import json
        from pathlib import Path
        self.apply(update={'parts': [self.part('H1', '## Original record\nOnly selected archive content.\n')], 'events': [self.event()]})
        self.rpc('save-version', '--project', self.project, '--record-id', 'BIC-0001', '--revision', 1)
        view = self.read(1)
        manifest = json.loads((self.project / '.brainstorming-intent/manifest.json').read_text())
        dependencies = manifest['versions']['BIC-0001']['1']['dependencies']
        archived = view['part_index']['H1']['relative_path']
        self.assertIn(archived, dependencies)
        Path(self.project / archived).unlink()
        # Default reading is deliberately limited; selected missing input is an error.
        self.assertEqual(self.read(1)['parts'], {})
        self.rpc('read', '--project', self.project, '--record-id', 'BIC-0001', '--revision', 1, '--event', 'E1', error='version_unavailable')

    def test_part_prepare_failure_does_not_publish_new_body_or_dependencies(self):
        from bic_v2_support import load_bic, rendered_pair
        from unittest.mock import patch
        bic = load_bic()
        self.apply()
        before = self.read()
        pair = rendered_pair(2)
        pair['update'] = {'parts': [self.part('H1', '## Original record\nNew archive.\n')], 'events': [self.event()]}
        real_write = bic.atomic_write
        def interrupted(path, text):
            real_write(path, text)
            if 'parts' in path.parts:
                raise OSError('stop after prepared part')
        with patch.object(bic, 'atomic_write', interrupted):
            with self.assertRaises(OSError):
                bic.publish_update(self.project, 'BIC-0001', 1, pair)
        self.assertEqual(self.read(), before)

    def test_read_to_draft_roundtrip_replaces_navigation_without_old_topic_path(self):
        topic = self.part('T1', 'First effective topic.\n')
        topic['kind'] = 'topic'
        self.apply(update={'parts': [topic]})
        old = self.read()
        for kind, path in [('current', self.current), ('history', self.history)]:
            path.write_text(old[kind]['text'].replace('BIC-0001', '{{RECORD_ID}}').replace('Revision: 1', 'Revision: {{REVISION}}'))
        topic = self.part('T1', 'Changed effective topic.\n')
        topic['kind'] = 'topic'
        self.apply(1, 'BIC-0001', {'parts': [topic]})
        new = self.read()
        self.assertNotIn(old['part_index']['T1']['relative_path'], new['current']['text'])
        self.assertEqual(new['current']['text'].count(new['part_index']['T1']['relative_path']), 1)
        self.assertIn('Keep the approved direction', new['current']['text'])

    def test_many_corrections_have_one_event_lookup_without_individual_daily_paths(self):
        self.apply(update={'parts': [self.part('H1', '## Original record\nHistorical entry.\n')], 'events': [self.event()]})
        for revision in range(1, 5):
            part_id = f'C{revision}'
            self.apply(revision, 'BIC-0001', {'parts': [self.part(part_id, f'Correction detail {revision}.\n')],
                                             'corrections': [{'target_event': 'E1', 'part_id': part_id, 'kind': 'recording_error'}]})
        selected = self.rpc('read', '--project', self.project, '--record-id', 'BIC-0001', '--current', '--event', 'E1')
        history = selected['history']['text']
        self.assertEqual(history.count('--current --event E1'), 1)
        self.assertEqual(len(selected['corrections']), 4)
        for revision in range(1, 5):
            self.assertNotIn(selected['part_index'][f'C{revision}']['relative_path'], history)
            self.assertIn(f'Correction detail {revision}.', selected['corrections'][revision - 1]['text'])

    def test_save_rejects_corrupt_part_before_creating_preserved_files(self):
        from pathlib import Path
        self.apply(update={'parts': [self.part('H1', '## Original record\nOriginal archive.\n')], 'events': [self.event()]})
        path = Path(self.read()['part_index']['H1']['path'])
        path.write_text('Changed archive bytes')
        self.rpc('save-version', '--project', self.project, '--record-id', 'BIC-0001', '--revision', 1, error='invalid_record')
        self.assertFalse((self.project / '.brainstorming-intent/versions').exists())

    def test_registered_part_identity_and_saved_dependency_closure_are_validated(self):
        import copy
        import json
        part = self.part('H1', '## Original record\nArchived approval.\n')
        self.apply(update={'parts': [part], 'events': [self.event()]})
        self.rpc('save-version', '--project', self.project, '--record-id', 'BIC-0001', '--revision', 1)
        path = self.project / '.brainstorming-intent/manifest.json'
        original = json.loads(path.read_text())
        for label in ('part path', 'part id', 'missing dependency', 'event target'):
            with self.subTest(label=label):
                changed = copy.deepcopy(original)
                if label == 'part path':
                    changed['records']['BIC-0001']['part_refs']['H1']['path'] = '.tmp/current.md'
                elif label == 'part id':
                    changed['records']['BIC-0001']['part_refs']['H1']['id'] = 'H2'
                elif label == 'missing dependency':
                    saved = changed['versions']['BIC-0001']['1']
                    del saved['dependencies'][saved['part_refs']['H1']['path']]
                else:
                    changed['events']['BIC-0001']['E1']['part_id'] = 'missing'
                path.write_text(json.dumps(changed))
                self.rpc('status', '--project', self.project, error='invalid_manifest')
        path.write_text(json.dumps(original))

    def test_same_event_id_in_another_record_does_not_leak_corrections(self):
        part = self.part('H1', '## Original record\nIndependent recorded approval.\n')
        self.apply(update={'parts': [part], 'events': [self.event()]})
        self.apply(update={'parts': [part], 'events': [self.event()]})
        self.apply(1, 'BIC-0002', {'parts': [self.part('C1', 'Correction for the second record only.\n')],
                                 'corrections': [{'target_event': 'E1', 'part_id': 'C1', 'kind': 'recording_error'}]})
        first = self.rpc('read', '--project', self.project, '--record-id', 'BIC-0001', '--current', '--event', 'E1')
        self.assertEqual(first['corrections'], [])


class BindingTests(BicV2Case):
    def test_binding_retains_exact_saved_input_after_further_apply(self):
        from pathlib import Path
        self.apply()
        self.rpc('bind', '--project', self.project, '--session-id', 'fixture-session',
                 '--record-id', 'BIC-0001', '--expected-revision', 1)
        self.apply(1, 'BIC-0001')
        pointer = self.rpc('bind', '--project', self.project, '--session-id', 'fixture-session', '--lookup')
        self.assertEqual(pointer['revision'], 1)
        self.assertTrue(Path(pointer['current_path']).resolve().is_relative_to(self.project.resolve()))
        self.assertIn('Revision: 1', Path(pointer['current_path']).read_text())
        self.assertEqual(self.read(1)['source_kind'], 'saved')
        self.assertTrue((self.project / '.brainstorming-intent/session-bindings.json').is_file())

    def test_binding_failure_keeps_saved_input_and_idempotent_retry_succeeds(self):
        from bic_v2_support import load_bic
        from unittest.mock import patch
        import argparse
        bic = load_bic()
        self.apply()
        real_write = bic.atomic_write
        def interrupted(path, text):
            if path.name == 'session-bindings.json':
                raise OSError('stop before binding publication')
            real_write(path, text)
        arguments = argparse.Namespace(project=str(self.project), plugin_data=None, lookup=False,
                                       session_id='fixture-session', record_id='BIC-0001', expected_revision=1)
        with patch.object(bic, 'atomic_write', interrupted):
            with self.assertRaises(OSError):
                bic.command_bind(arguments)
        self.assertEqual(self.read(1)['source_kind'], 'saved')
        self.assertFalse((self.project / '.brainstorming-intent/session-bindings.json').exists())
        for _ in range(2):
            self.rpc('bind', '--project', self.project, '--session-id', 'fixture-session',
                     '--record-id', 'BIC-0001', '--expected-revision', 1)
        self.assertEqual(self.read()['revision'], 1)

    def test_legacy_argument_returns_migration_instruction_without_touching_external_state(self):
        from pathlib import Path
        external = Path(self.temp.name) / 'legacy-data'
        external.mkdir()
        old = external / 'session-bindings.json'
        old.write_text('historical external state')
        before = old.read_bytes(), old.stat().st_mtime_ns
        value = self.rpc('bind', '--project', self.project, '--plugin-data', external,
                         '--session-id', 'fixture', '--lookup', error='binding_migration_required')
        self.assertIn('--project', value['error'])
        self.assertEqual((old.read_bytes(), old.stat().st_mtime_ns), before)
        self.assertFalse((self.project / '.brainstorming-intent').exists())

    def test_binding_alias_cannot_write_an_external_state_file(self):
        from pathlib import Path
        self.apply()
        outside = Path(self.temp.name) / 'outside.json'
        outside.write_text('{"schema_version": 1, "sessions": {}}')
        binding = self.project / '.brainstorming-intent/session-bindings.json'
        binding.symlink_to(outside)
        before = outside.read_bytes()
        self.rpc('bind', '--project', self.project, '--session-id', 'fixture', '--record-id', 'BIC-0001',
                 '--expected-revision', 1, error='invalid_bindings')
        self.assertEqual(outside.read_bytes(), before)
        self.assertFalse((self.project / '.brainstorming-intent/versions').exists())

    def test_external_root_draft_update_draft_and_part_are_rejected_before_publication(self):
        from pathlib import Path
        import json
        outside = Path(self.temp.name) / 'outside.md'
        outside.write_text(self.current.read_text())
        for draft_arg in ('--current-draft', '--history-draft', '--update-draft'):
            args = ['apply', '--project', self.project, '--expected-revision', 0,
                    '--current-draft', self.current, '--history-draft', self.history, draft_arg, outside]
            self.rpc(*args, error='invalid_draft')
        for symlink in (False, True):
            part_path = outside
            if symlink:
                part_path = self.scratch / 'part-alias.md'
                part_path.symlink_to(outside)
            update = self.scratch / 'update.json'
            update.write_text(json.dumps({'parts': [{'id': 'H1', 'kind': 'history', 'draft': str(part_path)}]}))
            self.rpc('apply', '--project', self.project, '--expected-revision', 0,
                     '--current-draft', self.current, '--history-draft', self.history, '--update-draft', update, error='invalid_draft')
        self.rpc('apply', '--project', self.project, '--record-id', '../escape', '--expected-revision', 0,
                 '--current-draft', self.current, '--history-draft', self.history, error='invalid_record_id')
        self.assertEqual(outside.read_text(), self.current.read_text())
        self.assertFalse((self.project / '.brainstorming-intent').exists())


class SnapshotDependencyTests(BicV2Case):
    part = PartsTests.part
    event = PartsTests.event

    def setUp(self):
        super().setUp()
        self.env.update(GIT_AUTHOR_NAME='BIC Fixture', GIT_AUTHOR_EMAIL='bic-fixture@example.invalid',
                        GIT_COMMITTER_NAME='BIC Fixture', GIT_COMMITTER_EMAIL='bic-fixture@example.invalid')

    def git(self, *args, project=None):
        import subprocess
        result = subprocess.run(['git', *map(str, args)], cwd=project or self.project,
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_snapshot_clone_recovers_saved_topics_original_event_and_later_correction(self):
        from pathlib import Path
        topic = self.part('T1', 'Original effective topic.\n')
        topic['kind'] = 'topic'
        self.apply(update={'parts': [topic, self.part('H1', '## Original record\nIncorrectly recorded approval.\n')], 'events': [self.event()]})
        self.rpc('bind', '--project', self.project, '--session-id', 'fixture', '--record-id', 'BIC-0001', '--expected-revision', 1)
        self.rpc('commit-snapshot', '--project', self.project, '--message', 'first complete input')
        topic = self.part('T1', 'Revised effective topic.\n')
        topic['kind'] = 'topic'
        self.apply(1, 'BIC-0001', {'parts': [topic, self.part('C1', 'The historical approval was wrong.\n')],
                                 'corrections': [{'target_event': 'E1', 'part_id': 'C1', 'kind': 'recording_error'}]})
        self.rpc('commit-snapshot', '--project', self.project, '--message', 'complete preserved dependencies')
        tracked = self.git('ls-tree', '-r', '--name-only', 'HEAD').splitlines()
        self.assertFalse(any('session-bindings' in path or '/.tmp/' in path or '/slots/a/' in path for path in tracked))
        self.assertTrue(any('/versions/BIC-0001/r1/version.json' in path for path in tracked))
        clone = Path(self.temp.name) / 'clone'
        self.git('clone', '-q', self.project, clone)
        restored = self.rpc('read', '--project', clone, '--record-id', 'BIC-0001', '--revision', 1, '--event', 'E1')
        self.assertIn('Original effective topic', restored['parts']['T1']['text'])
        self.assertIn('Incorrectly recorded', restored['parts']['H1']['text'])
        self.assertIn('historical approval was wrong', restored['corrections'][0]['text'])
        current = self.rpc('read', '--project', clone, '--record-id', 'BIC-0001', '--current')
        self.assertIn('Revised effective topic', current['parts']['T1']['text'])

    def test_missing_registered_dependency_rejects_snapshot_before_index_or_manifest_changes(self):
        from pathlib import Path
        self.apply(update={'parts': [self.part('H1', '## Original record\nRequired archive.\n')], 'events': [self.event()]})
        self.rpc('save-version', '--project', self.project, '--record-id', 'BIC-0001', '--revision', 1)
        self.rpc('commit-snapshot', '--project', self.project, '--message', 'baseline')
        target = self.read()['part_index']['H1']['path']
        Path(target).unlink()
        manifest = self.project / '.brainstorming-intent/manifest.json'
        before = manifest.read_bytes(), self.git('diff', '--cached'), self.git('rev-parse', 'HEAD')
        self.rpc('commit-snapshot', '--project', self.project, '--message', 'must reject', error='invalid_record')
        self.assertEqual((manifest.read_bytes(), self.git('diff', '--cached'), self.git('rev-parse', 'HEAD')), before)

    def test_replaced_unsaved_topic_is_retired_and_staged_only_when_previously_tracked(self):
        topic = self.part('T1', 'First topic.\n')
        topic['kind'] = 'topic'
        self.apply(update={'parts': [topic]})
        first_path = self.read()['part_index']['T1']['relative_path']
        self.rpc('commit-snapshot', '--project', self.project, '--message', 'first topic')
        for revision, text in [(1, 'Second topic.\n'), (2, 'Third topic.\n')]:
            topic = self.part('T1', text)
            topic['kind'] = 'topic'
            self.apply(revision, 'BIC-0001', {'parts': [topic]})
        self.rpc('commit-snapshot', '--project', self.project, '--message', 'replacement topic')
        tracked = self.git('ls-tree', '-r', '--name-only', 'HEAD').splitlines()
        self.assertNotIn(first_path, tracked)
        self.assertIn(self.read()['part_index']['T1']['relative_path'], tracked)
