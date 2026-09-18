# web

## 登录门禁配置

面板默认需要登录：配置 `WEB_LOGIN_PASSWORD`（明文）或 `WEB_LOGIN_PASSWORD_SHA256`（64 位十六进制，优先）后生效；
用户名由 `WEB_LOGIN_USERNAME` 指定（默认 `admin`）。两者都未配置时保持旧行为（面板开放访问），部署时必须配置。

- 会话密钥：`WEB_SESSION_SECRET`；留空则每次启动随机生成，重启后所有登录会话失效。
- 会话时长：`WEB_SESSION_HOURS`（小时，默认 168 = 7 天）；登录后 `session.permanent=True`。
- 回跳 `?next=` 仅允许站内相对路径，控制字符/`//`/反斜杠一律拒绝。
- 同一 IP 连续失败 5 次锁定 60 秒（内存字典，不持久化）。
- 写接口（`/api/update_*`，含 `/api/update_post_feed`）仍走各自的 `WEB_API_TOKEN` 鉴权，内部调用方（TradeSync/Promo/AutoDCA）不受登录门禁影响；`/health` 与 `/static/*` 免登录。
- 未登录访问读接口返回 401 JSON，页面/`/data/*` 返回 302 `/login?next=...`；Socket.IO 未登录连接会被拒绝。

配置键说明见 [`.env.example`](.env.example) 或工作区根 `.env.example`。测试：`.venv\Scripts\python.exe -m pytest tests\ -q`。
