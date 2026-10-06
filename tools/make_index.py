#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 QD（签到盒）第三方模板库索引 tpls_history.json。

QD 的「公共模板库 / 第三方库」要求仓库根目录有这个文件，格式见
https://github.com/qd-today/templates 的 README。改动模板后重新跑一次即可。

用法：python tools/make_index.py
"""
import base64
import datetime
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "CanM120/QD"
BRANCH = "main"
AUTHOR = "CanM120"

TEMPLATES = [
    {
        "name": "有道云笔记签到",
        "filename": "有道云笔记签到.har",
        "comments": (
            "只需填 cookie 变量（浏览器登录 note.youdao.com/web/ 后从请求头复制整行 Cookie，"
            "至少含 YNOTE_CSTK、YNOTE_LOGIN、YNOTE_SESS）。"
            "包含：安卓客户端登录奖励、安卓端签到、看视频广告奖励×3、Windows 端签到、任务日志。"
            "Cookie 失效时任务会报 AUTHENTICATION_FAILURE，重新抓一次即可（约 20 天有效期）。"
        ),
    },
]


def main():
    now = datetime.datetime.now()
    version = now.strftime("%Y%m%d")
    date = now.strftime("%Y-%m-%d %H:%M:%S")

    har = {}
    for tpl in TEMPLATES:
        path = os.path.join(ROOT, tpl["filename"])
        if not os.path.exists(path):
            raise SystemExit("找不到模板文件: " + path)
        with open(path, "rb") as f:
            raw = f.read()
        # 校验一下确实是合法 JSON（QD 内部 tpl 数组格式）
        json.loads(raw.decode("utf-8"))
        har[tpl["name"]] = {
            "name": tpl["name"],
            "author": AUTHOR,
            "url": "https://raw.githubusercontent.com/%s/%s/%s" % (REPO, BRANCH, tpl["filename"]),
            "update": False,
            "comments": tpl["comments"],
            "filename": tpl["filename"],
            "content": base64.b64encode(raw).decode("ascii"),
            "date": date,
            "version": version,
            "commenturl": "https://github.com/%s/issues" % REPO,
        }

    out = {"version": version, "har": har}
    dest = os.path.join(ROOT, "tpls_history.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("已写出:", dest)
    print("版本:", version, "| 模板数:", len(har), "| 模板:", "、".join(har))


if __name__ == "__main__":
    main()
