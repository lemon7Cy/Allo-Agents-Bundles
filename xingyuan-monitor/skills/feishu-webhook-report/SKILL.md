---
name: feishu-webhook-report
description: "Use when the user asks to (1) send a report, alert, or monitoring summary to a Feishu group, or (2) look up or discover a Feishu group chat_id (群号) — e.g. 查群号 / 飞书机器人加入了哪些群 / 列出机器人所在的群 / 查一下 chat_id / which Feishu groups is the bot in / find the group id. Delivers via the Feishu application bot (app_id/app_secret); the discover-groups command needs only app_id/app_secret while the send command also needs the target chat_id. Prefer interactive cards when sending. Send immediately when the user explicitly asks to send, otherwise preview first."
version: "2.0.0"
author: allo-official
required_env:
  - FEISHU_APP_ID
  - FEISHU_APP_SECRET
optional_env:
  - FEISHU_CHAT_ID
credentials:
  - key: FEISHU_APP_ID
    label: 飞书应用 App ID (cli_...)
    description: 自建应用机器人的 App ID，用于换取 tenant_access_token 发送消息。与飞书入站渠道共用同一套凭据。
    required: true
    secret: false
  - key: FEISHU_APP_SECRET
    label: 飞书应用 App Secret
    description: 自建应用机器人的 App Secret。仅保存在本地、不显示明文。
    required: true
    secret: true
  - key: FEISHU_CHAT_ID
    label: 目标群 Chat ID (oc_...)
    description: 要把报告/告警卡片发送到的飞书群 ID（群号）。机器人需已加入该群。可先留空——配好 App ID/Secret 后用本技能的「查群号」命令列出后再填。
    required: false
    secret: false
---

# Feishu Report (Application Bot)

## Overview

This skill sends reports, monitoring summaries, and incident alerts to a Feishu **group** using the **application bot** (`FEISHU_APP_ID` / `FEISHU_APP_SECRET`), addressed by the target group's `FEISHU_CHAT_ID`. Always transform the source content into a Feishu `interactive` card with a clean executive-summary layout. Use plain text only as a fallback when the card payload is too large or the user explicitly requests text.

This skill is delivery-only. Generate and review the business content first, then use this skill to format and send it.

**硬性规则（对话不产代码文件）**：发送/查询**只用内联 `python3 - <<'PY' … PY` heredoc 执行**，**绝不**在工作目录创建或保留任何 `.py` 脚本文件（例如 `send_feishu_*.py`）。对话就是对话——数据用环境变量/标准输入传入，执行完即结束，不在磁盘留脚本。

This is the **outbound** path (push a card into a group). Inbound group @ → reply is handled by the Allo Feishu *channel*, which uses the **same** application bot (`app_id` / `app_secret`, addressed by `chat_id`). So configure `FEISHU_APP_ID` / `FEISHU_APP_SECRET` once and both inbound and outbound work; this skill additionally needs `FEISHU_CHAT_ID` to know which group to post to. The bot must already be a member of that group.

## 查群号 / Discover group chat_id

When the user has added the bot to a group but doesn't know its `chat_id`, run this to list
every group the bot is a member of, with each `chat_id` and name. Only needs
`FEISHU_APP_ID` / `FEISHU_APP_SECRET` (not `FEISHU_CHAT_ID`). Use it during setup, then put
the right `chat_id` into `FEISHU_CHAT_ID`.

