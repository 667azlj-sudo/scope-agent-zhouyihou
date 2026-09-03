# -*- coding: utf-8 -*-
"""
sms.py —— 短信发送（阿里云短信）

密钥从环境变量读取，方便本地开发与部署分开管理：
  ALIYUN_AK_ID        阿里云 AccessKeyId
  ALIYUN_AK_SECRET    阿里云 AccessKeySecret
  ALIYUN_SIGN_NAME    短信签名（已审核通过）
  ALIYUN_TEMPLATE_CODE 验证码模板 Code（模板内容需含 ${code}）

未配置完整密钥时自动退回「模拟模式」：不真正发短信，只在日志打印验证码，
并在接口里把验证码返回给前端，方便本地联调。上线前填好环境变量即自动切真实发送。
"""
import base64
import hashlib
import hmac
import os
import time
import uuid
import urllib.parse

import httpx

ALIYUN_ENDPOINT = "https://dysmsapi.aliyuncs.com/"


def _env(name):
    return (os.environ.get(name) or "").strip()


def configured():
    """是否已配置完整阿里云短信密钥"""
    return all([
        _env("ALIYUN_AK_ID"),
        _env("ALIYUN_AK_SECRET"),
        _env("ALIYUN_SIGN_NAME"),
        _env("ALIYUN_TEMPLATE_CODE"),
    ])


def _percent_encode(s):
    return urllib.parse.quote(str(s), safe="~")


def _build_signature(params, access_key_secret):
    """阿里云 RPC 签名：对排序后的参数做 HMAC-SHA1 + base64"""
    sorted_keys = sorted(params.keys())
    canonical = "&".join(
        f"{_percent_encode(k)}={_percent_encode(params[k])}" for k in sorted_keys
    )
    string_to_sign = "GET&%2F&" + _percent_encode(canonical)
    h = hmac.new(
        (access_key_secret + "&").encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    )
    return base64.b64encode(h.digest()).decode("utf-8")


def send_sms(phone, code):
    """发送验证码短信。返回 (ok: bool, mock: bool, msg: str)。

    未配置密钥时走模拟模式，验证码会打印到后端日志（供本地联调）。
    """
    if not configured():
        # 模拟模式：不真正外发，只打印
        print(f"[SMS][mock] 发送验证码到 {phone}: {code}")
        return True, True, "模拟模式：验证码已生成"

    params = {
        "AccessKeyId": _env("ALIYUN_AK_ID"),
        "Action": "SendSms",
        "Format": "JSON",
        "PhoneNumbers": phone,
        "RegionId": "cn-hangzhou",
        "SignName": _env("ALIYUN_SIGN_NAME"),
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "TemplateCode": _env("ALIYUN_TEMPLATE_CODE"),
        "TemplateParam": f'{{"code":"{code}"}}',
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "Version": "2017-05-25",
    }
    params["Signature"] = _build_signature(params, _env("ALIYUN_AK_SECRET"))

    try:
        resp = httpx.get(ALIYUN_ENDPOINT, params=params, timeout=10.0)
        data = resp.json()
        if data.get("Code") == "OK":
            return True, False, "短信已发送"
        return False, False, f"短信发送失败：{data.get('Message', data.get('Code'))}"
    except Exception as e:  # noqa: BLE001
        return False, False, f"短信服务异常：{e}"


if __name__ == "__main__":
    # 本地联调：python sms.py
    print("configured:", configured())
    ok, mock, msg = send_sms("13800000000", "123456")
    print(ok, mock, msg)
