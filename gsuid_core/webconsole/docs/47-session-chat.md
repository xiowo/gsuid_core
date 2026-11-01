# 47. 会话管理（消息记录）API - /api/history/chat

> 控制台「会话管理」页的数据来源。与 [18. History Manager](./18-history.md) 共用同一份内存历史，
> 区别是这里返回**按段还原的消息**（文本 / @ / 引用 / 图片 / 语音 / 视频 / 文件 / 表情 /
> 合并转发 / Markdown / 按钮 / 卡片），并附带置顶、备注、拉黑等面板状态。
>
> 消息段由 `gsuid_core/message_history/segments.py` 生成，前端类型定义在
> `gsuid_hub/src/lib/sessionChat/index.ts`，两边结构必须同步修改。

## 47.1 数据从哪来

| 数据 | 来源 |
|------|------|
| 会话与消息 | `HistoryManager`（滚动保留 12 小时，进程内） |
| 置顶 / 拉黑 / 备注 | `data/webconsole_chat_prefs.json`（面板状态，与适配器无关） |
| 群名 / 群头像 | `CoreGroup` 表 |
| 用户 openid / unionid / 群身份 | 入站消息的 `sender` 快照 |

**机器人发出的消息按「最终发出去的那条」入库**：`Bot.send` 里 `convert_message` 与
`to_markdown` 都跑完之后才写历史，所以控制台看到的段数组就是适配器实际下发的内容。

## 47.2 段结构

```json
{"type": "text",     "text": "你好"}
{"type": "at",       "qq": "10000", "name": ""}
{"type": "reply",    "id": "123456"}
{"type": "image",    "url": "https://… 或 /api/history/resource/img_xxx"}
{"type": "record",   "url": "…"}
{"type": "video",    "url": "…"}
{"type": "file",     "url": "…", "name": "报告.pdf"}
{"type": "face",     "id": "1"}
{"type": "forward",  "count": 2, "items": [[seg, …], …]}
{"type": "markdown", "content": "## 标题", "template": {}, "raw": "…"}
{"type": "button",   "rows": [[{"text": "点我", "callback": "hi"}]]}
{"type": "ark",      "templateId": 23, "kv": [{"key": "", "value": ""}], "raw": "…"}
{"type": "unknown",  "kind": "some_type", "text": "[some_type]"}
```

媒体一律不留 base64：能拿到直链就用直链，其余登记进 `RM` 换成 `/api/history/resource/{id}`。
本地文件路径会先读成字节再登记——资源路由把 `str` 当 base64 解，直接存路径取回会 500。

插件常把 Markdown 直接拼进 `text` 段（`![图片 #36px #36px](路径)`、`[按钮](mqqapi://aio/inlinecmd?…)`），
平台侧会渲染成图片和按钮。这类 `text` 段会被升级成 `markdown` 段，其中的本地图片路径同步换成资源直链；
普通聊天里的 `1+1`、`a_b_c` 不命中 Markdown 结构，仍是 `text` 段。

## 47.3 会话列表

```
GET /api/history/chat/sessions
```

返回 `{sessions: [...], count}`，每项含 `session_id`、`type`、`title`（群名 / 昵称，取不到退回 id）、
`avatar`、`message_count`、`last_preview`、`last_time`，以及 `pinned` / `note` / `blacklisted`。
排序规则：置顶优先，其次按最后一条消息时间倒序。

## 47.4 会话消息

```
GET /api/history/chat/{session_id}/messages?limit=500
```

时间正序返回，每条形如：

```json
{
  "role": "user",
  "self": false,
  "user_id": "777",
  "user_name": "小明",
  "timestamp": 1760000000.0,
  "content": "纯文本，给 AI 用",
  "segments": [{"type": "text", "text": "你好"}],
  "sender": {"user_id": "777", "nickname": "小明", "role": "admin"},
  "msg_id": "123456"
}
```

`self=true` 表示机器人自己发的。`msg_id` 是平台消息 ID，引用回复要用它。

## 47.5 发送消息

