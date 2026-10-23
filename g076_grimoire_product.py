"""Grimoire Product installation. No DDL, catalog or rights fallback.

MASTER supplies canonical providers on the service transaction's PG connection.
The corpus is a SHA-pinned server snapshot, never an HTTP upload. Providers must
read/lock canonical identity, membership and lesson policy on that connection;
never commit, create a connection or perform external effects. Registration is
explicit and must precede all hooks except the existing containment guard.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import UUID

from flask import Blueprint, jsonify, request, session, send_file, redirect

from g076_grimoire_adapter import GrimoireRejected
from g076_grimoire_pg_service import PgGrimoireSteps
from practice_answer_authority import verify_practice_attempt, PracticeAttemptError


def enabled(environ):
    return str(environ.get('G076_GRIMOIRE_STEPS_ENABLED', '')).strip().lower() in ('1', 'true', 'on')


def question_sha(question):
    return hashlib.sha256(json.dumps(question, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


class CanonicalCorpus:
    """Verify exact source bytes and index without modifying official questions.

    canonical(conn,qid) returns the independently trusted import receipt with
    source_record_uuid, corpus_sha256, question_sha256 and catalog_revision.
    These values MUST come from canonical provenance, not be synthesized from
    this object. No legacy numeric identity or local catalog is substituted.
    """
    def __init__(self, source_bytes, expected_sha256, canonical):
        if (not isinstance(source_bytes, bytes) or not isinstance(expected_sha256, str)
                or not re.fullmatch('[0-9a-f]{64}', expected_sha256)
                or hashlib.sha256(source_bytes).hexdigest() != expected_sha256
                or not callable(canonical)):
            raise ValueError('canonical_corpus_proof_required')
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate_corpus_key')
                result[key] = value
            return result
        def invalid_constant(value):
            raise ValueError('invalid_corpus_json_constant')
        rows = json.loads(source_bytes.decode('utf-8-sig'), object_pairs_hook=unique,
                          parse_constant=invalid_constant)
        if not isinstance(rows, list) or not rows:
            raise ValueError('canonical_corpus_required')
        self._rows = {}
        for q in rows:
            if (not isinstance(q, dict) or type(q.get('id')) is not int or q['id'] < 1
                    or q['id'] in self._rows or 'g076_catalog_revision' in q):
                raise ValueError('invalid_canonical_question')
            self._rows[q['id']] = json.dumps(q, ensure_ascii=False)
        self.sha256, self.canonical = expected_sha256, canonical

    def lookup(self, qid):
        raw = self._rows.get(qid) if type(qid) is int else None
        if raw is None:
            raise GrimoireRejected('canonical_question_missing', 503)
        return json.loads(raw)

    def proof(self, conn, qid):
        q = self.lookup(qid)
        proof = self.canonical(conn, qid)
        try:
            identity = str(UUID(proof['source_record_uuid']))
            valid = (proof['corpus_sha256'] == self.sha256
                     and proof['question_sha256'] == question_sha(q)
                     and re.fullmatch('[0-9a-f]{64}', proof['catalog_revision'])
                     and UUID(identity).int != 0)
        except (TypeError, ValueError, KeyError, AttributeError):
            valid = False
        if not valid:
            raise GrimoireRejected('canonical_provenance_unavailable', 503)
        return proof

    def load(self, conn, qid):
        q, proof = self.lookup(qid), self.proof(conn, qid)
        if type(q.get('grimoire_id')) is not int or q['grimoire_id'] < 1:
            raise GrimoireRejected('canonical_grimoire_membership_missing', 503)
        q['g076_catalog_revision'] = proof['catalog_revision']
        return q

    def identity(self, conn, qid):
        return self.proof(conn, qid)['source_record_uuid']


@dataclass(frozen=True)
class Lesson:
    question_id: int
    scope: str
    title: str


class ProductGrimoire(PgGrimoireSteps):
    def _steps_enabled(self):
        # Product always projects board-only SGF and judges on the server.
        # Do not enable global legacy routes as a side effect of this gate.
        return enabled(self.environ)

    def __init__(self, *, corpus, entitlements, lesson, **kwargs):
        if not isinstance(corpus, CanonicalCorpus) or not callable(entitlements) or not callable(lesson):
            raise ValueError('trusted_product_providers_required')
        self.corpus, self.lesson = corpus, lesson
        super().__init__(load=corpus.load, identity=corpus.identity,
                         admit=entitlements, **kwargs)

    def admission(self, uid):
        # Policy chooses qid AND stable scope; no browser question/round/flag.
        with self._transaction(uid) as conn:
            lesson = self.lesson(conn, uid)
            if (not isinstance(lesson, Lesson) or type(lesson.question_id) is not int
                    or not isinstance(lesson.scope, str) or not 1 <= len(lesson.scope) <= 128
                    or not isinstance(lesson.title, str) or not 1 <= len(lesson.title) <= 160):
                raise GrimoireRejected('canonical_lesson_unavailable', 503)
            self._question(conn, uid, lesson.question_id)
        # issue rechecks provenance, rights and catalog under its own owner lock.
        token = self.issue(uid, question_id=lesson.question_id, scope=lesson.scope)
        return dict(attempt_token=token, title=lesson.title)


LEGACY_RULES = frozenset(('/api/grimoire/training/daily', '/api/training/contaminated',
                          '/api/training/answer'))
LEGACY_ENDPOINTS = frozenset(('grimoire.api_training_daily', 'grimoire.api_training_contaminated',
                              'grimoire.api_training_answer'))
UNSAFE_SHARED_ENDPOINTS = frozenset(('training_daily', 'dc_today', 'dc_submit', 'dc_history',
    'dc_history_detail', 'get_mistakes', 'friend_challenge_detail',
    'friend_challenge_answer', 'rt_start', 'rt_resume', 'rt_answer',
    'map_battle_v1_prepare_attempt', 'map_battle_v1_resume_validation',
    'map_battle_v1_battle_state', 'map_battle_v1_submission_nonce',
    'map_battle_v1_answers', 'g076_map_battle_step_start',
    'g076_map_battle_step_submit'))


def install_product_grimoire(app, service=None, *, environ=None, lookup=None):
    """Explicit MASTER seam; does nothing until called, OFF legacy is untouched.

    Install before any writer hook. Endpoint identity also contains aliases.
    The separate Grimoire gate contains legacy paths even with global privacy
    OFF. Missing official providers close admission, never restore old writers.
    """
    if service is not None and not isinstance(service, ProductGrimoire):
        raise ValueError('product_grimoire_service_required')
    gate = service.environ if service is not None else (os.environ if environ is None else environ)

    def dependency():
        candidate = service if service is not None else app.config.get('G077_GRIMOIRE_SERVICE')
        if not isinstance(candidate, ProductGrimoire) or candidate.environ is not gate:
            raise GrimoireRejected('grimoire_official_providers_unavailable', 503)
        return candidate

    def classify(qid):
        # Once bound, classification shares the pinned service snapshot. A
        # changed raw file cannot relabel an issued Grimoire token as Practice.
        if service is not None or app.config.get('G077_GRIMOIRE_SERVICE') is not None:
            return dependency().corpus.lookup(qid)
        if lookup is not None:
            return lookup(qid)
        return dependency().corpus.lookup(qid)
    if 'g076_grimoire_product' in app.extensions:
        raise RuntimeError('product_grimoire_already_installed')
    hooks = app.before_request_funcs.get(None, [])
    if any(h is not app.extensions.get('g076_othermode_authority') for h in hooks):
        raise RuntimeError('grimoire_guard_must_precede_writers')
    if any(app.before_request_funcs.get(key) for key in app.before_request_funcs if key is not None):
        raise RuntimeError('grimoire_guard_must_precede_writers')

    def containment():
        if not enabled(gate) or request.url_rule is None:
            return None
        if request.path in ('/', '/index.html') and 'grimoire' in request.args:
            return redirect('/grimoire/player', code=302)
        deny = request.url_rule.rule in LEGACY_RULES or request.endpoint in LEGACY_ENDPOINTS
        # Legacy aggregate transports can reveal solutions or settle a selected
        # Grimoire question without a question locator in the request. Until
        # each has a trusted per-question adapter, contain them before handlers.
        deny = deny or request.endpoint in UNSAFE_SHARED_ENDPOINTS
        deny = deny or (request.endpoint or '').startswith('g076_daily_steps.')
        # Rules also cover transports whose endpoint names change in app.py.
        deny = deny or request.url_rule.rule in (
            '/api/adventure/map-battles/v1/attempts',
            '/api/adventure/map-battles/v1/attempts/<attempt_id>/resume-validation',
            '/api/adventure/map-battles/v1/battles/<battle_id>',
            '/api/adventure/map-battles/v1/answers',
            '/api/adventure/map-battles/v2/steps/start',
            '/api/adventure/map-battles/v2/steps',
            '/api/daily-challenge/history/<date_str>')
        if request.endpoint == 'get_question':
            try:
                deny = bool(classify(request.view_args.get('qid')).get('grimoire_id'))
            except GrimoireRejected:
                deny = True
        # The existing ?grimoire= player submits qid to the common SRS writer.
        # Ignore claimed mode/source/grade: classify by the pinned full corpus.
        by_question = (request.path in ('/api/srs/review', '/api/srs/practice/attempt')
                       or request.endpoint in ('srs_review', 'srs_practice_attempt'))
        by_token = (request.path == '/api/srs/practice/answer'
                    or request.endpoint == 'srs_practice_answer')
        nonmap = (request.path in ('/api/g076/nonmap/steps', '/api/g076/nonmap/steps/start')
                  or request.endpoint in ('g076_nonmap_steps.start', 'g076_nonmap_steps.submit'))
        if by_question or by_token or nonmap:
            if request.content_length and request.content_length > 32768:
                return jsonify(error='grimoire_legacy_request_too_large'), 413
            data = request.get_json(silent=True)
            qid = data.get('question_id') if isinstance(data, dict) else None
            # Aggregate daily selection has no trustworthy browser qid; contain
            # it even if a pre-rollout practice token is relabelled daily.
            if nonmap and isinstance(data, dict) and data.get('flow') == 'daily':
                return jsonify(error='grimoire_secure_player_required'), 409
            try:
                if by_token or nonmap:
                    uid = session.get('user_id')
                    if type(uid) is not int or uid < 1:
                        raise GrimoireRejected('authentication_required', 401)
                    # Resolve server-signed ownership; NEVER trust a browser qid
                    # alongside a token, including tokens issued before rollout.
                    attempt = verify_practice_attempt(app.secret_key,
                        data.get('attempt_token') if isinstance(data, dict) else None, user_id=uid)
                    qid = attempt['question_id']
                if isinstance(qid, str) and len(qid) <= 20 and qid.isascii() and qid.isdigit():
                    qid = int(qid)
                q = classify(qid)
                deny = bool(q.get('grimoire_id'))
            except (GrimoireRejected, PracticeAttemptError, KeyError):
                deny = True
        if deny:
            return jsonify(error='grimoire_secure_player_required'), 409
        return None

    app.before_request(containment)

    @app.after_request
    def containment_cache(response):
        if enabled(gate):
            response.headers['Cache-Control'] = 'private, no-store'
        return response
    bp = Blueprint('g076_grimoire_product', __name__)
    root = Path(__file__).resolve().parent

    @bp.after_request
    def private(response):
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @bp.before_request
    def boundary():
        if not enabled(gate):
            return jsonify(error='grimoire_steps_disabled'), 503
        if type(session.get('user_id')) is not int or session['user_id'] < 1:
            return jsonify(error='authentication_required'), 401
        if request.method == 'POST':
            if (request.headers.get('X-Grimoire-Request') != '1'
                    or request.headers.get('Sec-Fetch-Site') == 'cross-site'
                    or request.headers.get('Origin', request.host_url.rstrip('/')) != request.host_url.rstrip('/')):
                return jsonify(error='same_origin_required'), 403
            if request.content_length is None:
                return jsonify(error='request_body_required'), 400
            if request.content_length > 16384:
                return jsonify(error='request_too_large'), 413

    @bp.errorhandler(GrimoireRejected)
    def rejected(error):
        return jsonify(error=error.code), error.status

    def call(operation):
        try:
            return jsonify(operation())
        except GrimoireRejected:
            raise
        except Exception:
            app.logger.exception('Grimoire Product dependency failed')
            return jsonify(error='grimoire_backend_unavailable'), 503

    @bp.get('/api/g076/grimoire/product/manifest')
    def manifest():
        # Installation is independently observable; configuration is not proof
        # that an official importer or entitlement policy has been validated.
        try:
            dependency()
            configured = True
        except GrimoireRejected:
            configured = False
        return jsonify(player_url='/grimoire/player',
            admission_url='/api/g076/grimoire/product/admission',
            steps_url='/api/g076/grimoire/product/steps',
            flag='G076_GRIMOIRE_STEPS_ENABLED', global_privacy_required=False,
            providers_configured=configured, corpus_verified=False,
            entitlements_verified=False, product_readiness='HOLD',
            contained_aggregate_endpoints=sorted(UNSAFE_SHARED_ENDPOINTS),
            additional_containment='legacy Grimoire; signed practice; nonmap daily; direct question; daily step blueprint')

    @bp.get('/grimoire/player')
    def player():
        return send_file(root / 'grimoire_player.html')

    @bp.get('/grimoire/player.js')
    def script():
        return send_file(root / 'js/game/g076_grimoire_product_client.js', mimetype='application/javascript')

    @bp.post('/api/g076/grimoire/product/admission')
    def admission():
        if request.get_json(silent=True) != {}:
            raise GrimoireRejected('server_lesson_only', 400)
        return call(lambda: dependency().admission(session['user_id']))

    @bp.post('/api/g076/grimoire/product/steps')
    def steps():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) not in (
                {'attempt_token'}, {'attempt_token', 'step_index', 'step_nonce', 'move'}):
            raise GrimoireRejected('invalid_step_fields', 400)
        return call(lambda: dependency().run(session['user_id'], data['attempt_token'],
                    {k: v for k, v in data.items() if k != 'attempt_token'} or None))

    app.register_blueprint(bp)
    app.extensions['g076_grimoire_product'] = service