```bash
python3 - <<'PY'
import json, os, sys, urllib.request

BASE = os.environ.get("FEISHU_API_BASE", "https://open.feishu.cn").rstrip("/")
APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")


def done(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False))
    sys.exit(code)


if not APP_ID or not APP_SECRET:
    done({"error": "missing_app_credentials"}, 2)


def req(url, method="GET", payload=None, headers=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json; charset=utf-8", **(headers or {})})
    with urllib.request.urlopen(r, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


try:
    tok = req(f"{BASE}/open-apis/auth/v3/tenant_access_token/internal", "POST", {"app_id": APP_ID, "app_secret": APP_SECRET})
except Exception as e:
    done({"error": "token_request_failed", "message": str(e)}, 1)
if tok.get("code") != 0:
    done({"error": "token_error", "code": tok.get("code"), "msg": tok.get("msg")}, 1)
token = tok.get("tenant_access_token", "")

chats, page_token = [], ""
for _ in range(10):
    url = f"{BASE}/open-apis/im/v1/chats?page_size=100" + (f"&page_token={page_token}" if page_token else "")
    try:
        res = req(url, "GET", headers={"Authorization": f"Bearer {token}"})
    except Exception as e:
        done({"error": "list_chats_failed", "message": str(e)}, 1)
    if res.get("code") != 0:
        done({"error": "list_chats_error", "code": res.get("code"), "msg": res.get("msg")}, 1)
    data = res.get("data", {})
    for c in data.get("items", []):
        chats.append({"chat_id": c.get("chat_id"), "name": c.get("name")})
    page_token = data.get("page_token", "")
    if not data.get("has_more"):
        break
done({"ok": True, "count": len(chats), "chats": chats})
PY
```

Show the user the returned `name` + `chat_id` list so they can pick the right group.

## Default Behavior

When this skill is selected, do not ask the user which card style to use. Apply these defaults automatically:

- Monitoring summary: compact executive card, `blue` header unless the content clearly indicates healthy (`green`), watch (`orange`), or incident (`red`).
- Daily/report request: executive report card using the same compact card fields, not a long Markdown paste.
- Alert: compact incident card with severity, scope, signal, and recommended actions.
- Generic summary: concise blue summary card.
- Confirmation preview: only required when the user asks for a draft/preview, asks to review first, or the send intent is ambiguous.

The user should only need to say what to send, not how to format it.

## Send Policy

Send immediately when the current user request explicitly asks to send or post to Feishu, for example:

- "send this to Feishu"
- "generate today's report and send it to Feishu"
- "post this alert to the group"
- "push the Xingyuan daily report now"

In this case, build the standard interactive card, send it, and then report the delivery result. Do not ask for a second confirmation.

Preview first when the user asks for a draft, preview, card design, or uses wording like "do not send", "wait for confirmation", or "let me review first".

If the request is ambiguous, default to preview first.

## Safety Contract

Before sending, all of the following must be true:

1. The complete outgoing content has been generated.
2. The current user request either explicitly asks to send now, or the user has confirmed after a preview.
3. The payload contains no secrets or raw credentials.

Never:

- Send automatically when the user only asked for a draft or preview.
- Print or reveal `FEISHU_APP_SECRET` or the `tenant_access_token`.
- Use `curl -v`, `set -x`, or any command that may expose secrets.
- Put secrets in URL query parameters.

## Card Design

Use Feishu `interactive` card messages by default:

```json
{
  "msg_type": "interactive",
  "card": {
    "config": { "wide_screen_mode": true },
    "header": {
      "template": "blue",
      "title": { "tag": "plain_text", "content": "Xingyuan Monitor | Daily Report" }
    },
    "elements": []
  }
}
```

Recommended visual language:

- Use `blue` for normal daily reports.
- Use `green` for healthy / success reports.
- Use `orange` for watch / warning reports.
- Use `red` for incident / high-risk alerts.
- Start with one compact overview block.
- Use `<text_tag color="blue">Label</text_tag>` for metric labels.
- Use `hr` between major sections.
- Use `note` for timestamp, data coverage, or caveats.
- Keep each card short enough to scan on mobile.

## Report Card Schema

When sending an operational daily report, structure the card like this:

1. Header: report name and date.
2. Overview markdown block: health status, time window, request/token/cost headline.
3. Metrics block: 4-8 key metrics using label tags.
4. Diagnosis block: confirmed facts and likely causes.
5. Risks/actions block: 1-3 short recommendations.
6. Note: generated time, data coverage, and whether it was manually confirmed.

