"""Execute actual app function bodies and canonical judge; no app bootstrap/DB."""
import ast
from pathlib import Path

import pytest

import map_battle_runtime as runtime
from choice_bridge_draft import (
    CHOICE_ADAPTER_ENABLED, ChoiceBridgeUnavailable, reject_unavailable_choice,
)
from sgf_engine.parser.sgf_parser import parse_sgf
from sgf_point_transform import transform_sgf


ROOT = Path(__file__).resolve().parents[1]
APP = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))


def app_function(name, namespace=None):
    namespace = {} if namespace is None else namespace
    node = next(n for n in APP.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'actual-app-body', 'exec'), namespace)
    return namespace[name]


transform = app_function('_transform_sgf')
point = app_function('_transform_point')


@pytest.mark.parametrize('size', [5, 9, 13, 19])
@pytest.mark.parametrize('t', range(8))
def test_actual_app_points_markers_judge_and_reverse_submission(size, t):
    # Independent explicit oracle, not the implementation helper.
    n, x, y = size - 1, 1, 2
    expected = [(x, y), (n-y, x), (n-x, n-y), (y, n-x),
                (n-x, y), (x, n-y), (y, x), (n-y, n-x)][t]
    pair = ''.join(chr(v + 97) for v in expected)
    props = ''.join(f'{p}[bc]' for p in ('AB', 'AW', 'AE', 'TR', 'SQ', 'CR', 'MA'))
    sgf = f'(;SZ[{size}]{props}LB[bc:A:1]C[bc];B[bc];W[])'
    result = transform(sgf, t)
    for p in ('AB', 'AW', 'AE', 'TR', 'SQ', 'CR', 'MA', 'B'):
        assert f'{p}[{pair}]' in result
    assert f'LB[{pair}:A:1]C[bc]' in result
    assert ';W[]' in result
    assert point(x, y, size, t) == expected
    attempt = dict(board_size=size, player_color='B', transform_id=f't{t}')
    payload = dict(battle_id='offline', attempt_id='a', submission_nonce='private-nonce',
                   battle_revision=0, question_revision='r', player_color='B',
                   transform_id=f't{t}', transform_version='v',
                   moves=[dict(x=expected[0], y=expected[1])])
    canonical = runtime.canonicalize_answer(payload, attempt)
    # Judge against ORIGINAL source: verifies actual reverse mapping, not just
    # display parser assertions. Keep setup separate from solution fixture.
    question = dict(id=1, content=f'(;SZ[{size}]PL[B];B[bc])')
    assert runtime.judge_map_battle_answer_v1(question, attempt, canonical).result == 'CORRECT'
    verify = app_function('_rt_server_verify', dict(
        parse_sgf=parse_sgf, _rt_transform_idx=lambda *args: t))
    assert verify(question, 'offline', payload['moves']) is True


def test_c_exact_nine_by_nine_oracle():
    source = '(;SZ[9]AB[bc]LB[bc:A:1]TR[bc]SQ[bc]CR[bc]MA[bc]C[bc])'
    assert transform(source, 1) == '(;SZ[9]AB[gb]LB[gb:A:1]TR[gb]SQ[gb]CR[gb]MA[gb]C[bc])'


@pytest.mark.parametrize('t', range(8))
def test_raw_labels_text_escape_newlines_and_tree_boundaries(t):
    label = r'A:1\:two\]three\\tail'
    text = r'B[bc\] SZ[19\] ;(TR[bc\]) \\ end' + '\r\n答案 bc'
    source = f'(;SZ[9]GN[{text}]C[{text}]LB[bc:{label}]XX[bc](;B[bc])(;W[bc]))'
    pair = ''.join(chr(v + 97) for v in point(1, 2, 9, t))
    expected = (f'(;SZ[9]GN[{text}]C[{text}]LB[{pair}:{label}]XX[bc]'
                f'(;B[{pair}])(;W[{pair}]))')
    assert transform(source, t) == expected
    if t == 0:
        assert transform(source, t).encode('utf-8') == source.encode('utf-8')


