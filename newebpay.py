# -*- coding: utf-8 -*-
"""藍新金流（NewebPay）定期定額 API 封裝。

文件依據：藍新「信用卡定期定額技術串接手冊」NDNP-1.0.5
- 建立委託：POST {base}/MPG/period（幕前，自動送出表單）
- 每期授權通知：NotifyURL 收到 Period=AES(JSON)
- 委託狀態修改（終止/暫停/重啟）：POST {base}/MPG/period/AlterStatus

金鑰一律由環境變數提供（伺服器 /opt/go-odyssey/.env）：
  NEWEBPAY_MERCHANT_ID / NEWEBPAY_HASH_KEY / NEWEBPAY_HASH_IV
  NEWEBPAY_TEST=1 → 測試環境 ccore.newebpay.com（預設）；0 → 正式 core.newebpay.com
"""
import os
import json
import time
import urllib.parse
import urllib.request

from Crypto.Cipher import AES  # pycryptodome

MERCHANT_ID = os.environ.get('NEWEBPAY_MERCHANT_ID', '')
HASH_KEY    = os.environ.get('NEWEBPAY_HASH_KEY', '')
HASH_IV     = os.environ.get('NEWEBPAY_HASH_IV', '')
IS_TEST     = os.environ.get('NEWEBPAY_TEST', '1') != '0'

BASE_URL = 'https://ccore.newebpay.com' if IS_TEST else 'https://core.newebpay.com'
PERIOD_URL      = f'{BASE_URL}/MPG/period'
ALTERSTATUS_URL = f'{BASE_URL}/MPG/period/AlterStatus'


def is_configured():
    return bool(MERCHANT_ID and HASH_KEY and HASH_IV)


# ── AES-256-CBC（PKCS7）─────────────────────────────────────────

def _pkcs7_pad(data: bytes) -> bytes:
    pad = 32 - (len(data) % 32)
    return data + bytes([pad]) * pad


def _pkcs7_unpad(data: bytes) -> bytes:
    pad = data[-1]
    if 1 <= pad <= 32:
        return data[:-pad]
    return data


def aes_encrypt(plain: str) -> str:
    """加密為 hex 字串（藍新 PostData_ 格式）。"""
    cipher = AES.new(HASH_KEY.encode(), AES.MODE_CBC, HASH_IV.encode())
    return cipher.encrypt(_pkcs7_pad(plain.encode('utf-8'))).hex()


def aes_decrypt(hexdata: str) -> str:
    cipher = AES.new(HASH_KEY.encode(), AES.MODE_CBC, HASH_IV.encode())
    raw = cipher.decrypt(bytes.fromhex(hexdata.strip()))
    return _pkcs7_unpad(raw).decode('utf-8', errors='replace')


# ── 定期定額：建立委託 ───────────────────────────────────────────

def build_period_form(*, mer_order_no: str, amount: int, period_type: str,
                      period_point: str, period_times: int, prod_desc: str,
                      payer_email: str, notify_url: str, return_url: str,
                      back_url: str = '') -> dict:
    """產生建立委託所需的自動送出表單資料。

    period_type: 'M'（每月）或 'Y'（每年）
    period_point: M → '01'~'31'；Y → 'MMDD'
    回傳 {action, fields}，前端組 <form> 自動 POST。
    """
    params = {
        'RespondType':     'JSON',
        'TimeStamp':       str(int(time.time())),
        'Version':         '1.5',
        'LangType':        'zh-Tw',
        'MerOrderNo':      mer_order_no,
        'ProdDesc':        prod_desc,
        'PeriodAmt':       str(int(amount)),
        'PeriodType':      period_type,
        'PeriodPoint':     period_point,
        'PeriodStartType': '2',   # 立即執行委託金額授權（第一期當下扣款）
        'PeriodTimes':     str(int(period_times)),
        'PayerEmail':      payer_email,
        'EmailModify':     '0',
        'PaymentInfo':     'N',
        'OrderInfo':       'N',
        'NotifyURL':       notify_url,
        'ReturnURL':       return_url,
    }
    if back_url:
        params['BackURL'] = back_url
    post_data = aes_encrypt(urllib.parse.urlencode(params))
    return {
        'action': PERIOD_URL,
        'fields': {
            'MerchantID_': MERCHANT_ID,
            'PostData_':   post_data,
        },
    }


# ── 通知解密 ────────────────────────────────────────────────────

def decrypt_period_response(period_hex: str) -> dict:
    """解密 NotifyURL / ReturnURL 的 Period 參數。

    回傳藍新 JSON dict：{'Status': 'SUCCESS', 'Message': ..., 'Result': {...}}
    解析失敗丟 ValueError。
    """
    plain = aes_decrypt(period_hex)
    try:
        return json.loads(plain)
    except json.JSONDecodeError:
        # 部分版本以 query string 回傳
        parsed = urllib.parse.parse_qs(plain)
        if parsed:
            return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
        raise ValueError(f'無法解析 Period 內容: {plain[:200]}')


# ── 委託狀態修改（終止續扣）─────────────────────────────────────

def alter_period_status(*, mer_order_no: str, period_no: str,
                        alter_type: str = 'terminate') -> dict:
    """終止（terminate）/ 暫停（suspend）/ 重啟（restart）委託。

    回傳藍新回應 dict（period 欄位已解密）。失敗丟 RuntimeError。
    """
    params = {
        'RespondType': 'JSON',
        'Version':     '1.0',
        'TimeStamp':   str(int(time.time())),
        'MerOrderNo':  mer_order_no,
        'PeriodNo':    period_no,
        'AlterType':   alter_type,
    }
    body = urllib.parse.urlencode({
        'MerchantID_': MERCHANT_ID,
        'PostData_':   aes_encrypt(urllib.parse.urlencode(params)),
    }).encode()
    req = urllib.request.Request(
        ALTERSTATUS_URL, data=body, method='POST',
        headers={'Content-Type': 'application/x-www-form-urlencoded',
                 # 藍新 WAF 會擋無 User-Agent 的請求（403）
                 'User-Agent': 'Mozilla/5.0 (GoOdyssey Server)'})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode('utf-8', errors='replace')
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f'AlterStatus 回應非 JSON: {raw[:300]}')
    # period 欄位為加密內容 → 解密後取代
    enc = data.get('period') or data.get('Period')
    if isinstance(enc, str) and enc:
        try:
            data['period_decrypted'] = decrypt_period_response(enc)
        except Exception:
            data['period_decrypted'] = None
    return data