```
POST /api/history/chat/{session_id}/send    (multipart/form-data)
```

| 字段 | 说明 |
|------|------|
| `mode` | `plain` / `markdown` / `card` / `rich` |
| `text` | 普通文本 |
| `markdown` | markdown 正文（`plain` 模式下忽略） |
| `card` | `{type, content}` 的 JSON，出 `card` 段。面板只开放图文卡片 `tuwen`，字段用 QQ 官方叫法 `title` / `description` / `pic_url` / `url`，空字段不发；`desc` / `picUrl` / `jumpUrl` 也会被归一成官方字段名，认不出的字段直接丢弃（官方接口对多余字段是报错不是忽略）。协议端发不出 card 时适配器会跳过该段 |
| `at` | 逗号分隔的用户 id 列表，@ 段排在正文之后 |
| `reply` | 被引用消息的 `msg_id`，reply 段排在最前 |
| `image_urls` | 图片直链（仅 http/https） |
| `images` / `records` / `videos` / `files` | 上传文件，`rich` 模式下四个都会带上（前端按 MIME 自动分段） |

发出去的消息会经 `Bot.send` 自动进历史，随后由 WebSocket 推回前端，不需要本地插入。

## 47.6 会话偏好

```
POST /api/history/chat/{session_id}/prefs
{"pinned": true, "note": "自家小群", "blacklisted": false}
```

三个字段都可省略，只改传了的。`note` 传空串表示清除，最长 64 字。

> `blacklisted` 写的是**框架级全局黑名单**（`sp_config` 的 `BlackList`，与「拉黑」命令同源）：
> 群聊记群号、私聊记 QQ 号，命中后该会话不再触发任何命令 / AI / 插件。

## 47.7 群 / 用户信息卡

```
GET /api/history/chat/{session_id}/info?user_id=&refresh=true
```

群聊返回群名 / 群号 / 人数，私聊返回昵称 / 群名片 / 群身份 / openid / 账号 / unionid。
`refresh=true` 时先向适配器现取（OneBot 系经 `plugins/OneBotUID` 的通用接口桥），
取不到就退回面板记录，并在 `live_error` 里说明原因。

## 47.8 实时推送

```
WS /api/history/chat/ws?token=<控制台登录令牌>
```

帧格式：

```json
{"type": "message", "session_id": "…", "message": {…}}
{"type": "cleared", "session_id": "…"}
{"type": "deleted", "session_id": "…"}
{"type": "ping"}
```

`HistoryManager.add_message` 写入后经 `message_history/hub.py` 广播；`ping` 每 25 秒一帧，
用来保活并顺带发现掉线的客户端。队列满时丢新消息，不阻塞发消息主链路。

## 47.9 消息缓存

内存里的历史只有 12 小时，重启就没了。开启缓存后会把**消息原始段**写进数据库
（表 `coremessagecache`），重启后控制台还能翻。

```
GET  /api/history/chat/cache          → {hours, enabled, count}
POST /api/history/chat/cache          {"hours": 24}   // 0 = 不缓存
POST /api/history/chat/cache/clear    → {removed}
```

- 配置项 `CacheHours` 在 `data/configs/message_cache_config.json`，**默认 0（不缓存）**，
  单位小时，上限 8760。改的是同一份数据的两个入口：
  **框架配置 → 消息缓存**，以及**会话管理页头部的数据库图标**；
- 写入走 `message_history/cache.py` 的后台协程：`add_message` 里只投递，不落库阻塞；
  批量 200 条 / 最多等 2 秒，队列满（2000）就丢，绝不反压消息链路；
- 清理每 10 分钟一次，删掉 `created_at` 超出保留窗口的行；改小保留时长会立刻清一次；
- 关掉缓存**不会**删存量数据，要清就调 `cache/clear` 或面板上的「清空缓存」；
- 读的时候内存优先：`/messages` 把库里内存没有的补上（按 `角色 + 时间 + 内容` 去重），
  响应里的 `from_cache` 是这次从库里补的条数；`/sessions` 也会把只在库里存在的会话列出来。
