# -*- coding: utf-8 -*-
"""
e2e_smoke.py —— 端到端鉴权/越权冒烟测试

用法：
  1. 启动后端（mock 短信模式，即未配置阿里云密钥）：
     py -m uvicorn app:app --host 127.0.0.1 --port 8000
  2. 另开终端运行：
     py e2e_smoke.py

覆盖：401 拦截、注册/登录、token 鉴权、个人画像、IDOR（员工读不到经理画像）、
     经理专属接口 403。
"""
import httpx

BASE = "http://127.0.0.1:8000"
fails = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL") + "  " + name + (("  " + extra) if extra else ""))
    if not cond:
        fails.append(name)


def main():
    # 1. 未登录访问受保护接口 → 401
    r = httpx.get(BASE + "/api/users")
    check("未登录访问 /api/users 返回 401", r.status_code == 401, f"status={r.status_code}")

    # 2. 注册负责人（mock 短信返回 code）
    r = httpx.post(BASE + "/api/sms/send", json={"phone": "13800000001"}).json()
    if not r.get("mock"):
        print("SKIP：未处于 mock 短信模式，无法自动注册（请勿配置阿里云密钥）")
        return 1 if fails else 0
    code = r.get("code")
    reg = httpx.post(BASE + "/api/register", json={
        "name": "e2e经理", "password": "pw123", "role": "manager",
        "phone": "13800000001", "code": code, "company_name": "e2e公司", "position": "负责人",
    }).json()
    check("注册负责人", reg.get("ok") is True, str(reg.get("msg")))

    # 3. 登录拿 token
    lg = httpx.post(BASE + "/api/login", json={"account": "e2e经理", "password": "pw123"}).json()
    check("经理登录", lg.get("ok") is True)
    mtoken = lg.get("token")
    mgr = lg.get("user") or {}
    mh = {"Authorization": "Bearer " + mtoken}

    # 4. 带 token 访问 → 200
    r = httpx.get(BASE + "/api/users", headers=mh)
    check("经理带 token 访问 /api/users 返回 200", r.status_code == 200, f"status={r.status_code}")

    # 5. 设置并读取本人画像
    r = httpx.post(f"{BASE}/api/profile/{mgr['id']}", json={"info": "我是负责人", "habits": "早起"}, headers=mh)
    check("设置画像", r.json().get("ok") is True)
    r = httpx.get(f"{BASE}/api/profile/{mgr['id']}", headers=mh)
    check("读取画像", r.json().get("profile", {}).get("info") == "我是负责人")

    # 6. 注册员工（凭邀请码）
    comp = httpx.get(f"{BASE}/api/companies/{mgr['company_id']}", headers=mh).json()
    invite = comp.get("company", {}).get("invite_code")
    if not invite:
        print("SKIP：拿不到公司邀请码，跳过员工/越权部分")
        return 1 if fails else 0
    r = httpx.post(BASE + "/api/sms/send", json={"phone": "13800000002"}).json()
    ecode = r.get("code")
    ereg = httpx.post(BASE + "/api/register", json={
        "name": "e2e员工", "password": "pw123", "role": "employee",
        "phone": "13800000002", "code": ecode, "invite_code": invite, "position": "员工",
    }).json()
    check("注册员工", ereg.get("ok") is True, str(ereg.get("msg")))
    elg = httpx.post(BASE + "/api/login", json={"account": "e2e员工", "password": "pw123"}).json()
    etoken = elg.get("token")
    eh = {"Authorization": "Bearer " + etoken}

    # 7. IDOR：员工读经理画像 → 应返回员工自己的（info 为空），而非经理的
    r = httpx.get(f"{BASE}/api/profile/{mgr['id']}", headers=eh)
    pinfo = r.json().get("profile", {}).get("info")
    check("IDOR：员工读经理画像被强制为本人", pinfo != "我是负责人", f"info={pinfo!r}")

    # 8. 员工访问经理专属接口 → 403
    r = httpx.get(BASE + "/api/payouts", headers=eh)
    check("员工访问 /api/payouts 返回 403", r.status_code == 403, f"status={r.status_code}")

    print("\n" + ("ALL PASS" if not fails else "FAILED: " + str(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
