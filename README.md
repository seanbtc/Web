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

## 订单行显示（方向在前文案）与盈亏方向归属

- **全部订单行统一文案（方向在前）**：`多头开仓/空头开仓/多头平仓/空头平仓/多头加仓/空头加仓`（替换旧“开多仓/平空仓”等）。
  普通单按 side 派生：开/加 BUY→多头、SELL→空头；平 BUY→空头平仓（平空）、SELL→多头平仓（平多）；净调/决策腿记录沿用 `decision_leg_*` 优先（`leg_*`/执行语义回退）。
- **盈亏按方向归属（`display_pnl`）**：净额执行产生的已实现盈亏归属“被减仓/被平的那一侧”（执行平 BUY→空头、平 SELL→多头），只显示在该侧自身的平仓行；
  若某行展示的是另一侧动作（如“多头开仓”行实际执行的是减少空头）→ 该行订单盈亏显示“-”（`display_pnl=null`），金额结转到该侧平仓行累计显示，并以 `display_pnl_note` 标注来源日期（如 `含 10-06 结转`）。
  无对应平仓行时结转仅挂起不显示（纯展示层；摘要/总账仍按原始 `order_pnl` 计，总合计不变）。
- 派生与账务回放统一在加载/更新入口收尾（`_finalize_lead_records` = `_replay_trade_records_with_pnl` + `_apply_display_pnl_attribution`），幂等；决策腿字段随归一化落盘。
- **total_profit 曲线按 `display_pnl` 归属日期**：结转亏损落被平侧平仓行所属日期（如 10-06 的亏损落 10-08 的空头平仓行）；无该字段的旧记录回退原始已实现盈亏。
- 前端订单盈亏列优先取 `display_pnl`（字段存在时 `null` 表示“-”，并在数值下显示结转备注）；旧数据无该字段时回退 `order_pnl ?? realized_pnl ?? net_profit`。
- 现网五条记录示例（after）：09-21 `空头开仓`；10-06 `多头开仓`（盈亏“-”）；10-08 `空头平仓` `-783.67`（`display_pnl=-783.6658`，备注 `含 10-06 结转`）；10-08 `多头开仓`（“-”）；12:00 `多头加仓`（“-”）。

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
- 回填后重启 Web（或等待热加载）即可见徽章变为“多头开仓”、备注 `净头寸调整（实际执行：减少空头 0.187）`。
