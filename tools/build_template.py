#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 QD（签到盒）可导入的「有道云笔记 每日签到」模板，并做离线校验。

输出格式：QD 内部 tpl 数组格式（与 qd-today/templates 社区模板库里的 .har 完全一致）。
QD 的「我的模板 → + → 上传 HAR」同时支持该格式与标准 HAR 格式。

用法：
    python tools/build_template.py
渲染校验需要 jinja2（可选，没有也能生成模板，只是跳过渲染校验）。
"""
import json
import os
import re
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
OUT = os.path.join(PROJECT, "有道云笔记签到.har")

# 渲染校验需要 jinja2；没有也不影响生成模板，只是跳过渲染校验那一步。
# 若把 jinja2 离线解压在 tools/pylibs 或 _research/pylibs，会自动挂上，免安装。
for _cand in (os.path.join(PROJECT, "tools", "pylibs"), os.path.join(PROJECT, "_research", "pylibs")):
    if os.path.isdir(_cand) and _cand not in sys.path:
        sys.path.insert(0, _cand)

HOST = "https://note.youdao.com"
UA_ANDROID = "ynote-android"
UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) ynote-desktop/1.2.2 Chrome/87.0.4280.141 "
    "Electron/11.4.10 Safari/537.36"
)
FORM = "application/x-www-form-urlencoded"

# 判成功/失败用的断言片段。
# 200 判成功；AUTHENTICATION_FAILURE 是实测（无有效 Cookie 请求接口）得到的响应特征：
#   {"canTryAgain":false,"scope":"SECURITY","error":"207",
#    "message":"Message[AUTHENTICATION_FAILURE]: User token must be authenticated."}
OK = {"re": "200", "from": "status"}
GOT_SPACE = {"re": r'"space"|"total"', "from": "content"}
AUTH_FAIL = {"re": "AUTHENTICATION_FAILURE", "from": "content"}


def num(var):
    """jinja 表达式片段：把提取到的字节数字安全转成整数（未提取到时为 0）。"""
    return "(%s|default(0)|int)" % var


def mb(var):
    """完整的 jinja 表达式：字节 → MB（保留 2 位小数）。"""
    return "{{ (%s / 1048576)|round(2) }}" % num(var)


def mb_sum(vars_):
    return "{{ ((%s) / 1048576)|round(2) }}" % " + ".join(num(v) for v in vars_)


def headers(ua=UA_ANDROID, accept=None):
    hs = [
        {"name": "Cookie", "value": "{{cookie}}"},
        {"name": "User-Agent", "value": ua},
        {"name": "Content-Type", "value": FORM},
    ]
    if accept:
        hs.append({"name": "Accept", "value": accept})
    return hs


def entry(comment, method, url, hdrs, data="", mime=None, success=None, failed=None, extract=None):
    request = {"method": method, "url": url, "headers": hdrs, "cookies": [], "data": data}
    if mime:
        request["mimeType"] = mime
    return {
        "comment": comment,
        "request": request,
        "rule": {
            "success_asserts": [] if success is None else success,
            "failed_asserts": [] if failed is None else failed,
            "extract_variables": [] if extract is None else extract,
        },
    }


def build_log_url():
    """把人类可读的日志文本转成 api://util/string/replace 的 URL。

    静态文字（含中文）必须预先百分号编码；jinja 表达式渲染出来只有数字和小数点，本身 URL 安全。
    """
    text = (
        "有道云笔记签到｜安卓登录奖励 {rewardSpace_M} MB｜安卓签到 {anspace_M} MB｜"
        "视频广告 {adspace_M} MB｜Windows签到 {w1space_M} MB｜总空间 {capacity_M} MB"
    )
    exprs = {
        "rewardSpace_M": mb("rewardSpace"),
        "anspace_M": mb("anspace"),
        "adspace_M": mb_sum(["adspace1", "adspace2", "adspace3"]),
        "w1space_M": mb("w1space"),
        "capacity_M": mb("capacity"),
    }
    parts = []
    for chunk in re.split(r"\{(\w+)\}", text):
        if chunk in exprs:
            parts.append(exprs[chunk])
        elif chunk:
            parts.append(urllib.parse.quote(chunk, safe=""))
    return "api://util/string/replace?r=text&p=&s=&t=" + "".join(parts)


def windows_url(method):
    """Windows 客户端接口。cstk 从 Cookie 里提取；注意这里绝不能对字符串调用 .format()，
    否则 jinja 的 {{ }} 会被当成格式化占位符吃掉。"""
    return (
        HOST
        + "/yws/mapi/user?method="
        + method
        + "&device_type=PC&_system=windows&_appName=ynote"
        + "&_vendor=official-website&cstk={{cstk|urlencode}}"
    )


# p 参数同时兼容「QD 会 / 不会 对 query 做百分号解码」两种情况：
#   解码后 -> (YNOTE_CSTK=[0-9a-zA-Z]*)；不解码 -> (YNOTE_CSTK%3D[0-9a-zA-Z]*)。
# 用 * 而不是 +，因为 + 在 query 里会被解码成空格。
CSTK_PATTERN = "api://util/regex?p=(YNOTE_CSTK%3D[0-9a-zA-Z]*|YNOTE_CSTK=[0-9a-zA-Z]*)&data={{cookie|urlencode}}"


def build():
    items = []

    # 1. 会话保活：拿返回的 Set-Cookie 在本次运行内续期（QD 会把新 Cookie 用在后续请求上）。
    #    故意不写断言：这一步失败不该让整个任务变红。
    items.append(
        entry(
            "会话保活 getsess（失败不影响后续）",
            "GET",
            HOST + "/login/acc/pe/getsess?product=YNOTE",
            headers(),
        )
    )

    # 2. 安卓客户端登录奖励（Cookie 失效会在这里第一个暴露出来）
    items.append(
        entry(
            "安卓客户端登录奖励 sync",
            "POST",
            HOST + "/yws/api/daupromotion?method=sync",
            headers(),
            mime=FORM,
            success=[OK],
            failed=[AUTH_FAIL],
            extract=[{"name": "rewardSpace", "re": r'"rewardSpace":(\d+)', "from": "content"}],
        )
    )

    # 3. 安卓端签到（主奖励；已签到时返回 space=0，同样算成功）
    items.append(
        entry(
            "安卓端签到 checkin",
            "POST",
            HOST + "/yws/mapi/user?method=checkin&_system=android",
            headers(),
            mime=FORM,
            success=[GOT_SPACE],
            failed=[AUTH_FAIL],
            extract=[{"name": "anspace", "re": r'"space":(\d+)', "from": "content"}],
        )
    )

    # 4. 看视频广告奖励（每天 3 次；没奖励或已达上限时返回 0/报错，都不算任务失败）
    for i in (1, 2, 3):
        items.append(
            entry(
                "看视频广告奖励 adRandomPrompt %d/3" % i,
                "POST",
                HOST + "/yws/mapi/user?method=adRandomPrompt",
                headers(),
                mime=FORM,
                extract=[{"name": "adspace%d" % i, "re": r'"space":(\d+)', "from": "content"}],
            )
        )

    # 5. 从 Cookie 提取 YNOTE_CSTK（Windows 端接口需要）
    items.append(
        entry(
            "从 Cookie 提取 YNOTE_CSTK",
            "GET",
            CSTK_PATTERN,
            [],
            extract=[
                {"name": "cstk", "re": r"YNOTE_CSTK=([0-9a-zA-Z]+)", "from": "content"},
                {"name": "cstk", "re": r"YNOTE_CSTK%3D([0-9a-zA-Z]+)", "from": "content"},
            ],
        )
    )

    # 6. Windows 客户端：先查状态再签到（额外奖励，尽力而为）
    win_headers = headers(UA_DESKTOP, accept="application/json, text/plain, */*")
    items.append(entry("Windows 端签到状态 getSignStatus", "POST", windows_url("getSignStatus"), win_headers, mime=FORM))
    items.append(
        entry(
            "Windows 端签到 checkin",
            "POST",
            windows_url("checkin"),
            win_headers,
            mime=FORM,
            extract=[{"name": "w1space", "re": r'"space":(\d+)', "from": "content"}],
        )
    )

    # 7. 查询当前总空间（仅用于日志）
    items.append(
        entry(
            "查询当前总空间",
            "POST",
            HOST + "/yws/mapi/user?method=get",
            headers(),
            mime=FORM,
            extract=[{"name": "capacity", "re": r'"q":"(\d+)"', "from": "content"}],
        )
    )

    # 8. 组装日志：QD 会把最后一条请求提取到的 __log__ 作为任务日志
    items.append(
        entry("生成日志", "GET", build_log_url(), [], extract=[{"name": "__log__", "re": ".+", "from": "content"}])
    )

    return items


# --------------------------------------------------------------------------- 校验

SAMPLE = {
    "cookie": (
        "YNOTE_CSTK=Ab12Cd34; YNOTE_SESS=v2|abcdefgh; YNOTE_LOGIN=1||1700000000000; "
        "JSESSIONID=ABCDEF; __yadk_uid=xyz"
    ),
    "cstk": "Ab12Cd34",
    "rewardSpace": "10485760",
    "anspace": "2097152",
    "adspace1": "1048576",
    "adspace2": "0",
    "adspace3": "524288",
    "w1space": "1048576",
    "capacity": "3221225472",
}


def qd_tpl2har(tpl):
    """复刻 libs/fetcher.py 的 Fetcher.tpl2har，验证模板能被 QD 正常转换。"""
    entries = []
    for en in tpl:
        req = en["request"]
        parsed = urllib.parse.urlparse(req["url"])
        data = req.get("data")
        item = {
            "checked": True,
            "startedDateTime": "2024-01-01T00:00:00",
            "time": 1,
            "request": {
                "method": req["method"],
                "url": req["url"],
                "httpVersion": "HTTP/1.1",
                "headers": [dict(x, checked=True) for x in req.get("headers", [])],
                "queryString": [{"name": n, "value": v} for n, v in urllib.parse.parse_qsl(parsed.query)],
                "cookies": [dict(x, checked=True) for x in req.get("cookies", [])],
                "headersSize": -1,
                "bodySize": len(data) if data else 0,
            },
            "response": {},
            "cache": {},
            "timings": {},
            "success_asserts": en["rule"]["success_asserts"],
            "failed_asserts": en["rule"]["failed_asserts"],
            "extract_variables": en["rule"]["extract_variables"],
        }
        if data:
            item["request"]["postData"] = dict(mimeType=req.get("mimeType"), text=data)
        entries.append(item)
    return {"log": dict(creator=dict(name="binux", version="QD"), entries=entries, pages=[], version="1.2")}


def validate(tpl):
    problems = []

    for i, en in enumerate(tpl, 1):
        req, rule = en["request"], en["rule"]
        if req["method"] not in ("GET", "POST"):
            problems.append("第 %d 条: 方法异常 %s" % (i, req["method"]))
        if not req["url"]:
            problems.append("第 %d 条: url 为空" % i)
        if req["method"] == "POST" and req.get("mimeType") != FORM and not req["url"].startswith("api://"):
            problems.append("第 %d 条: POST 缺少 mimeType" % i)
        for key in ("success_asserts", "failed_asserts", "extract_variables"):
            for r in rule[key]:
                try:
                    re.compile(r["re"])
                except re.error as e:
                    problems.append("第 %d 条 %s 正则非法: %s" % (i, key, e))
                if r["from"] not in ("content", "status", "header") and not r["from"].startswith("header-"):
                    problems.append("第 %d 条 %s 的 from 不合法: %s" % (i, key, r["from"]))

    har = qd_tpl2har(tpl)
    if len(har["log"]["entries"]) != len(tpl):
        problems.append("tpl2har 条目数不一致")

    try:
        from jinja2 import meta
        from jinja2.sandbox import SandboxedEnvironment
    except ImportError:
        print("[skip] 本机没有 jinja2，跳过渲染校验")
        return problems, har

    env = SandboxedEnvironment()
    declared = sorted(meta.find_undeclared_variables(env.parse(json.dumps(tpl, ensure_ascii=False))))
    print("模板变量（QD 自动推导；建任务时只有 cookie 需要填）:")
    print("   ", declared)

    def render(i, where, raw, check_space=False):
        if not raw:
            return None
        try:
            out = env.from_string(raw).render(**SAMPLE)
        except Exception as e:  # noqa: BLE001
            problems.append("第 %d 条 %s 渲染失败: %r" % (i, where, e))
            return None
        if "{" in out or "}" in out:
            problems.append("第 %d 条 %s 渲染后仍含花括号（jinja 未解析或 .format 吃掉）: %s" % (i, where, out[:120]))
        if check_space and " " in out:
            problems.append("第 %d 条 %s 渲染后含空格: %s" % (i, where, out[:120]))
        return out

    for i, en in enumerate(tpl, 1):
        req = en["request"]
        render(i, "url", req["url"], check_space=True)
        render(i, "data", req.get("data"), check_space=True)
        for h in req.get("headers", []):
            out = render(i, "header " + h["name"], h["value"])
            if h["name"].lower() == "cookie" and out and "YNOTE_CSTK" not in out:
                problems.append("第 %d 条 Cookie 头渲染异常" % i)

    rendered = env.from_string(tpl[-1]["request"]["url"]).render(**SAMPLE)
    t_value = urllib.parse.parse_qs(urllib.parse.urlparse(rendered).query).get("t", [""])[0]
    print("渲染出的任务日志:")
    print("   ", t_value)
    if "MB" not in t_value:
        problems.append("日志文本异常")

    # 断言覆盖情况：必须至少有一条请求在 Cookie 失效时会失败
    guards = [en for en in tpl if any(r["from"] == "content" and "AUTHENTICATION" in r["re"] for r in en["rule"]["failed_asserts"])]
    if not guards:
        problems.append("没有任何请求会在 Cookie 失效时报错")
    print("会在 Cookie 失效时报错的请求数:", len(guards))

    # 至少一条请求带 __log__
    if not any(r["name"] == "__log__" for en in tpl for r in en["rule"]["extract_variables"]):
        problems.append("没有设置 __log__，任务将没有日志")

    return problems, har


def main():
    tpl = build()
    problems, har = validate(tpl)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(tpl, f, ensure_ascii=False, indent=2)
    with open(OUT, encoding="utf-8") as f:
        json.load(f)
    print("\n已写出:", OUT)
    print("条目数:", len(tpl), "| JSON 校验通过 | tpl2har 校验通过（%d 条）" % len(har["log"]["entries"]))

    if problems:
        print("\n发现问题:")
        for p in problems:
            print("   -", p)
        raise SystemExit(1)
    print("全部校验通过")


if __name__ == "__main__":
    main()
