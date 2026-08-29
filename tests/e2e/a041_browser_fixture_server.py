"""Disposable same-origin fixture server for A041 browser evidence.

Serves candidate static files plus deterministic server-owned read models. It
never imports app.py, opens a database, or writes repository data.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
REQUESTS: list[dict[str, object]] = []
ICON = "/assets/hero/equipment/functional/"


def item(inv_id, item_id, slot, name, name_en, label, label_en, value, icon, equipped):
    return {
        "inv_id": inv_id, "inventory_id": inv_id, "item_id": item_id, "id": item_id,
        "slot": slot, "name": name, "name_en": name_en,
        "display_name": name, "display_name_en": name_en, "rarity": "common",
        "icon": ICON + icon, "icon_alt": name_en, "owned_quantity": 1,
        "owned": True, "equipped": equipped, "functional_equipment": True,
        "active_effect_details": ([{
            "key": "fixture_" + item_id, "label": label, "label_en": label_en,
            "value_label": value, "value_label_en": value,
        }] if equipped else []),
        "unsupported_effects": [],
        "comparison_summary": {"state": "CURRENTLY_EQUIPPED" if equipped else "BASELINE"},
        "where_to_obtain": "測試伺服器裝備快照",
        "where_to_obtain_en": "Fixture server equipment snapshot",
        "source": "a041-browser-fixture",
    }


EQUIPMENT = [
    item(101, "wooden_sword", "weapon", "木劍", "Wooden Sword", "攻擊", "Attack", "+4", "wooden_sword.svg", True),
    item(102, "cloth_robe", "armor", "粗布衣", "Cloth Robe", "傷害減免", "Damage reduction", "0%", "cloth_robe.svg", True),
    item(103, "lucky_stone", "accessory", "幸運石", "Lucky Stone", "掉落加成", "Drop bonus", "+1%", "lucky_stone.svg", True),
    item(104, "iron_sword", "weapon", "鐵劍", "Iron Sword", "攻擊", "Attack", "+10", "iron_sword.svg", False),
]
WARDROBE = [{
    "id": "fixture_fox_style", "type": "outfit", "name": "狐影外觀",
    "name_en": "Fox Style Cosmetic", "owned": True, "equipped": True,
    "effects": {}, "color": "#7c3aed", "art": "/assets/hero/items/robe_fox.svg",
}]


def payload(path: str):
    if path == "/api/auth/me":
        return {"logged_in": True, "user_id": 41041, "username": "a041-browser",
                "nickname": "A041 Browser", "display_name": "A041 Browser",
                "go_rank": "20k", "is_premium": False, "tour_done": True}
    if path == "/api/player/presentation":
        return {"contract_version": "PLAYER_PRESENTATION_API_V1", "projection_status": "OK",
                "hero": {"hero_id": "apprentice"},
                "progression": {"xp": 40, "level": 2, "rank_level": "2", "go_rank": "20k"},
                "display_identity": {"display_name": "A041 Browser", "username": "a041-browser"}}
    if path == "/api/player/appearance":
        return {"character_key": "apprentice", "wardrobe": WARDROBE,
                "equipped": {"outfit_id": "fixture_fox_style"},
                "combat_armor": "cloth", "combat_weapon": "none", "combat_cape": "none",
                "combat_offhand": "none", "combat_hat": "none", "combat_pet": "none",
                "combat_aura": "none", "combat_acc": "none"}
    if path == "/api/player/inventory":
        return EQUIPMENT
    if path == "/api/skills/profile":
        return {"display_name": "A041 Browser", "username": "a041-browser",
                "nickname": "A041 Browser", "character_key": "apprentice", "rank_level": 2,
                "go_rank": "20k", "xp": 40, "xp_next": 100, "total_xp": 40,
                "wardrobe": WARDROBE, "functional_equipment": EQUIPMENT,
                "combat_stats": {"attack_bonus_pct": 5, "damage_reduction_pct": 0,
                                  "crit_multiplier": 1, "counter_negated": False,
                                  "combo_multiplier_double": False},
                "active_effects": {"xp_bonus": 0, "drop_bonus": 0}}
    if path == "/api/pet/status": return {"pet": None, "inventory": []}
    if path in ("/api/badges/definitions", "/api/badges/earned", "/api/srs/all", "/api/questions"): return []
    if path == "/api/user/coins": return {"coins": 0}
    if path == "/api/dm/unread_count": return {"count": 0}
    if path == "/api/class/profile": return {}
    if path == "/api/subscription/status": return {"is_premium": False, "remaining": 20, "daily_limit": 20}
    if path == "/api/curriculum/summary": return {"units": [], "cardsCount": 0}
    if path == "/api/quest-board": return {"accepted": [], "claimable": [], "open_quests": [], "quest_meta": [], "coins": 0, "xp": 0}
    if path == "/api/quests/today": return {"quests": []}
    if path in ("/api/stats/dashboard", "/api/stats/summary"): return {}
    if path == "/api/xp/status": return {"remaining": 20, "daily_limit": 20}
    if path == "/api/adventure/bootstrap": return {"zones": [], "progress": {}, "selected_zone": None}
    if path == "/api/monster/status": return {"active": False}
    if path == "/api/shop/catalog": return {"items": [], "inventory": {}}
    return {}


def encoded(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "A041Fixture/1.0"

    def log_message(self, *_args):
        return

    def _record(self, status, path):
        REQUESTS.append({"method": self.command, "path": path, "status": status})

    def _send(self, status, kind, body):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionAbortedError):
                pass

    def do_HEAD(self):  # noqa: N802
        self.serve(head_only=True)

    def do_GET(self):  # noqa: N802
        self.serve(head_only=False)

    def do_POST(self):  # noqa: N802
        path = urlsplit(self.path).path
        self._record(200, path)
        self._send(200, "application/json; charset=utf-8", encoded({"ok": True}))

    def serve(self, head_only=False):
        path = urlsplit(self.path).path
        if path.startswith("/__a041/seed-"):
            seeds = {
                "/__a041/seed-stale-cache": '{"character":"mage","armor":"old_armor","weapon":"old_weapon","offhand":"old_offhand","hat":"old_hat","cape":"old_cape","pet":"old_pet","aura":"old_aura","acc":"old_acc"}',
                "/__a041/seed-corrupt-cache": "{not-json",
                "/__a041/seed-unowned-cache": '{"character":"unknown","weapon":"unowned_item","armor":"unknown_armor","acc":"unknown_accessory"}',
            }
            body = ("<script>localStorage.setItem('hero_combat_gear_v1', "
                    + json.dumps(seeds.get(path, seeds["/__a041/seed-corrupt-cache"]))
                    + ");</script>").encode("utf-8")
            self._record(200, path)
            self._send(200, "text/html; charset=utf-8", body)
            return
        if path.startswith("/socket.io/"):
            self._record(200, path)
            self._send(200, "application/javascript; charset=utf-8", b"")
            return
        if path == "/favicon.ico":
            self._record(200, path)
            self._send(200, "image/x-icon", b"")
            return
        if path == "/__a041/requests":
            body = encoded(REQUESTS)
            self._record(200, path)
            self._send(200, "application/json; charset=utf-8", body)
            return
        if path.startswith("/api/"):
            body = encoded(payload(path))
            self._record(200, path)
            self._send(200, "application/json; charset=utf-8", body)
            return
        route_map = {"/hero": "hero.html", "/inventory": "inventory.html", "/curriculum": "curriculum.html", "/bot": "bot.html", "/landing": "landing.html", "/": "index.html"}
        relative = route_map.get(path, path.lstrip("/"))
        candidate = (ROOT / relative).resolve()
        try: candidate.relative_to(ROOT)
        except ValueError: candidate = ROOT / "index.html"
        if not candidate.is_file():
            self._record(404, path)
            self._send(404, "text/plain; charset=utf-8", b"not found")
            return
        self._record(200, path)
        self._send(200, mimetypes.guess_type(candidate.name)[0] or "application/octet-stream", candidate.read_bytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"A041_FIXTURE_PORT={server.server_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
