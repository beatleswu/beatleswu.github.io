"""Read only six explicit repository fixtures, never discover/open a live DB.

Structural terminal-policy estimate, not end-to-end availability or population
sampling. Output binds every observation to exact fixture bytes.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sgf_answer_authority import AnswerAuthorityUnavailable, terminal_verdict
from sgf_engine.parser.sgf_parser import parse_sgf

FIXTURES = (
    'tests/fixtures/acceptance/questions.json',
    'tests/fixtures/lord_trial_natural/questions.json',
    'tests/fixtures/lord_trial_natural/questions_multi_ply.json',
    'tests/fixtures/g009_p1_questions.json',
    'tests/fixtures/g009_p1_a1_questions.json',
    'tests/fixtures/g009_rc0102_questions.json',
)


def audit(paths=FIXTURES, *, historical=False):
    reports = []
    for name in paths:
        raw = (ROOT / name).read_bytes()
        records = json.loads(raw)
        if not isinstance(records, list):
            raise ValueError(f'fixture is not record list: {name}')
        if historical and (len(records) != 41591 or hashlib.sha256(raw).hexdigest() !=
                           '4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28'):
            raise ValueError('historical_corpus_identity_mismatch')
        stats, fields, reasons = Counter(), Counter(), Counter()
        for q in records:
            fields.update(q.keys())
            stats['records'] += 1
            if q.get('accepted_moves') or q.get('accepted_answers'):
                stats['records_with_alternative_authority'] += 1
            try:
                root = parse_sgf(q.get('content', ''))
            except ValueError:
                stats['parse_failed'] += 1
                continue
            nodes, pending = [], [root]
            while pending:
                node = pending.pop()
                nodes.append(node)
                pending.extend(node.children)
            if any(len(n.children) > 1 for n in nodes):
                stats['multi_branch_records'] += 1
            if any('LB' in n.metadata.get('properties', {}) for n in nodes):
                stats['lb_records_not_choice_evidence'] += 1
            if any(any(k in n.metadata.get('properties', {}) for k in ('C', 'TE', 'BM', 'DO', 'IT'))
                   for n in nodes):
                stats['annotated_records'] += 1
            blocked = False
            for leaf in (n for n in nodes if not n.children):
                try:
                    terminal_verdict(q, root, leaf)
                except AnswerAuthorityUnavailable as exc:
                    blocked = True
                    reasons[str(exc)] += 1
            stats['terminal_policy_unavailable_records' if blocked else
                  'terminal_policy_available_records'] += 1
        reports.append(dict(path=name, sha256=hashlib.sha256(raw).hexdigest(),
                            counts=dict(stats), fields=dict(sorted(fields.items())),
                            unavailable_leaf_reasons=dict(reasons)))
    return dict(schema='g070-fixture-audit-v1', fixtures=reports,
                scope=('Historical 2026-08-09 offline snapshot, not current Production. ' if historical else
                       'Synthetic fixtures only; nonrepresentative and may overlap. ') +
                      'Alternatives can bypass terminal policy. Not a live-corpus rate.',
                current_source_bound_41591_corpus='REQUIRED_BEFORE_ACCEPTANCE_NOT_EVALUATED')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--historical-corpus', type=Path)
    args = parser.parse_args()
    result = (audit((str(args.historical_corpus),), historical=True)
              if args.historical_corpus else audit())
    print(json.dumps(result, ensure_ascii=False, indent=2))
