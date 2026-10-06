#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本目录的文件通过 GitHub API 上传/更新到仓库，**不需要安装 git**。

用法（在本文件所在目录执行）：

    python upload.py                      # 会提示粘贴 GitHub Token（输入时不回显）
    python upload.py --dry-run            # 只列出将要上传的文件
    set GITHUB_TOKEN=ghp_xxx && python upload.py          # Windows
    export GITHUB_TOKEN=ghp_xxx && python upload.py       # macOS / Linux

Token 需要勾选对该仓库的 Contents 读写权限（fine-grained token 选
Repository permissions -> Contents: Read and write；classic token 选 repo 即可）。

Token 只在本机内存里使用，不会写入任何文件。
"""
import argparse
import base64
import getpass
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = "CanM120/QD"
BRANCH = "main"
API = "https://api.github.com"
ROOT = os.path.dirname(os.path.abspath(__file__))

SKIP_DIRS = {".git", "__pycache__", ".idea", ".vscode", "node_modules"}
SKIP_FILES = {"desktop.ini", "Thumbs.db", ".DS_Store"}
SKIP_SUFFIX = (".pyc", ".pyo", ".zip", ".log")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def api(method, path, token, payload=None):
    url = path if path.startswith("http") else API + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "qd-tpl-uploader")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=60) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(body)
        except Exception:  # noqa: BLE001
            pass
        return e.code, body


def collect():
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in SKIP_FILES or name.lower().endswith(SKIP_SUFFIX):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, ROOT).replace("\\", "/")
            files.append((rel, full))
    return sorted(files)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只列出文件，不真正上传")
    ap.add_argument("--message", default="", help="提交说明")
    args = ap.parse_args()

    files = collect()
    print("仓库: %s（分支 %s）" % (REPO, BRANCH))
    print("待上传文件 %d 个:" % len(files))
    for rel, full in files:
        print("   %-40s %6d 字节" % (rel, os.path.getsize(full)))
    if args.dry_run:
        return 0

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("\n需要一个有该仓库 Contents 写权限的 GitHub Token。")
        print("生成地址: https://github.com/settings/tokens")
        token = getpass.getpass("粘贴 Token（输入时不显示）: ").strip()
    if not token:
        print("没有拿到 Token，已取消。")
        return 1

    status, who = api("GET", "/user", token)
    if status != 200:
        print("Token 校验失败:", status, who)
        return 1
    print("\nToken 属于账号:", who.get("login"))

    status, repo = api("GET", "/repos/" + REPO, token)
    if status != 200:
        print("读取仓库失败:", status, repo)
        return 1
    if not repo.get("permissions", {}).get("push"):
        print("警告: 该 Token 对这个仓库似乎没有推送权限，可能会失败。")

    message = args.message or "更新有道云笔记签到模板"
    failed = 0
    for rel, full in files:
        with open(full, "rb") as f:
            raw = f.read()
        quoted = urllib.parse.quote(rel, safe="/")
        payload = {
            "message": "%s: %s" % (message, rel),
            "content": base64.b64encode(raw).decode("ascii"),
            "branch": BRANCH,
        }
        status, existing = api("GET", "/repos/%s/contents/%s?ref=%s" % (REPO, quoted, BRANCH), token)
        if status == 200 and isinstance(existing, dict) and existing.get("sha"):
            payload["sha"] = existing["sha"]  # 已存在 -> 更新
            action = "更新"
        else:
            action = "新建"
        status, res = api("PUT", "/repos/%s/contents/%s" % (REPO, quoted), token, payload)
        if status in (200, 201):
            print("   %s %s -> %s" % (action, rel, res.get("commit", {}).get("sha", "")[:8]))
        else:
            failed += 1
            print("   失败 %s -> HTTP %s %s" % (rel, status, res))
    print("\n完成，失败 %d 个。" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
