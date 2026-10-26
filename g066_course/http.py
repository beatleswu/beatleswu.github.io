"""Unregistered Flask blueprint; G/D must supply all authority adapters."""
from .service import CourseError


def create_blueprint(service, *, current_user, csrf_valid, presenter, media):
    from flask import Blueprint, jsonify, request
    bp = Blueprint("g066_course_v1", __name__, url_prefix="/api/course-v1")

    @bp.before_request
    def guard():
        service._guard(current_user())
        if request.method == "POST" and csrf_valid() is not True:
            raise CourseError("csrf_required", 403)

    @bp.after_request
    def private(response):
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @bp.errorhandler(CourseError)
    def expected(error):
        return jsonify(error=error.code), error.status

    def body(required, optional=()):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not set(required) <= data.keys() or set(data) - set(required) - set(optional):
            raise CourseError("invalid_request_fields", 400)
        for field in ("run_id", "retry_id", "request_id"):
            if field in data and (not isinstance(data[field], str) or not 1 <= len(data[field]) <= 128):
                raise CourseError("invalid_request_fields", 400)
        return data

    @bp.get("/summary")
    def summary():
        return jsonify(service.summary(current_user()))

    @bp.post("/start")
    def start():
        d = body(("lesson", "request_id"))
        return jsonify(service.start(current_user(), d["lesson"], d["request_id"]))

    @bp.post("/answer")
    def answer():
        d = body(("run_id", "slot", "moves", "request_id"), ("retry_id",))
        return jsonify(service.answer(current_user(), d["run_id"], d["slot"], d["moves"], d["request_id"], d.get("retry_id")))

    @bp.post("/retry")
    def retry():
        d = body(("run_id", "slot", "request_id"), ("replace",))
        return jsonify(service.retry(current_user(), d["run_id"], d["slot"], d["request_id"], d.get("replace", False)))

    @bp.get("/question")
    def question():
        if set(request.args) - {"run_id", "slot", "retry_id"}:
            raise CourseError("invalid_request_fields", 400)
        try:
            slot = int(request.args.get("slot", ""))
        except ValueError:
            raise CourseError("invalid_slot", 400)
        return jsonify(service.question(current_user(), request.args.get("run_id", ""), slot, presenter, request.args.get("retry_id")))

    @bp.get("/media/<int:lesson>")
    def video(lesson):
        entry = service._lesson(lesson)
        # Adapter returns approved external URL / subtitle URL; never local Windows paths.
        value = media(current_user(), entry["id"], service.version)
        if not value or value.get("owner_review") != "APPROVED":
            raise CourseError("media_owner_review_required", 403)
        from urllib.parse import urlsplit
        url = urlsplit(value.get("external_url") or "")
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise CourseError("media_external_url_required", 503)
        return jsonify({k:value[k] for k in ("external_url", "owner_review", "sha256") if k in value})

    return bp
