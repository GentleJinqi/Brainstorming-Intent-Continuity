import json
from pathlib import Path

from bic_v2_support import BicV2Case, write_v1


class ValidationScopeTests(BicV2Case):
    def validate_current(self, revision, error=None):
        return self.rpc('validate', '--project', self.project,
                        '--record-id', 'BIC-0001', '--current-only',
                        '--expected-revision', revision, error=error)

    def manifest(self):
        return json.loads((self.project / '.brainstorming-intent/manifest.json').read_text())

    def part(self, part_id, kind, text):
        draft = self.scratch / f'{part_id}.md'
        draft.write_text(text)
        return {'id': part_id, 'kind': kind, 'draft': str(draft)}

    def test_current_validation_returns_exact_apply_pointer_and_explicit_scope(self):
        applied = self.apply()
        validated = self.validate_current(1)
        self.assertEqual(validated['validation_scope'], 'current')
        self.assertEqual(validated['records'], ['BIC-0001'])
        for field in ('record_id', 'revision', 'current_path', 'history_path'):
            self.assertEqual(validated[field], applied[field])
        full = self.rpc('validate', '--project', self.project)
        self.assertEqual(full, {'ok': True, 'state': 'valid', 'records': ['BIC-0001']})
        record_full = self.rpc('validate', '--project', self.project, '--record-id', 'BIC-0001')
        self.assertEqual(record_full, {**full, **{field: applied[field] for field in
                         ('record_id', 'revision', 'current_path', 'history_path')}})

    def test_other_record_body_corruption_is_outside_current_scope(self):
        self.apply()
        second = self.apply()
        Path(second['current_path']).write_text('broken unrelated record')
        self.validate_current(1)
        self.rpc('validate', '--project', self.project, error='invalid_record')

    def test_old_saved_body_corruption_is_outside_current_scope(self):
        self.apply()
        saved = self.rpc('save-version', '--project', self.project,
                         '--record-id', 'BIC-0001', '--revision', 1)
        self.apply(1, 'BIC-0001')
        Path(saved['current_path']).write_text('broken old saved body')
        self.validate_current(2)
        self.rpc('validate', '--project', self.project, '--record-id', 'BIC-0001',
                 error='version_conflict')

    def test_old_saved_topic_corruption_is_outside_new_topic_dependency(self):
        self.apply(update={'parts': [self.part('T1', 'topic', 'Original topic')]})
        self.rpc('save-version', '--project', self.project,
                 '--record-id', 'BIC-0001', '--revision', 1)
        old = self.manifest()['records']['BIC-0001']['part_refs']['T1']['path']
        self.apply(1, 'BIC-0001', {'parts': [self.part('T1', 'topic', 'Revised topic')]})
        (self.project / old).write_text('corrupt obsolete saved topic')
        self.validate_current(2)
        self.rpc('validate', '--project', self.project, error='version_conflict')

    def test_current_documents_must_both_match_the_expected_revision(self):
        applied = self.apply()
        for field in ('current_path', 'history_path'):
            with self.subTest(field=field):
                path = Path(applied[field])
                original = path.read_bytes()
                path.write_text('broken current document')
                self.validate_current(1, error='invalid_record')
                path.write_bytes(original)

    def test_current_topic_and_history_parts_are_required(self):
        self.apply(update={'parts': [self.part('T1', 'topic', 'Effective topic'),
                                     self.part('H1', 'history', 'Required historical detail')]})
        for part in self.manifest()['records']['BIC-0001']['part_refs'].values():
            with self.subTest(kind=part['kind']):
                path = self.project / part['path']
                original = path.read_bytes()
                path.write_text('corrupt registered part')
                self.validate_current(1, error='invalid_record')
                path.write_bytes(original)

    def test_correction_original_part_remains_required_after_topic_replacement(self):
        self.apply(update={'parts': [self.part('H1', 'history', '## Initial event\nOriginal')],
                           'events': [{'id': 'E1', 'part_id': 'H1', 'anchor': 'initial-event',
                                       'title': 'Initial event', 'conditions': 'Original observation'}]})
        self.apply(1, 'BIC-0001', {
            'parts': [self.part('T1', 'topic', 'Original correction')],
            'corrections': [{'target_event': 'E1', 'part_id': 'T1', 'kind': 'recording_error'}]})
        correction_path = self.manifest()['corrections'][0]['part']['path']
        self.apply(2, 'BIC-0001', {'parts': [self.part('T1', 'topic', 'Current topic')]})
        (self.project / correction_path).write_text('corrupt original correction')
        self.validate_current(3, error='invalid_record')

    def test_current_saved_descriptor_and_bodies_are_required_after_end(self):
        self.apply(update={'round': {'action': 'end', 'evidence': {
            'asked': 'End this round?', 'answer': 'Yes', 'source': 'fixture confirmation'}}})
        self.validate_current(1)
        saved = self.manifest()['versions']['BIC-0001']['1']
        for field in ('descriptor_path', 'current_path', 'history_path'):
            with self.subTest(field=field):
                path = self.project / saved[field]
                original = path.read_bytes()
                path.write_text('{}' if field == 'descriptor_path' else 'corrupt saved body')
                self.validate_current(1, error='version_conflict')
                path.write_bytes(original)

    def test_stale_expected_revision_does_not_validate_saved_or_newer_revision(self):
        self.apply()
        self.rpc('save-version', '--project', self.project,
                 '--record-id', 'BIC-0001', '--revision', 1)
        self.apply(1, 'BIC-0001')
        self.validate_current(1, error='revision_conflict')
        self.validate_current(3, error='revision_conflict')

    def test_incomplete_scope_arguments_are_rejected(self):
        self.apply()
        for extra in (['--current-only'],
                      ['--current-only', '--record-id', 'BIC-0001'],
                      ['--current-only', '--expected-revision', 1],
                      ['--record-id', 'BIC-0001', '--expected-revision', 1]):
            with self.subTest(extra=extra):
                self.rpc('validate', '--project', self.project, *extra, error='invalid_arguments')

    def test_success_and_revision_conflict_do_not_write_project_files(self):
        self.apply()
        def inventory():
            return {str(path.relative_to(self.project)): (path.read_bytes(), path.stat().st_mtime_ns)
                    for path in self.project.rglob('*') if path.is_file()}
        before = inventory()
        self.validate_current(1)
        self.validate_current(2, error='revision_conflict')
        self.assertEqual(inventory(), before)

    def test_current_validation_does_not_enroll_an_absent_project(self):
        self.validate_current(1, error='not_enrolled')
        self.assertFalse((self.project / '.brainstorming-intent').exists())

    def test_other_record_metadata_still_receives_global_manifest_validation(self):
        self.apply()
        self.apply()
        manifest = self.manifest()
        manifest['records']['BIC-0002']['revision'] = 0
        (self.project / '.brainstorming-intent/manifest.json').write_text(json.dumps(manifest))
        self.validate_current(1, error='invalid_manifest')

    def test_current_dependency_alias_is_rejected(self):
        self.apply(update={'parts': [self.part('T1', 'topic', 'Effective topic')]})
        path = self.project / self.manifest()['records']['BIC-0001']['part_refs']['T1']['path']
        alias_target = self.scratch / 'alias-target.md'
        alias_target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(alias_target)
        self.validate_current(1, error='invalid_record')

    def test_schema1_current_validation_remains_read_only(self):
        write_v1(self.project, revision=3)
        self.assertEqual(self.validate_current(3)['revision'], 3)
        self.assertEqual(self.manifest()['schema_version'], 1)
