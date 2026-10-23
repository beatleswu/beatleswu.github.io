"""G/D integration seam. Default flags are OFF; no automatic migrations."""
from html import escape
from pathlib import Path

from .http import create_blueprint
from .service import CourseError


def install_course_v1(app):
    if app.config.get("G066_COURSE_RUNTIME_ENABLED", False) is not True:
        return False
    if app.config.get("G066_COURSE_OWNER_APPROVED", False) is not True:
        raise RuntimeError("G066 Owner Gate required")
    adapters = app.config["G066_COURSE_ADAPTERS"]
    service = adapters["service"]
    if service.enabled is not True:
        raise RuntimeError("G066 service flag OFF")
    app.register_blueprint(create_blueprint(service,
        **{k:adapters[k] for k in ("current_user", "csrf_valid", "presenter", "media")}))
    from flask import Response, send_from_directory, jsonify
    ui = Path(__file__).with_name("ui")

    def asset(name="index.html"):
        try:
            service._guard(adapters["current_user"]())
        except CourseError as error:
            return jsonify(error=error.code), error.status
        if name not in {"index.html", "course.css", "course.js", "curriculum-embed.js"}:
            return jsonify(error="not_found"), 404
        if name == "index.html":
            html = (ui / name).read_text(encoding="utf-8")
            html = html.replace('<meta charset="utf-8">', '<meta charset="utf-8"><meta name="course-csrf" content="' + escape(adapters["csrf_token"](), quote=True) + '">')
            response = Response(html, mimetype="text/html")
        else:
            response = send_from_directory(ui, name)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response
    app.add_url_rule("/course-v1/", "g066_course_page", asset)
    app.add_url_rule("/course-v1/<name>", "g066_course_asset", asset)
    return True
