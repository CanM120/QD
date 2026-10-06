# QD 模板库 · 有道云笔记每日签到

给 [qd-today/qd](https://github.com/qd-today/qd)（签到盒）用的**有道云笔记每日签到**模板。
本仓库同时是一个符合 QD 规范的**第三方模板库**（根目录有 `tpls_history.json`），可以直接在 QD 里订阅并自动更新。

> 只需要填一个 **Cookie** 变量就能跑。账号密码登录不可用 —— 有道登录已加图形验证码，所有在维护的脚本都改成 Cookie 方式了。

## 这个模板做什么

| # | 请求 | 作用 | 失败会让任务变红吗 |
| --- | --- | --- | --- |
| 1 | `GET /login/acc/pe/getsess` | 会话保活，用返回的 Set-Cookie 在本次运行内续期 | 不会 |
| 2 | `POST /yws/api/daupromotion?method=sync` | 安卓客户端**登录奖励** | **会**（Cookie 失效在这里第一个暴露） |
| 3 | `POST /yws/mapi/user?method=checkin&_system=android` | 安卓端**每日签到**（主奖励） | **会** |
| 4-6 | `POST /yws/mapi/user?method=adRandomPrompt` ×3 | 看视频广告奖励（每天 3 次） | 不会 |
| 7 | `GET api://util/regex` | 从 Cookie 里提取 `YNOTE_CSTK` | 不会 |
| 8 | `POST …?method=getSignStatus&device_type=PC…` | Windows 端签到状态（预热） | 不会 |
| 9 | `POST …?method=checkin&device_type=PC…` | Windows 端**签到**（多端各可领一次） | 不会 |
| 10 | `POST /yws/mapi/user?method=get` | 查当前总空间（只用于日志） | 不会 |
| 11 | `GET api://util/string/replace` | 把上面的数字拼成任务日志 | 不会 |

设计取舍：**只有第 2、3 条是硬断言**（HTTP 200 / 响应里出现 `space`），所以 Cookie 失效时会明确报错；其余都是「额外收益」，拿不到只会让日志里的数字变成 0，不会把整个任务判失败。

跑成功后任务日志形如：

```
有道云笔记签到｜安卓登录奖励 10.0 MB｜安卓签到 2.0 MB｜视频广告 1.5 MB｜Windows签到 1.0 MB｜总空间 3072.0 MB
```

## 一、先抓 Cookie（必需）

1. 用 Chrome 打开并登录 <https://note.youdao.com/web/>
2. `F12` → `网络 / Network` → 刷新页面
3. 点任意一个 `note.youdao.com` 的请求 → `标头 / Headers` → `请求标头` → 复制 `Cookie:` 这一行的**整行值**
4. 至少要包含 `YNOTE_CSTK`、`YNOTE_LOGIN`、`YNOTE_SESS`；建议整行都带上（`JSESSIONID`、`__yadk_uid`、`YNOTE_PERS` 等）
5. 有效期约 **20 天**，失效后任务会报 `AUTHENTICATION_FAILURE`，重新抓一次即可

> 抓 Cookie 用的浏览器尽量和平时用的一致 —— 有道对 UA 有校验，换了环境可能提示未登录。

## 二、在 QD 里使用

### 方式 A：订阅本仓库（可自动更新）

1. QD → `我的模板` → `社区模板` → 添加模板库（`reponame` / `repourl` / `repobranch` 三个字段）：
   - 仓库名：`CanM120`（随便填）
   - 仓库地址：`https://github.com/CanM120/QD`
   - 分支：`main`
2. 点「更新存储库」，在列表里找到「**有道云笔记签到**」→ 点 Subscribe 订阅
3. 之后 QD 会按 `tpls_history.json` 里的版本号自动更新模板

### 方式 B：手动导入（一定可用）

1. 下载本仓库的 [`有道云笔记签到.har`](./有道云笔记签到.har)
2. QD → `我的模板` → 右上角 `+` → 上传该文件 → 保存

### 然后创建任务

1. `我的任务` → `+` → 模板选「有道云笔记签到」
2. 任务变量 `cookie` 粘贴第一步抓到的内容（其余变量是模板内部提取数据用的，**留空即可**）
3. 执行时间：每天一次，建议 09:00 左右
4. 先点「测试」看日志，确认无误再保存；建议打开「失败时通知」，Cookie 过期能第一时间知道

## 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| 报 `AUTHENTICATION_FAILURE`，或 status 500 | Cookie 失效 / 复制不全 / 换了 UA。接口原样返回：`{"error":"207","message":"Message[AUTHENTICATION_FAILURE]: User token must be authenticated."}`，重新抓 Cookie |
| 某一项显示 0 MB | 该项今天已经领过（比如你手动签过到），或已达当天上限，属正常 |
| Windows 那两步一直失败 | 说明 `YNOTE_CSTK` 和提取规则对不上，把第 8、9 条请求删掉即可，不影响安卓部分奖励 |
| 想再多一点空间 | 社区模板库里的「有道云笔记IOS端签到」用的是 iOS 端 Cookie，和本模板互不冲突，可以一起跑 |
| 一天能领几次 | 安卓 / Windows / iOS 客户端分开计费，各自可领一次，所以本模板同时做了安卓和 Windows 两条 |

## 目录结构

```
.
├── 有道云笔记签到.har      # 模板本体（QD 内部 tpl 数组格式，与官方社区模板库一致）
├── tpls_history.json      # QD 第三方模板库索引（订阅本仓库时读取）
├── tools/
│   ├── build_template.py  # 生成 + 校验模板（改请求 / 改日志文案后跑它）
│   └── make_index.py      # 重新生成 tpls_history.json
└── upload.py              # 不装 git 也能上传：走 GitHub API
```

## 怎么改、怎么更新

```bash
# 1. 改模板：编辑 tools/build_template.py 的 build()，然后
python tools/build_template.py     # 重新生成 有道云笔记签到.har 并做校验

# 2. 刷新索引
python tools/make_index.py

# 3. 上传（需要对该仓库有 Contents 写权限的 GitHub Token）
python upload.py
```

`build_template.py` 会做三项离线校验：JSON 合法性、按 QD 源码 `libs/fetcher.py` 的 `tpl2har` 复刻转换、以及用 jinja2 真渲染所有 URL / 请求头 / 日志文本（本机有 jinja2 时）。

## 这个模板做过哪些验证

- **接口**：实际向 `note.youdao.com` 发过请求（无效 Cookie），确认鉴权失败的真实返回，断言照它写的
- **格式**：与官方社区模板库（`qd-today/templates`，400+ 个模板）的 `.har` 格式一致，`tpl2har` 转换校验通过
- **渲染**：jinja2 3.1.6 `SandboxedEnvironment` 真渲染过全部 URL / 请求头 / 日志文本
- **参考**：[`qd-today/templates`](https://github.com/qd-today/templates) 里的 `有道云笔记.har`、`有道云笔记IOS端.har`，以及 [Sitoi/dailycheckin 的有道实现](https://github.com/Sitoi/dailycheckin/blob/main/dailycheckin/youdao/main.py)

相比社区老模板的改进：去掉了对第三方换算网站 `cunchu.bmcx.com` 的 5 次依赖请求（更快，也不再把你账号的空间数值发给第三方），MB 换算改为模板内计算；补上了社区模板完全没有的失败断言；增加看视频广告奖励。

## 参考

- QD 项目：<https://github.com/qd-today/qd> ｜ 文档：<https://qd-today.github.io/qd/zh_CN/>
- 官方社区模板库：<https://github.com/qd-today/templates>
- 有道接口与 Cookie：[DailyCheckIn 设置文档](https://sitoi.github.io/dailycheckin/settings/youdao/)、[只能 Cookie 登录的说明](https://github.com/DeppWang/youdaonote-pull)

## License

[MIT](./LICENSE) © CanM120

> 仅供学习交流，请自行承担使用风险；请勿用于商业用途。
