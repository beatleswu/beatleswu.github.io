"""F-safe semantic successor checks; no live accounts or browser acceptance."""
import json
import subprocess
from pathlib import Path

from test_g008_fresh_e_character_authority import authority_env
from future30_character_service import grant_future30_character

ROOT = Path(__file__).resolve().parents[1]


def test_current_modules_projection_lifecycle_outfit_and_inline_syntax():
    result = subprocess.run(
        ['node', 'tests/e2e/run_f_g009_post_g008_semantic_rebase.mjs'],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report['result'] == 'PASS'
    assert report['logicalProjectionCases'] == 30
    assert report['visualMappingAndHashCases'] == 33


def test_apply_refresh_preserves_legacy_outfit_rows_and_unknown_unentitled_state(authority_env):
    database, client_for = authority_env
    with database() as conn:
        conn.execute("UPDATE player_appearance SET outfit_id='legacy-outfit' WHERE user_id=1")
        conn.execute("INSERT INTO player_wardrobe VALUES(1,'legacy-outfit','before','legacy')")
        grant_future30_character(conn, 1, 'A1', 'ACCEPTANCE_TEST', environment='test',
                                 allow_acceptance_test=True, source_reference='f-isolated-regression')
    client = client_for()
    assert client.post('/api/skills/character', json={'character_key': 'A1'}).status_code == 200
    for reader in (client, client_for()):
        payload = reader.get('/api/player/appearance').get_json()
        assert payload['character_key'] == 'A1'
        assert payload['character_entitled'] is True
        assert payload['equipped']['outfit_id'] == 'legacy-outfit'
    with database() as conn:
        before = tuple(conn.execute('SELECT * FROM player_appearance WHERE user_id=1').fetchone())
    for key, status in [('A31', 400), ('A3', 403)]:
        assert client.post('/api/skills/character', json={'character_key': key}).status_code == status
        with database() as conn:
            assert tuple(conn.execute('SELECT * FROM player_appearance WHERE user_id=1').fetchone()) == before
            assert tuple(conn.execute('SELECT * FROM player_wardrobe').fetchone()) == (1, 'legacy-outfit', 'before', 'legacy')


def test_no_parallel_hero_host_or_server_authority_is_introduced():
    renderer = (ROOT / 'js/g008_future30_hero_renderer.js').read_text(encoding='utf-8')
    assert renderer.count('new THREE.WebGLRenderer(') == 1
    assert 'player_appearance.character_key' in renderer
    assert 'entry.owned !== true' in renderer
    assert 'entry.acquisition_source !== "ACCEPTANCE_TEST"' in renderer
    assert 'mountP048Preview' not in renderer
    assert 'filename' not in renderer
    assert 'export function destroyHeroAppearance()' in renderer
    shop = (ROOT / 'shop.html').read_text(encoding='utf-8')
    assert "isEn() ? 'All eligible cosmetics are owned' : '所有可選外觀皆已擁有'" in shop
    assert "isEn() ? 'No eligible cosmetics are available' : '目前沒有符合資格的外觀'" in shop