Do not paste a full Markdown report into one giant card block. Convert the report into compact card fields. Tables should be summarized into 3-5 key rows unless the user explicitly asks for full tables.

Example card body:

```json
{
  "msg_type": "interactive",
  "card": {
    "config": { "wide_screen_mode": true },
    "header": {
      "template": "blue",
      "title": { "tag": "plain_text", "content": "Xingyuan Monitor | 2026-06-16" }
    },
    "elements": [
      {
        "tag": "markdown",
        "content": "<text_tag color=\"blue\">Status</text_tag> Healthy\n<text_tag color=\"blue\">Window</text_tag> 2026-06-16 Asia/Shanghai\n<text_tag color=\"blue\">Summary</text_tag> MaaS traffic is stable; DFCode usage is concentrated in gpt-5.5."
      },
      { "tag": "hr" },
      {
        "tag": "markdown",
        "content": "**Key Metrics**\n<text_tag color=\"blue\">Requests</text_tag> 2,439\n<text_tag color=\"blue\">Tokens</text_tag> 30.67M\n<text_tag color=\"blue\">Cost</text_tag> 917.55\n<text_tag color=\"blue\">Top model</text_tag> gpt-5.5"
      },
      { "tag": "hr" },
      {
        "tag": "markdown",
        "content": "**Diagnosis**\n- MaaS health is normal.\n- DFCode usage aligns with MaaS token trend.\n- No confirmed incident from feedback or audit logs."
      },
      {
        "tag": "note",
        "elements": [
          { "tag": "plain_text", "content": "Generated by Xingyuan Monitor. Sent after manual confirmation." }
        ]
      }
    ]
  }
}
```

## Xingyuan Monitor Card Alignment（星元监控卡片对齐）

When the content comes from the Xingyuan monitor agent, it is already a monitor card
with fields 状态 / 范围 / 信号 / 诊断 / 建议 / 缺口. Map it 1:1 into the Feishu card so the
group sees the same structure as the in-app dashboard:

- Header template by 状态: `正常`→`green`, `关注`→`orange`, `异常`/incident→`red`,
  `数据不足`→`grey` (or `blue`). Default `blue`.
- Overview markdown block: 状态 + 范围 + 信号.
- Metrics block: render the agent's `指标：` line (e.g. `token_total`, `requests`, `cost`,
  `top_model`) as `<text_tag color="blue">Label</text_tag>` rows. Do NOT invent metrics —
  only show what the agent provided.
- Diagnosis block: 诊断.
- Actions block: 建议 (≤3).
- Note: 缺口 + generated time + data coverage.

Keep it compact and mobile-scannable. When 缺口 says a capability/data source is unavailable
(e.g. DFCode MCP 未加载), surface it in the note rather than hiding it — a truthful gap is part
of the report.

## Alert Card Schema

When sending an incident or warning, use a more compact card:

```json
{
  "msg_type": "interactive",
  "card": {
    "config": { "wide_screen_mode": true },
    "header": {
      "template": "red",
      "title": { "tag": "plain_text", "content": "Xingyuan Alert | MaaS Error Spike" }
    },
    "elements": [
      {
        "tag": "markdown",
        "content": "<text_tag color=\"red\">Severity</text_tag> High\n<text_tag color=\"blue\">Scope</text_tag> public-maas / gpt-5.5\n<text_tag color=\"blue\">Signal</text_tag> upstream 429 increased in the last 15 minutes"
      },
      { "tag": "hr" },
      {
        "tag": "markdown",
        "content": "**Recommended Actions**\n1. Check provider pool health.\n2. Verify top accounts and throttling.\n3. Watch user feedback for failed requests."
      }
    ]
  }
}
```

## Send Script (Application Bot)