@pytest.mark.parametrize('size', [5, 9, 13, 19])
@pytest.mark.parametrize('t', range(8))
def test_compressed_lists_expand_to_same_transformed_rectangle(size, t):
    props = ('AB', 'AW', 'AE', 'TR', 'SQ', 'CR', 'MA')
    result = transform(f'(;SZ[{size}]' + ''.join(f'{p}[ab:cd][bc]' for p in props) + ')', t)
    # Inspect raw declared values; expanded point sets are an independent oracle.
    from sgf_point_transform import _properties
    expected = {point(x, y, size, t) for x in range(3) for y in range(1, 4)}
    for _, _, prop, start, end in _properties(result):
        if prop not in props or ':' not in result[start:end]:
            continue
        a, b = result[start:end].split(':')
        x1, y1, x2, y2 = [ord(c)-97 for c in a+b]
        actual = {(x, y) for x in range(x1, x2+1) for y in range(y1, y2+1)}
        assert actual == expected


def test_size_is_root_property_not_comment_and_collection_is_scoped():
    assert transform(r'(;C[SZ[5\]];B[bc])', 1) == r'(;C[SZ[5\]];B[qb])'
    assert transform('(;SZ[9];B[bc])(;SZ[13];B[bc])', 1) == '(;SZ[9];B[gb])(;SZ[13];B[kb])'
    assert transform('(;AB[bc]SZ[9])', 1) == '(;AB[gb]SZ[9])'


@pytest.mark.parametrize('t', range(8))
def test_pass_invalid_points_and_unknown_properties_untouched(t):
    s = '(;SZ[9]XX[bc]LB[bad]TR[zz]AB[];B[];W[tt])'
    assert transform(s, t) == s


@pytest.mark.parametrize('source', ['(;SZ[9:13];B[bc])', '(;SZ[0])',
                                   '(;C[unterminated)', '(;SZ[9]SZ[13])'])
def test_unsupported_input_fails_without_partial_transformation(source):
    assert transform(source, 0) is source
    with pytest.raises(ValueError):
        transform(source, 1)


@pytest.mark.parametrize('user,entitled,enable,status,code', [
    (None, True, False, 401, 'login_required'),
    (None, True, True, 401, 'login_required'),
    (7, False, False, 403, 'question_forbidden'),
    (7, False, True, 403, 'question_forbidden'),
    (7, 1, True, 403, 'question_forbidden'),
    (7, True, False, 404, 'feature_off'),
    (7, True, True, 503, 'verified_choice_schema_unavailable'),
])
def test_choice_draft_negative_only_no_attempt_answer_or_nonce(user, entitled, enable, status, code):
    assert CHOICE_ADAPTER_ENABLED is False
    with pytest.raises(ChoiceBridgeUnavailable) as error:
        reject_unavailable_choice(user_id=user, entitled=entitled, requested_enabled=enable)
    assert (error.value.status, error.value.code) == (status, code)
    assert vars(error.value) == dict(code=code, status=status)


def test_lb_cannot_infer_choices_or_accept_client_verdict():
    with pytest.raises(TypeError):
        reject_unavailable_choice(user_id=7, entitled=True, question='(;LB[aa:1])')
    with pytest.raises(TypeError):
        reject_unavailable_choice(user_id=7, entitled=True, correct_choice_id='a')


@pytest.mark.parametrize('t', range(8))
def test_roundtrip_raw_properties_and_declared_nonstandard_square(t):
    source = r'(;SZ[25]AB[bc][aa:cd]AE[dd]LB[bc:A\:B\]C\\]GN[answer bc];B[tt])'
    inverse = [0, 3, 2, 1, 4, 5, 6, 7][t]
    assert transform(transform(source, t), inverse) == source
    # tt is an intersection on a 25 board, legacy pass only for <=19 boards.
    if t == 1:
        assert ';B[ft]' in transform(source, t)
