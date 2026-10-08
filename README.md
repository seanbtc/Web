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

## 总盈亏曲线（total_profit.json）自动更新

- 历史写入方：仓库内无任何代码写 `data/total_profit.json`（仅读取 + mtime 热加载），此前为人工维护；现由 Web 在收到 `/api/update_lead` 并落盘 `lead_trades.json` 后自动更新。
- **当日点由程序接管**：`YYYY-MM-DD` 当日点会随窗口盈亏原地重算，请勿人工手改（改动会在下一次同步被覆盖）；历史点仍可人工维护。
- 规则（`_sync_total_profit_from_lead`，幂等、确定性）：以最新一个早于今日的曲线点为基线，当日点
  `total_funds = 基线 total_funds + 窗口内 lead 记录的已实现盈亏之和`，`principal` 沿用基线；
  窗口口径与 lead summary 一致（`order_pnl`/`realized_pnl`，含净头寸调整平仓），基线之前与 archived 记录视为已计入基线、不重复累计。
- **基线粒度语义**：日粒度点（`YYYY-MM-DD`）为当日结算值，窗口从**次日**起算；年月粒度点（`YYYY-MM`）为**月末结算值**，窗口从**次月 1 日**起算（基线月内记录不再重复累计）。基线日期格式无法判定时打印告警并跳过自动同步（不改动文件）。
- **旧 payload 回退**：TradeSync 未携带 `realized_pnl/gross_pnl/entry_price/exit_price/timestamp` 时，Web 按回放持仓桶推算平仓盈亏，`timestamp` 缺失回退为接收时间（`_normalize_lead_trade_record`），不影响同步窗口口径。
- 当日点已存在时原地重算（同一日多笔成交/重复推送不会重复累计）；窗口盈亏为 0（`abs(window_pnl) < 1e-9`）时不改动文件。
- 写盘为原子写（tempfile + `os.replace`，同目录内替换）；热加载解析失败时打印告警并保留现有内存数据，不回退为空。
- 生效方式：重启 web 后，历史记录展示字段在加载时幂等重算；总盈亏曲线在下一笔 `/api/update_lead` 时补齐（含空窗期补记）。

## 净头寸调整显示（决策腿优先级）与历史回填

- 展示优先级：`decision_leg_direction`/`decision_leg_action`（决策腿）→ 现有 `leg_*`/执行语义回退。
  决策腿 `long/open` → “开多仓”、`short/close` → “平空仓”（add 同理为“加X仓”）；缺失时沿用执行语义徽章与 `leg_*` 备注。
- 备注口径：决策腿为开/加时显示实际执行净额说明（如 `净头寸调整（实际执行：减少空头 0.187）`，优先取 `attribution` 净头寸前后值，缺失按决策腿兜底）；
  平仓类沿用单侧原因（如 `信号平仓（净头寸调整执行）`）；任何路径不输出“归因：”叙事。盈亏列照常显示（有值即显示）。
- 决策腿字段随归一化落盘（`_normalize_lead_trade_record`），重载/重算幂等稳定。

### 一次性历史回填工具

2026-10-06 00:00:03 的旧净调记录（`order_id=1155109993906`，平空 0.187@85220.3，实为多头腿开仓驱动）需要补决策腿字段；
10-08 两条（平空 0.01 / 开多 0.173）靠优先级+回退自然正确，无需回填。

```powershell
# 预览（零写盘）
.venv\Scripts\python.exe tools\backfill_legacy_decision.py --dry-run
# 执行（自动备份原文件为 lead_trades.json.bak-<UTC 时间戳>）
.venv\Scripts\python.exe tools\backfill_legacy_decision.py
```

- 默认目标 `data\lead_trades.json`（可用 `--file` 指定，`--order-id` 默认 `1155109993906`）；不联网、不依赖 Web 服务。
- 幂等：字段已一致时不写盘、不备份；写盘为原子替换。
- 验证输出（示例）：dry-run 打印 `decision_leg_action: None -> 'open'` 等三行后 `[dry-run] 仅预览，未写盘`；
  正式执行打印三行 diff 后 `完成：order_id=1155109993906；备份：...`；再次执行打印 `已是最新（幂等）`。
- 回填后重启 Web（或等待热加载）即可见徽章变为“开多仓”、备注 `净头寸调整（实际执行：减少空头 0.187）`。