Build the interactive card and place it in `FEISHU_CARD_JSON` (either the full
`{"msg_type":"interactive","card":{...}}` object or just the bare card object — the script
accepts both). If no card JSON is provided, it sends `FEISHU_MESSAGE_TEXT` as a simple
interactive card. The script obtains a `tenant_access_token` from `FEISHU_APP_ID` /
`FEISHU_APP_SECRET`, then posts to the group `FEISHU_CHAT_ID` via the Feishu Messenger API.

```bash
python3 - <<'PY'
import json, os, sys, urllib.request, urllib.error

BASE = os.environ.get("FEISHU_API_BASE", "https://open.feishu.cn").rstrip("/")
APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
CHAT_ID = os.environ.get("FEISHU_CHAT_ID", "")
card_json = os.environ.get("FEISHU_CARD_JSON", "").strip()
text = os.environ.get("FEISHU_MESSAGE_TEXT", "").strip()


def done(obj, code=0):
    # Never include the secret or token in output.
    print(json.dumps(obj, ensure_ascii=False))
    sys.exit(code)


if not APP_ID or not APP_SECRET:
    done({"error": "missing_app_credentials"}, 2)
if not CHAT_ID:
    done({"error": "missing_chat_id"}, 2)


def post(url, payload, headers=None):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json; charset=utf-8", **(headers or {})}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


# 1) tenant_access_token (never logged)
try:
    tok = post(f"{BASE}/open-apis/auth/v3/tenant_access_token/internal", {"app_id": APP_ID, "app_secret": APP_SECRET})
except Exception as e:
    done({"error": "token_request_failed", "message": str(e)}, 1)
if tok.get("code") != 0:
    done({"error": "token_error", "code": tok.get("code"), "msg": tok.get("msg")}, 1)
token = tok.get("tenant_access_token", "")

# 2) build interactive card content (the API wants `content` as a JSON string of the card object)
if card_json:
    raw = json.loads(card_json)
    card_obj = raw.get("card", raw) if isinstance(raw, dict) else raw
    content = json.dumps(card_obj, ensure_ascii=False)
elif text:
    content = json.dumps({"config": {"wide_screen_mode": True}, "elements": [{"tag": "markdown", "content": text}]}, ensure_ascii=False)
else:
    done({"error": "nothing_to_send"}, 2)

# 3) send to the group by chat_id
try:
    res = post(
        f"{BASE}/open-apis/im/v1/messages?receive_id_type=chat_id",
        {"receive_id": CHAT_ID, "msg_type": "interactive", "content": content},
        headers={"Authorization": f"Bearer {token}"},
    )
except urllib.error.HTTPError as e:
    done({"error": "send_http_error", "status": e.code}, 1)
except Exception as e:
    done({"error": "send_failed", "message": str(e)}, 1)
if res.get("code") != 0:
    done({"error": "send_error", "code": res.get("code"), "msg": res.get("msg")}, 1)
done({"ok": True, "message_id": res.get("data", {}).get("message_id"), "chat_id": CHAT_ID})
PY
```

## Plain Text Fallback

Use Feishu `text` only if the user explicitly asks for plain text or the interactive card fails due to payload size. With the application bot, send it as a text message via the same API (`msg_type: "text"`, `content` = `{"text": "..."}` as a JSON string).

## Recommended Flow

1. Draft the report or alert.
2. Convert it to a concise interactive card automatically using this skill's default behavior.
3. Show the final card content to the user in readable Markdown form before sending.
4. Ask the user to choose: send / revise / cancel.
5. After confirmation, place the full card payload in `FEISHU_CARD_JSON` and run the send script.
6. Report the result (`ok` + `message_id`, or the returned error code). If delivery fails, explain the error code without exposing the app secret or token.

## Content Guidelines

- Keep the header under 40 characters when possible.
- Keep the first block to 2-4 lines.
- Use metric labels instead of long paragraphs.
- Put caveats in `note`, not in the headline.
- For daily reports, avoid more than 3 recommendations.
- For alerts, make severity, scope, signal, and action immediately visible.
- Do not ask the user for color, layout, card type, or schema unless they explicitly request customization.
