# -*- coding: utf-8 -*-
"""PayPal Subscriptions API 封裝（Premium 訂閱，美元計價）。

流程：
- 首次：自動建立 Product + 兩個 Billing Plan（月繳 US$10 / 年繳 US$84），plan id 存 app_kv
- 訂閱：POST /v1/billing/subscriptions → 取 approval 連結讓用戶到 PayPal 核准
- 開通/續扣：webhook（或導回時主動查詢）→ 一律以 GET subscription 的即時狀態為準，
  不信任 webhook payload 內容（防偽造）；效期推進用 next_billing_time + 寬限期

金鑰由環境變數提供（伺服器 /opt/go-odyssey/.env）：
  PAYPAL_CLIENT_ID / PAYPAL_SECRET
  PAYPAL_TEST=1 → sandbox（預設）；0 → live
"""
import os
import json
import time
import base64
import urllib.request
import urllib.error
import urllib.parse

CLIENT_ID = os.environ.get('PAYPAL_CLIENT_ID', '')
SECRET    = os.environ.get('PAYPAL_SECRET', '')
IS_TEST   = os.environ.get('PAYPAL_TEST', '1') != '0'

BASE_URL = ('https://api-m.sandbox.paypal.com' if IS_TEST
            else 'https://api-m.paypal.com')

_token_cache = {'token': None, 'expires': 0}


def is_configured():
    return bool(CLIENT_ID and SECRET)


def _request(method, path, body=None, token=None, headers=None):
    url = f'{BASE_URL}{path}'
    h = {'Content-Type': 'application/json',
         'User-Agent': 'GoOdyssey/1.0'}
    if token:
        h['Authorization'] = f'Bearer {token}'
    if headers:
        h.update(headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
            return resp.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', errors='replace')
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {'error': raw[:500]}


def get_access_token():
    """Client-credentials token，快取至過期前 60 秒。"""
    now = time.time()
    if _token_cache['token'] and now < _token_cache['expires'] - 60:
        return _token_cache['token']
    auth = base64.b64encode(f'{CLIENT_ID}:{SECRET}'.encode()).decode()
    req = urllib.request.Request(
        f'{BASE_URL}/v1/oauth2/token',
        data=b'grant_type=client_credentials',
        method='POST',
        headers={'Authorization': f'Basic {auth}',
                 'Content-Type': 'application/x-www-form-urlencoded',
                 'User-Agent': 'GoOdyssey/1.0'})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode())
    _token_cache['token'] = data['access_token']
    _token_cache['expires'] = now + int(data.get('expires_in', 3600))
    return _token_cache['token']


# ── Product / Plan 建立（冪等，由呼叫端持久化 plan id）────────────

def create_product():
    token = get_access_token()
    status, data = _request('POST', '/v1/catalogs/products', {
        'name': 'Go Odyssey Premium',
        'description': 'Go Odyssey Premium membership',
        'type': 'SERVICE',
        'category': 'EDUCATIONAL_AND_TEXTBOOKS',
    }, token)
    if status not in (200, 201):
        raise RuntimeError(f'PayPal create product failed: {status} {data}')
    return data['id']


def create_plan(product_id, *, name, usd, interval_unit, interval_count=1):
    """interval_unit: 'MONTH' 或 'YEAR'。"""
    token = get_access_token()
    status, data = _request('POST', '/v1/billing/plans', {
        'product_id': product_id,
        'name': name,
        'billing_cycles': [{
            'frequency': {'interval_unit': interval_unit,
                          'interval_count': interval_count},
            'tenure_type': 'REGULAR',
            'sequence': 1,
            'total_cycles': 0,   # 0 = 無限期續訂直到取消
            'pricing_scheme': {'fixed_price': {'value': str(usd),
                                               'currency_code': 'USD'}},
        }],
        'payment_preferences': {
            'auto_bill_outstanding': True,
            'payment_failure_threshold': 2,
        },
    }, token)
    if status not in (200, 201):
        raise RuntimeError(f'PayPal create plan failed: {status} {data}')
    return data['id']


# ── 訂閱 ────────────────────────────────────────────────────────

def create_subscription(plan_id, *, custom_id, return_url, cancel_url):
    """回傳 (subscription_id, approval_url)。"""
    token = get_access_token()
    status, data = _request('POST', '/v1/billing/subscriptions', {
        'plan_id': plan_id,
        'custom_id': str(custom_id),
        'application_context': {
            'brand_name': 'Go Odyssey',
            'locale': 'en-US',
            'shipping_preference': 'NO_SHIPPING',
            'user_action': 'SUBSCRIBE_NOW',
            'return_url': return_url,
            'cancel_url': cancel_url,
        },
    }, token)
    if status not in (200, 201):
        raise RuntimeError(f'PayPal create subscription failed: {status} {data}')
    approval = next((l['href'] for l in data.get('links', [])
                     if l.get('rel') == 'approve'), '')
    return data['id'], approval


def get_subscription(sub_id):
    token = get_access_token()
    status, data = _request('GET', f'/v1/billing/subscriptions/{sub_id}',
                            None, token)
    if status != 200:
        raise RuntimeError(f'PayPal get subscription failed: {status} {data}')
    return data


def cancel_subscription(sub_id, reason='User requested cancellation'):
    token = get_access_token()
    status, data = _request(
        'POST', f'/v1/billing/subscriptions/{sub_id}/cancel',
        {'reason': reason}, token)
    if status not in (200, 204):
        raise RuntimeError(f'PayPal cancel failed: {status} {data}')
    return True
