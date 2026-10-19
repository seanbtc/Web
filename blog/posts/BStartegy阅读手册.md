---
title: BStartegy阅读手册
date: 2026-06-08 22:14:28
---
# BStrategy 代码库阅读文档

> 基于可配置周期 K 线的多策略融合量化交易系统。

---

## 目录

1. [项目概览](#1-项目概览)
2. [目录结构](#2-目录结构)
3. [架构总览](#3-架构总览)
4. [核心模块详解](#4-核心模块详解)
   - [4.1 入口层](#41-入口层)
   - [4.2 配置系统](#42-配置系统)
   - [4.3 数据层](#43-数据层)
   - [4.4 信号层](#44-信号层)
   - [4.5 回测引擎](#45-回测引擎)
   - [4.6 参数优化器](#46-参数优化器)
   - [4.7 监控层](#47-监控层)
   - [4.8 交易管理层](#48-交易管理层)
   - [4.9 风控层](#49-风控层)
5. [策略体系](#5-策略体系)
6. [运行模式](#6-运行模式)
7. [Both 模式详解](#7-both-模式详解)
8. [配置系统详解](#8-配置系统详解)
9. [数据流图](#9-数据流图)
10. [关键设计决策](#10-关键设计决策)

---

## 1. 项目概览

BStrategy 是一个 Python 量化交易系统，围绕 **固定周期 K 线（默认 4H）** 运行。核心思路：
- 每根 K 线收线时计算 **6 类技术指标**（3 震荡类 + 3 趋势类）
- 结合 **日线裸 K 形态概率模型** 输出开平仓信号
- 通过 **Webhook** 将信号推送到 TradeSync 服务执行实际订单

### 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.10+ |
| 数据处理 | pandas >= 2.0, numpy >= 1.24 |
| 时区处理 | pytz >= 2023.3, zoneinfo |
| 行情获取 | Binance REST API (requests) |
| WebSocket | websocket-client >= 1.6.0 |
| 并行优化 | multiprocessing (ProcessPoolExecutor) |
| 跨进程通信 | multiprocessing.shared_memory |

### 依赖

```
pandas>=2.0.0
numpy>=1.24.0
pytz>=2023.3
requests>=2.28.0
websocket-client>=1.6.0
```

---

## 2. 目录结构

```
BStrategy/
├── multistrategy.py                # 【核心】KlineMonitor 主调度器 (3132 行)
├── multistrategy_cli.py            # CLI 入口与模式分发 (583 行)
├── live_risk_monitor.py            # 实盘风控监控器，REST API 价格轮询 (662 行)
├── requirements.txt                # Python 依赖
├── README.md                       # 项目简要说明
│
├── core/                           # 核心配置与工具
│   ├── config.py                   # StrategyConfig 数据类 + 交易对配置加载 (1187 行)
│   ├── position_sizing.py          # 仓位计算 & 数量归一化 (86 行)
│   ├── runtime_utils.py            # 运行时工具函数 (216 行)
│   └── virtual_position_state.py   # Both 模式虚拟仓位状态管理 (75 行)
│
├── data/                           # 数据获取与指标计算
│   ├── indicators.py               # 技术指标 + Binance API 客户端 (727 行)
│   ├── kline_archive.py            # 本地 K 线 CSV.GZ 归档 (285 行)
│   └── daily_pattern_analyzer.py   # 日线 K 线形态识别 (579 行)
│
├── signals/
│   └── signal_calculator.py        # 六类子策略信号计算 (391 行)
│
├── backtest/                       # 回测引擎
│   ├── backtest_runner.py          # 逐 bar 回放引擎 (1365 行)
│   ├── combined_backtest.py        # 训练/验证双窗口合并回测 (321 行)
│   ├── both_mode_runtime.py        # Both 模式虚拟仓位运行时 (371 行)
│   ├── backtest_window_utils.py    # 时间窗口工具 (141 行)
│   ├── market_regime_boundaries.json      # BTC 牛熊边界定义
│   ├── optimizer_search_space.json        # 默认搜索空间 (含 common/short/long 分组)
│   └── search_spaces/              # 参数模板库
│       ├── conservative.json       # 保守 (150 trials, 低回撤优先)
│       ├── balanced.json           # 平衡 (120 trials, 收益与风险平衡)
│       └── aggressive.json         # 激进 (180 trials, 收益优先)
│
├── optimization/                   # 参数搜索
│   ├── auto_optimizer.py           # SmartParameterOptimizer (2561 行)
│   └── optimize_mode_config.py     # 优化模式配置数据类 (180 行)
│
├── monitoring/                     # 实盘监控
│   ├── monitor_components.py       # 调度器/仓位执行器/optimize-live 协调器 (1028 行)
│   ├── monitor_runtime_summary.py  # Live 启动摘要格式化 (96 行)
│   └── monitor_signal_formatter.py # 信号格式化输出 (215 行)
│
├── trading/                        # 交易管理
│   ├── pair_runtime_manager.py     # 交易对动态监听管理 (288 行)
│   ├── webhook_payloads.py         # Webhook 路由与负载构建 (38 行)
│   └── strategy_promo_bridge.py    # StrategyPromo 事件桥接 (55 行)
│
├── trading_pairs/                  # 交易对配置
│   ├── _template.pair.json         # 配置模板 (以 _ 开头即被排除)
│   ├── btc.lead.json               # 带单配置 (both 模式, 4 账号)
│   ├── btc.um.json                 # UM 合约配置 (both 模式, 1 账号)
│   └── params/                     # 优化参数文件
│       ├── btc_combine_lead_public.long.optimize_params.json
│       ├── btc_combine_lead_public.short.optimize_params.json
│       ├── btc_combine_um.long.optimize_params.json
│       └── btc_combine_um.short.optimize_params.json
│
├── logs/pairs/                     # 运行日志（按交易对文件分流）
├── runtime/                        # 运行时状态文件
└── backtest/output/                # 回测报告输出
```

---

## 3. 架构总览

### 3.1 分层架构

```
┌─────────────────────────────────────────────────┐
│                   CLI Layer                       │
│         multistrategy_cli.py (argparse)           │
│   mode dispatch, pair selection, batch runner     │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              Orchestration Layer                  │
│   multistrategy.py  —  KlineMonitor (核心调度器)  │
│   pair_runtime_manager.py  —  多交易对管理        │
└────┬──────────┬──────────┬──────────┬────────────┘
     │          │          │          │
┌────▼───┐ ┌───▼────┐ ┌───▼───┐ ┌───▼──────────┐
│  Data  │ │Signals │ │Backtest│ │  Monitoring   │
│  Layer │ │ Layer  │ │ Engine │ │  & Trading    │
└────────┘ └────────┘ └────────┘ └───────────────┘
```

### 3.2 核心对象关系

```
KlineMonitor (multistrategy.py)
    ├── cfg: StrategyConfig              # 配置（含参数文件叠加）
    ├── ti: TechnicalIndicators           # 指标计算器（含 Binance API、K线归档）
    │     └── daily_analyzer: DailyPatternAnalyzer  # 日线形态分析
    ├── sc: SignalCalculator             # 信号计算器
    ├── bt: BacktestRunner               # 回测引擎
    ├── pe: MonitorPositionExecutor      # 仓位执行器（下单/平仓/IPnL跟踪）
    ├── ol: MonitorOptimizeLiveCoordinator  # optimize-live 协调器
    ├── scheduler: MonitorScheduler      # 定时器/生命周期
    ├── promo_bridge: StrategyPromoEventBridge  # 社交推送桥
    │
    ├── _virtual_short: dict             # Both模式 - 做空虚拟仓位
    ├── _virtual_long: dict              # Both模式 - 做多虚拟仓位
    └── _general_position: dict          # Both模式 - 实际持仓追踪
```

---

## 4. 核心模块详解

### 4.1 入口层

#### multistrategy_cli.py

系统唯一入口，负责：
- **参数解析**：argparse 处理 `--mode`, `--pair`, `--backtest`, `--optimize`, `--all-enabled-pairs`, `--watch-pairs` 等
- **模式分发**：根据 `--mode` 或交易对配置中的 `run_mode` 决定运行模式
- **交易对加载**：按优先级 `--pair/--pairs > --all-enabled-pairs > 交互选择 > 单配置默认`
- **批处理队列**：backtest/optimize 模式下，both 交易对自动拆成 short/long 两个子任务顺序执行
- **Live 启动**：启动 KlineMonitor 线程 + LiveRiskMonitor 全局单例

**运行模式映射** (`multistrategy_cli.py:174-187`):
```
--mode       → 直接使用
--backtest   → "backtest"
--optimize   → "optimize"
默认         → 从 trading_pairs JSON 读取，无则 "live"
```

**优化模式** (`multistrategy_cli.py:357-398`): 遍历 monitors，对 each monitor 遍历 short/long directional runs，调用 `optimizer_runner` 执行参数搜索。

#### multistrategy.py — KlineMonitor 类

系统最核心的类，314 行的 `__init__` 构建完整运行时环境。关键职责：

| 职责 | 实现 |
|------|------|
| K 线处理 | `process_candle()` — 单根 K 线的完整处理流程 |
| 指标计算 | 委托给 `self.ti.calculate_all_indicators()` |
| 信号评估 | 委托给 `self.sc.calculate_signals()` / `calculate_long_signals()` |
| 信号→交易决策 | `_evaluate_short_entry()`, `_evaluate_long_entry()`, `_evaluate_short_close()`, `_evaluate_long_close()` |
| Both 模式 | `process_candle_both_mode()` — 委托给 both_mode_runtime |
| Webhook 发送 | `_send_trade_webhook()` — POST 到 TradeSync |
| 止盈止损 | 回测中由 backtest_runner 处理；实盘中由 LiveRiskMonitor 独立处理 |
| 回测 | `run_backtest_replay()` — 加载数据→创建BacktestRunner→运行 |
| optimize-live | 委托给 `MonitorOptimizeLiveCoordinator` |

**关键属性** (来自 `__init__` 的初始化):
```python
self.symbol                    # "BTCUSDT"
self.running = True            # 运行标志
self.is_backtest = False       # 回测模式标志
self.equity = initial_capital  # 当前净值
self.position = {}             # 单方向持仓: size, avg_price, stop_price, trade_count 等
self.trade_records = []        # 已平仓记录
self.order_events = []         # 订单事件日志（用于回测浮亏计算）
self.both_long_short_enabled   # Both 模式总开关
```

**`process_candle()` 核心流程** (`multistrategy.py:560+`):
```
1. 获取 K 线数据 (交易所 API 或回测注入)
2. 计算所有技术指标 → indicators dict
3. 获取每日形态快照 → daily_snapshot
4. 根据交易方向评估开仓信号: _evaluate_short_entry() / _evaluate_long_entry()
5. 根据交易方向评估平仓信号: _evaluate_short_close() / _evaluate_long_close()
6. Both 模式: 合并短/长信号 → process_candle_both_mode()
7. 止盈止损检查: apply_risk_rules()
8. 记录信号日志
```

**`run()` 方法** (`multistrategy.py:2945+`): 启动主循环:
1. 调用 `scheduler.run()` → 对齐到下一个 K 线收线时间
2. Bootstrap：如果需要恢复状态，从历史数据回放
3. 如果启用 optimize-live，启动协调器
4. 进入事件循环（Timer 驱动）

---

### 4.2 配置系统

#### core/config.py — StrategyConfig

`@dataclass StrategyConfig` 包含约 **130+ 配置字段**，分为以下类别：

| 类别 | 字段示例 | 默认值 | 说明 |
|------|---------|--------|------|
| **基础运行** | `run_mode`, `symbol`, `initial_capital` | `""`, `""`, `0.0` | 必填 |
| **K线设置** | `kline_timeframe_minutes`, `kline_close_wait_seconds` | `0`, `2` | K线周期、收线等待 |
| **交易** | `trade_direction`, `fee_rate`, `enable_real_orders` | `""`, `0.00035`, `True` | 方向、手续费、是否真实下单 |
| **仓位** | `position_ratio`, `leverage`, `probability_to_position_ratio_scale` | `2.0`, `1.0`, `2.0` | 仓位杠杆 |
| **止损** | `stoploss`, `movestoploss`, `stoploss_perc`, `stop_source` | `True`, `"Percentage"`, `0.0425`, `"low"` | 止损参数 |
| **止盈** | `take_profits`, `max_tp`, `short_profit_perc`, `short_profit_qty` | `True`, `4`, `0.13`, `0.6` | 多级止盈 |
| **延迟** | `delay_rsi`, `delay_macd`, `delay_srsi`, `delay_mfi`, `delay_super`, `delay_cross`, `delay_exit` | `6`, `3`, `6`, `6`, `5`, `6`, `16` | 信号延迟过滤 |
| **策略1-6** | `use_strategy1..6`, `rsi_length`, `macd_ma1_type` 等 | 见代码 | 子策略参数 |
| **阈值** | `trend_signal_threshold`, `osc_signal_threshold` | `1`, `1` | 趋势/震荡确认阈值 |
| **日线形态** | `daily_pattern_enabled`, 5 类 pattern weight, `min_fit`, `min_strength` | 见代码 | 日线分析参数 |
| **回测窗口** | `from_year/month/day`, `to_year/month/day` | `0` | 训练窗口 |
| **验证窗口** | `validation_from_year/month/day`, `validation_to_year/month/day` | `0` | 验证窗口 |
| **Webhook** | `webhook_url`, `webhook_profiles_dir`, `webhook_target_account_files` | localhost | 信号推送 |
| **数据** | `backtest_data_file`, `kline_archive_file`, `market_regime_boundaries_file` | random | 数据文件路径 |

#### 配置加载优先级

`load_config()` (`config.py:1140-1179`) 采用**多层叠加**策略：

```
1. StrategyConfig 默认值 (Python 代码中的硬编码)
2. apply_trading_pair_config() (trading_pairs/*.json 的直接字段)
3. load_params_from_json() (优化参数文件，倒第二层覆盖)
4. apply_trading_pair_config() 再次调用 (交易对直配字段最高优先级)
5. Both 模式: 额外 load_directional_params_from_json(short) + (long)
6. 种子归档: 将 backtest_data_file 导入 LocalKlineArchive
```

**关键设计**：交易对 JSON 的直配字段（symbol, initial_capital, trade_direction 等）优先级始终高于优化参数文件。第 4 步的二次调用确保优化参数不会覆盖这些固定字段。

#### Both 模式配置拆分

Both 模式的核心机制 (`config.py:812-831`):
```python
def build_directional_runtime_config(self, direction):
    directional_cfg = copy.deepcopy(self)
    _apply_param_payload(directional_cfg, self.common_params)     # 先 common
    _apply_param_payload(directional_cfg, self.short_params)      # 再方向独立
    directional_cfg.trade_direction = direction                   # 单向
    return directional_cfg
```

`common_params` 包含 shared 字段（运行参数），`short_params` / `long_params` 包含方向独立的策略参数。这样 short 和 long 可以有完全不同的止损/止盈/指标参数。

#### 市场牛熊区间

`market_regime_boundaries.json` 定义 BTC 历史高低点序列：
- `lowest` → 牛市起点（当前位置是市场最低点）
- `highest` → 熊市起点（当前位置是市场最高点）

`refresh_market_regime_windows()` (`config.py:738-792`) 根据当前 UTC 时间自动判定：
- **训练窗口** = 上一个同类型区间的起始到终止
- **验证窗口** = 当前区间起始到当前时间
- `active_market_regime` = `"bull"` 或 `"bear"`

**当前状态** (基于文件预定义的边界):
```
2022-11-21 23:59 → lowest  (熊市最低点, 牛市起点)
2025-10-06 23:59 → highest (牛市最高点, 熊市起点)
2026-06-08       → now     (当前仍在 bear 区间)
```

---

### 4.3 数据层

#### data/indicators.py — TechnicalIndicators

**SimpleBinanceAPI** (`indicators.py:33-125`):
- 期货和现货双市场 K 线拉取
- 自动重试 + HTTP 连接池 (`HTTPAdapter`)
- `get_historical_klines()`: 支持 `start_time` / `end_time` 参数
- `get_current_price()`: 实时价格查询

**TechnicalIndicators** (`indicators.py:127-727`):
- 持有 `SimpleBinanceAPI` 实例
- 持有 `DailyPatternAnalyzer` 实例
- 持有 `LocalKlineArchive` 实例（可选）

**支持的均线类型** (MA types):
```python
SMA, EMA, RMA (Wilder's), WMA, VWMA, DEMA, TEMA, HMA
```

**计算的指标** (`calculate_all_indicators()`):
| 指标 | 说明 | 输出 |
|------|------|------|
| RSI | Relative Strength Index (Pine Script 兼容) | 0-100 值 |
| Stoch RSI | Stochastic RSI %K | 含 stoch_k, stoch_d |
| MFI | Money Flow Index | 0-100 值 |
| MACD | 双均线交叉 (MA 类型/源可配) | macd_line, signal_line, histogram |
| Supertrend | ATR 趋势带 (Pine 兼容) | trend (1=上涨, -1=下跌), direction, atr |
| MA Cross | 双均线金叉死叉 | ma1, ma2 (双均线序列) |
| Daily Pattern | 日线 K 线形态概率分析 | bullish/bearish probability/confidence |

**K 线数据获取策略** (`_get_kline_data()`):
1. 先尝试**本地归档** (`LocalKlineArchive`)
2. 缺失部分从 **Binance API** 拉取
3. 拉取的增量数据自动追加到归档
4. 数据始终以 **UTC** 时区存储

#### data/kline_archive.py — LocalKlineArchive

本地 K 线数据管理系统：

- **存储格式**: CSV.GZ 压缩文件
- **线程安全**: `RLock` 保护读写
- **归档机制**:
  - `append_dataframe()`: 追加新 K 线，自动去重合并
  - `verify_contiguous_windows()`: 检查数据连续性
  - `get_window()`: 按时间范围读取数据切片
- **种子文件**: 启动时将现有 CSV 导入归档
- **LRU 缓存**: 通过 `_DF_CACHE` 缓存最近读取的数据窗口
- **时区处理**: 存储 UTC，运行时转为 `Asia/Shanghai`

#### data/daily_pattern_analyzer.py — DailyPatternAnalyzer

识别 **10 种经典日线 K 线形态**，每类都有对应的 bullish 和 bearish 版本：

| 形态 | 权重 (可配) | 说明 |
|------|-----------|------|
| Pin Bar (锤子线/流星) | 1.00 | 长影线 + 小实体 |
| Engulfing (吞没) | 1.10 | 实体完全覆盖前一根 |
| Morning/Evening Star (启明/黄昏星) | 1.15 | 三日反转形态 |
| Three Soldiers/Crows (三白兵/三黑鸦) | 0.95 | 三日连续实体推进 |
| Marubozu (光头光脚) | 0.70 | 无影线实体 |

**分析流程**:
1. 聚合日内所有 K 线为日线 OHLC（时区可配）
2. 对每根日线评估 10 种形态
3. 每个形态输出两个分数：
   - **fit**: 形态符合度 (0-1)
   - **strength**: 形态强度 (0-1)
4. **confidence** = weight × fit × strength
5. 汇总 bull_confidence / bear_confidence
6. **net_edge** = tanh(bull - bear) → 映射为 bullish_probability / bearish_probability (0.5-1.0)
7. 将日线级分析映射到日内每根 K 线

**阈值过滤**:
- `daily_pattern_min_fit`: 最小符合度阈值 (默认 0.0)
- `daily_pattern_min_strength`: 最小强度阈值 (默认 0.0)
- `daily_pattern_dominant_min_confidence`: 主导形态最小置信度 (默认 0.12)

---

### 4.4 信号层

#### signals/signal_calculator.py — SignalCalculator

计算六类子策略的开仓/平仓信号。

**震荡类信号** (超买超卖判断):

| 编号 | 策略 | 做空开仓信号 | 做多开仓信号 |
|------|------|-------------|-------------|
| 1 | RSI | RSI >= rsi_long_level (默认 70) | RSI <= rsi_short_level (默认 30) |
| 2 | Stoch RSI | Stoch K >= srsi_long_level (默认 75) | Stoch K <= srsi_short_level (默认 22) |
| 3 | MFI | MFI >= mfi_long_level (默认 80) | MFI <= mfi_short_level (默认 20) |

**趋势类信号** (方向变化判断):

| 编号 | 策略 | 做空信号 | 做多信号 |
|------|------|---------|---------|
| 4 | MACD | MACD 线下穿信号线 | MACD 线上穿信号线 |
| 5 | Supertrend | 趋势翻转为下跌 (1→-1) | 趋势翻转为上涨 (-1→1) |
| 6 | MA Cross | 均线 1 下穿均线 2 | 均线 1 上穿均线 2 |

**信号确认机制**:
```
开仓条件: 震荡类信号数 >= osc_signal_threshold AND 趋势类信号数 >= trend_signal_threshold
平仓条件: 对应的平仓信号（震荡或趋势退出）
```

**延迟参数**:
- 每个信号独立 `delay_*` 参数（如 `delay_rsi=6` 表示信号需持续 6 根 K 线才生效）
- `delay_exit`: 平仓后重新开仓的最短间隔（防止频繁交易）
- 实现: `since_entry` / `since_close` 计数器

**回测优化**: `precompute_sequences()` 将指标布尔序列预计算为 numpy 数组，避免每根 K 线重复创建 pandas Series。

---

### 4.5 回测引擎

#### backtest/backtest_runner.py — BacktestRunner

核心回放机制：**直接复用 `KlineMonitor.process_candle()`** — 不做重复实现。

**数据加载** (`run()`, `backtest_runner.py:1090+`):
1. 从 CSV.GZ 或 CSV 加载历史 K 线
2. 模块级 DataFrame LRU 缓存 (max 8 entries)
3. 按时间范围过滤数据窗口

**运行流程** (`run()`):
```
1. 加载 K 线 DataFrame
2. 创建（或复用）KlineMonitor 实例
3. 向 monitor.ti 注册回放函数，替代 API 调用:
   - monitor.ti._get_kline_data = 从预加载 DataFrame 读取
   - monitor.ti._get_current_price = 从 DataFrame 读取收盘价
4. 预计算全部指标序列 (一次性计算，避免逐根重复)
5. 预计算信号布尔序列 (precompute_sequences)
6. 逐根迭代 DataFrame，调用 monitor.process_candle()
7. 每个 event 检查 cancel_event (support optimize-live 取消)
8. 收集 trade_records, order_events
9. 计算净值曲线、最大回撤、胜率、盈利因子等
10. 生成中文 JSON 报告 + 订单 CSV
```

**fill_mode 支持**:
- **next_open** (默认): 信号触发后，按下一根 K 线开盘价成交
- **close**: 按当前 K 线收盘价成交

**Both 模式适配** (`_patched_process_candle_both_mode`):
回测时自动注入 direction context，让 monitor 知道当前是在评估 short 还是 long 方向的信号。

#### backtest/combined_backtest.py — Combined Backtest

用于 train/validation 双窗口回测:

```python
run_combined_backtest_replay(
    train_window,      # 训练窗口
    validation_window, # 验证窗口
    initial_capital    # 起始资金 = train 窗口期末净值
)
# → 合并两份 report + 合并 trade/order CSV
```

#### backtest/both_mode_runtime.py — Both Mode 运行时

**核心概念**: 虚拟仓位 (virtual position) vs 实际仓位 (actual position)

- **虚拟仓位**: short 和 long 各自独立维护，记录各自的 size, avg_price, stop_price, tp 等级
- **实际仓位**: 账户中的真实持仓 = 虚拟持仓的净头寸 (long - short)

**关键函数**:

| 函数 | 功能 |
|------|------|
| `open_virtual_position()` | 开虚拟仓位，维护 avg_price, stop_price, tp levels |
| `close_virtual_position()` | 平虚拟仓位，处理部分平仓 |
| `maybe_update_virtual_move_stop()` | TP 触发后移动止损价 |
| `apply_virtual_risk_rules()` | 对两个方向的虚拟仓位分别检查 TP/SL |
| `apply_virtual_target_position()` | 根据双方向信号计算目标实际持仓 |
| `process_candle_both_mode()` | Both 模式主处理流程 |

**process_candle_both_mode 流程** (both_mode_runtime.py:247+):
```
1. 对 short 和 long 方向分别计算信号配置文件
2. apply_virtual_risk_rules() — 检查虚拟仓位的 TP/SL
3. 分别评估 short 和 long 的开平仓信号
4. apply_virtual_target_position() — 将双方向信号合并为目标实际仓位
5. 比较目标仓位 vs 当前实际仓位 → open/close delta
6. 记录交易记录和订单事件
```

**目标仓位计算** (`apply_virtual_target_position`):
```
目标 = (long 虚拟仓位大小) - (short 虚拟仓位大小)
实际需执行 = 目标 - 当前实际持仓
正值 → 开多或平空
负值 → 开空或平多
```

---

### 4.6 参数优化器

#### optimization/auto_optimizer.py — SmartParameterOptimizer

**算法**: 多锚点重启坐标巡游爬山 (Multi-Anchor Restart Coordinate-Walk Hill Climbing)

```
初始化 → 生成 N 个随机锚点
    ↓
对每个锚点:
    循环:
        坐标巡游: 依次调整每个参数 ± neighbor_span_steps × step
        如无改善 → 随机扰动试探 (adaptive probe intensity)
        如改善 → 接受新位置，继续巡游
    ↓
输出 Top-K 最优参数组合
```

**评分体系** (多目标):

| 指标 | 默认权重 (balanced) | 说明 |
|------|-------------------|------|
| `net_profit_rate` | 0.55 | 净利润率 |
| `win_rate` | 0.15 | 胜率 |
| `profit_factor` | 0.20 | 盈利因子 (总盈利/总亏损) |
| `max_drawdown` | 0.10 | 最大回撤率 (负向指标) |

**双窗口评估**:
```
score = train_weight × score_train + validation_weight × score_validation - gap_penalty × |score_train - score_validation|
```
gap_penalty 惩罚过拟合（train 和 validation 分数差距大时扣分）。

**搜索空间类型**:
- **Flat (平铺)**: `parameters: { param_name: {type, min, max, step} }` — 通用模式
- **Grouped (分组)**: `parameters.common`, `parameters.short`, `parameters.long` — Both 模式独立优化

**参数类型支持**:
- `float`: 连续值，带 min, max, step
- `int`: 整数，带 min, max, step
- `choice`: 枚举，带 choices 列表
- `bool`: 布尔值

**初始化约束**: 对超买/超卖参数有顺序约束（如 `srsi_short_level < srsi_long_level`），通过 `_sanitize_params()` 自动纠正。

**Process Pool**: 使用 `ProcessPoolExecutor` 并行评估。worker 通过共享内存 cancel flag 支持 optimise-live 的中断信号。

**参数缓存**: LRU 缓存 (512 entries)，避免重复评估相同参数组合。

**模板对比**: `template_benchmark.py` 可批量运行 conservative/balanced/aggressive 三个模板并对比结果。

#### optimization/optimize_mode_config.py

`OptimizeModeConfig` 数据类，包含：
- `search_space_file`: 搜索空间 JSON 路径
- `trials`, `top_k`, `max_workers`: 搜索配置
- `target_cpu_utilization`: CPU 利用率目标 (默认 0.9)
- `max_drawdown_hard_limit` / `max_floating_loss_hard_limit`: 硬性上限

---

### 4.7 监控层

#### monitoring/monitor_components.py

**SharedCancelFlag** (`monitor_components.py:15-66`):
- 基于 `multiprocessing.shared_memory` 的跨进程取消信号
- 创建者持有 `_owner=True` 有权 `unlink()`
- 用于 optimize-live 中取消正在运行的 parallel evaluation

**MonitorPositionExecutor** (`monitor_components.py:68-462`):
- `place_short_order()` / `place_long_order()`: 开仓下单
- `close_short_position()` / `close_long_position()`: 平仓下单
- 自动计算手续费 → `equity` 更新
- 创建 `trade_records` 条目
- 推送 Webhook (POST) + StrategyPromo 事件
- 支持**部分平仓** (partial close)
- `_update_floating_pnl()`: 实时浮动盈亏曲线追踪

**MonitorOptimizeLiveCoordinator** (`monitor_components.py:464-900`):
optimize-live 模式的完整工作流：

```
1. 启动: 创建 worker thread + 全局锁 + monitor 锁
2. 等待 position 完全清空（关闭全部虚拟持仓）
3. acquire 全局锁 → acquire monitor 锁 → run_cycle()
4. run_cycle():
   a. 创建 SharedCancelFlag
   b. 在 worker thread 中运行 SmartParameterOptimizer
   c. 监视进度（heartbeat thread）
   d. 完成后: save_params_to_json() → load_directional_params_from_json()
   e. advanced virtual position state 到新的参数参数
5. release 锁
6. 等待下次触发（下一次 position 全平后）
```

**跳过去重**: optimize-live 会记录哪些方向最近已优化过，如果短时间内再次触发则跳过。

**MonitorScheduler** (`monitor_components.py:902-1028`):
- `is_candle_close()`: 检查当前时间是否为 K 线边界（整点收盘）
- `wait_for_first_candle_close()`: 等待到下一个 K 线收线时间
- `schedule_timer()`: 在 K 线收线时刻设置 Timer
- `run()`: 主循环 bootstrap → schedule → 等待 timer 触发 → 调用 process_candle() → schedule 下一次
- `stop()`: 取消 timer + 清理资源

#### monitoring/monitor_signal_formatter.py

将内部信号状态格式化为人类可读的水平条和标签：

```
趋势[MACD|ST|MA]  osc[RSI|SRSI|MFI]  裸K[方向|形态|拟合度|强度|概率]
空头信号权重=2    趋势=1  震荡=1   方向=空
```

提供 `signal_state_label()` 返回 "空/多/双/无" 标签。

#### monitoring/monitor_runtime_summary.py

Live 启动时打印摘要信息：
- bootstrap 回放统计 (bar count, 时间跨度)
- 当前持仓状态
- 净值
- 已关闭的 trades 汇总 (胜率, 净利润)
- 浮动盈亏估算

---

### 4.8 交易管理层

#### trading/pair_runtime_manager.py — TradingPairRuntimeManager

动态交易对管理器，支持在进程运行时增加/删除/修改交易对配置：

```
Main Loop:
    1. scan trading_pairs/ (可配间隔, 默认 60s)
    2. 对比当前运行状态:
       - 新文件 → start_monitor()
       - 已删除文件 → stop_monitor()
       - 配置变更 → restart_monitor()
    3. sleep → 回到 1
```

**配置签名**: 通过 JSON 序列化 `vars(cfg)` 计算签名，忽略市场牛熊区间等动态字段。签名变化才触发重启。

**延迟重启**: 如果当前有活跃 position，推迟到全部平仓后再重启。旧 monitor 标记为 `_pending_restart`，平仓后自动执行切换。

#### trading/webhook_payloads.py

Webhook payload 构建和标准化：
- `safe_float()`: 安全的 float 转换
- `normalize_webhook_target_accounts()`: 将 string/iterable 转为 tuple
- `build_trade_probability_payload()`: 构建包含概率和日线形态数据的 Webhook 负载

#### trading/strategy_promo_bridge.py — StrategyPromoEventBridge

桥接到 StrategyPromo 项目，通过写入 JSONL 文件发送事件：
- 事件类型: `open`, `add` (加仓), `close`, `regime_switch`
- 元数据: symbol, pair_name, trade_direction, 价格, 数量, PnL 等
- 线程安全: threading.Lock 保护文件写入

---

### 4.9 风控层

#### live_risk_monitor.py — LiveRiskMonitor

**设计原因**: 实盘中 K 线级处理间隔长 (4H)，价格可能在 K 线之间剧烈波动触发 TP/SL。

**机制**:
```
Polling Thread (独立线程):
    每隔 1 秒:
        对所有注册的 symbol 从 Binance REST API 拉取实时价格
    每隔 5 秒:
        对所有注册的 owner (KlineMonitor 实例):
            检查 single-direction 和 both-mode 虚拟仓位的 TP/SL
            如触发 → 调用 owner.pe.close_long/short_position()
            发送 webhook
```

**Move-stop 逻辑**: 与回测 engine 保持一致 — 当价格触及 TP 水平后，自动上移/下移止损价。

**状态文件**: 将运行状态定期写入 `runtime/live_risk_status.json`，方便外部监控。

**Owner 管理**:
- `register_owner()`: KlineMonitor 开仓后注册
- `unregister_owner()`: KlineMonitor 平仓后注销
- 基于 `id(owner)` 的弱引用管理

---

## 5. 策略体系

### 5.1 六大子策略总览

```
┌─────────────────────────────────────────────┐
│              六策略融合体系                    │
├───────────────┬───────────────┬─────────────┤
│   震荡类 (3)   │   趋势类 (3)   │  日线形态     │
│  RSI / SRSI /  │  MACD / ST /  │  10种K线形态  │
│    MFI        │  MA Cross     │  概率模型     │
├───────────────┴───────────────┴─────────────┤
│          双重确认 → 信号触发                   │
│   震荡条件 >= osc_threshold (默认1)           │
│   AND 趋势条件 >= trend_threshold (默认1)     │
├─────────────────────────────────────────────┤
│  × 日线形态概率映射 → 最终仓位大小             │
└─────────────────────────────────────────────┘
```

### 5.2 信号权重系统

每个子策略产生 boolean 信号，汇总为：

```python
total_short_weight = sum(
    use_RSI * RSI_short_signal +
    use_SRSI * SRSI_short_signal +
    use_MFI * MFI_short_signal
)

total_trend_weight = sum(
    use_MACD * MACD_short_signal +
    use_ST * ST_short_signal +
    use_MA * MA_short_signal
)
```

### 5.3 仓位计算

```python
probability = daily_pattern.bullish_probability or bearish_probability
# 0.5 - 1.0 范围

ratio = probability_to_position_ratio(probability, scale)
# scale 默认 2.0, 映射 0.5→1.0 的概率到 0→1.0 的仓位比率

quantity = (equity * leverage * ratio) / price
quantity = normalize_quantity(quantity, symbol)
# 按最小交易单位 (step size) 取整
```

---

## 6. 运行模式

### 模式对比

| 特性 | live | backtest | optimize | optimize-live |
|------|------|----------|----------|---------------|
| K 线源 | Binance REST | CSV 文件 | CSV 文件 | Binance REST + CSV |
| 订单执行 | 真实 Webhook | 模拟 (回放) | 模拟 | 真实 Webhook |
| 参数搜索 | ❌ | ❌ | ✅ | ✅ (自动触发) |
| 风控 (TP/SL) | LiveRiskMonitor | 回测内置 | 回测内置 | LiveRiskMonitor |
| 数据归档更新 | ✅ | ❌ | ❌ | ✅ |
| 市场区间 | 动态计算 | 使用配置固定 | 使用配置固定 | 动态计算 |
| optimize-live 触发 | — | — | — | 每次全平仓后 |

### optimize-live 详细流程

```
1. KlineMonitor live 模式正常运行
2. 每次 process_candle() 后检查虚拟仓位是否完全清空
3. 如果全空 → 触发 MonitorOptimizeLiveCoordinator.run_cycle()
4. 检查是否最近已优化 (跳过重复)
5. 使用市场区间计算的训练/验证窗口运行 SmartParameterOptimizer
6. 将最优参数写入 trading_pairs/params/*.json
7. 重新加载参数到当前配置
8. 推进虚拟仓位状态 (取用新参数)
9. 继续 live 模式运行
```

### 启动参数速查

```bash
# 实时交易
python multistrategy.py --mode live --all-enabled-pairs

# 优化-实盘 (auto re-optimize)
python multistrategy.py --mode optimize-live --search-space backtest/search_spaces/balanced.json --max-workers 4

# 手动参数优化
python multistrategy.py --optimize --pair btc_lead_short --trials 120 --top-k 20 --max-workers 4

# 历史回测
python multistrategy.py --mode backtest --pair btc_um_short

# 模板对比
python template_benchmark.py --trials 40 --max-workers 4

# 动态监听模式
python multistrategy.py --watch-pairs --pair-scan-seconds 60
```

---

## 7. Both 模式详解

### 7.1 核心原理

Both 模式同时管理 **short 虚拟仓位** 和 **long 虚拟仓位**，但**实际交易所账户只有单一持仓**（净头寸）。

```
虚拟 state:
  _virtual_short: {size: 0.5, avg_price: 62000, stop_price: 63000, ...}
  _virtual_long:  {size: 0.8, avg_price: 61800, stop_price: 58800, ...}

实际账户:
  net = long - short = 0.8 - 0.5 = +0.3 (净多头)
  执行: open_long(0.3) 或 close_short(0.3)
```

### 7.2 参数独立性

Both 模式下 short 和 long 各自有独立的：
- 策略参数 (RSI 阈值、MACD 周期等)
- 止损参数 (stoploss_perc, move_stoploss_factor)
- 止盈参数 (max_tp, short_profit_perc)
- 日线形态权重
- 延迟参数

通过 `common_params` / `short_params` / `long_params` 三层分离实现。

### 7.3 状态管理

`core/virtual_position_state.py` 定义的虚拟仓位状态字典：
```python
{
    'size': 0.0,           # 虚拟持仓大小
    'initial_size': 0.0,   # 初始持仓 (用于计算)
    'avg_price': 0.0,      # 平均成交价
    'entry_time': None,    # 入场时间
    'stop_price': 0.0,     # 当前止损价
    'next_tp': 0.0,        # 下一个止盈价
    'filled_tp_levels': set(),  # 已触发的止盈等级
    'since_entry': 0,      # 入场后 K 线数
    'since_close': 0,      # 平仓后 K 线数 (控制 delay_exit)
}
```

### 7.4 止盈止损 (Both 模式)

**止盈**: 分级止盈 — `max_tp` 个等级，每个等级触发条件:
```
short: current_price <= avg_price * (1 - tp_level * short_profit_perc)
long:  current_price >= avg_price * (1 + tp_level * short_profit_perc)
```

每触发一级止盈，平掉 `short_profit_qty × 剩余数量`。

**移动止损**: 每触发一个止盈等级，止损价自动向有利方向移动 `move_stoploss_factor × short_profit_perc`。

---

## 8. 配置系统详解

### 8.1 交易对配置文件格式

`trading_pairs/btc.lead.json` 示例结构：

```json
{
  "name": "带单",           // 显示名称
  "enabled": true,          // 是否启用
  "run_mode": "optimize-live",
  "symbol": "BTC/USDT",
  "kline_timeframe_minutes": 240,
  "initial_capital": 2725,
  "trade_direction": "both",
  "position_ratio": 1,
  "webhook_profiles_dir": "TradeSync/accounts",
  "webhook_target_account_files": ["okx.lead.json", "binance.lead.json", ...],
  "optimize_params_file_short": "params/btc_combine_lead_public.short.optimize_params.json",
  "optimize_params_file_long": "params/btc_combine_lead_public.long.optimize_params.json",
  "backtest_data_file": "backtest/backtest_data_BTCUSDT_4h_daily_20191231-20260521.csv.gz",
  "market_regime_boundaries_file": "backtest/market_regime_boundaries.json",
  "live_state_start": {"year": 2026, "month": 6, "day": 4, "hour": 23, "minute": 59},
  "backtest_time_range": {
    "start": {"year": 2021, "month": 11, "day": 9, "hour": 23, "minute": 59},
    "end": {"year": 2022, "month": 11, "day": 21, "hour": 23, "minute": 59}
  },
  "validation_time_range": {
    "start": {"year": 2025, "month": 10, "day": 5, "hour": 23, "minute": 59},
    "end": {"year": 2026, "month": 12, "day": 31, "hour": 23, "minute": 59}
  }
}
```

**文件规则**:
- 只有 `.json` 文件被加载
- 以 `_` 开头的文件被排除（模板文件）
- `enabled: false` 的文件在 `--all-enabled-pairs` 模式下被排除

### 8.2 搜索空间配置

`backtest/search_spaces/balanced.json`:
```json
{
  "trials": 120,                  // 总迭代次数
  "seed": 42,
  "exploration_ratio": 0.5,       // 探索/利用平衡
  "restart_anchor_count": 4,      // 爬山重启锚点数
  "min_trades": 8,                // 最少平仓笔数筛选
  "train_weight": 0.6,            // 训练权重
  "validation_weight": 0.4,       // 验证权重
  "validation_gap_penalty": 0.15, // 过拟合惩罚
  "train_window": { ... },        // 训练窗口
  "validation_window": { ... },   // 验证窗口
  "objective_weights": {          // 多目标权重
    "net_profit_rate": 0.55,
    "win_rate": 0.15,
    "profit_factor": 0.2,
    "max_drawdown": 0.1
  },
  "parameters": {                 // 搜索参数定义
    "stoploss_perc": {
      "type": "float",
      "min": 0.03,
      "max": 0.09,
      "step": 0.0025,
      "neighbor_span_steps": 3
    }
  }
}
```

### 8.3 三模板对比

| 特征 | conservative | balanced | aggressive |
|------|-------------|----------|------------|
| trials | 150 | 120 | 180 |
| min_trades | 12 | 8 | 6 |
| net_profit_rate 权重 | 0.35 | 0.55 | 0.70 |
| max_drawdown 权重 | 0.20 | 0.10 | 0.05 |
| exploration_ratio | 0.45 | 0.50 | 0.60 |
| validation_gap_penalty | 0.25 | 0.15 | 0.10 |
| 止损范围 | 更宽保守 | 适中 | 更窄激进 |
| 策略 | 低回撤优先 | 收益与风险平衡 | 收益优先 |

---

## 9. 数据流图

### 9.1 实盘模式数据流

```
Binance REST API
      │
      ▼
┌─────────────────┐
│ get_kline_data()  │ ← ─ ─ ─ LocalKlineArchive (增量存档)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ calculate_all_   │
│  indicators()    │ ← ─ DailyPatternAnalyzer (日线形态)
└────────┬────────┘
         │ indicators dict
         ▼
┌─────────────────┐
│ calculate_       │
│  signals()       │
└────────┬────────┘
         │ signal dict
         ▼
┌─────────────────┐
│ process_candle() │
│  (trade decision)│
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌──────────┐
│Webhook│ │Strategy   │
│(Trade │ │Promo      │
│Sync)  │ │(JSONL)    │
└───────┘ └──────────┘
         │
         ▼
┌──────────────────┐
│ LiveRiskMonitor   │ (独立线程)
│  (TP/SL polling)  │
└──────────────────┘
```

### 9.2 回测模式数据流

```
CSV.GZ / CSV 文件
      │
      ▼
┌─────────────────┐
│ BacktestRunner   │
│  load CSV → DF   │ ← LRU cache (max 8)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 向 monitor 注册   │
│ 回放 K 线/价格    │
│ 函数             │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 预计算全部指标    │ → 一次性 compute
│ 预计算信号序列   │ → precompute_sequences
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 逐 bar 循环       │
│  monitor.        │
│  process_candle()│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 组合回测结果     │
│  (combined/     │
│   train+val)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 输出:            │
│  JSON report    │
│  CSV orders     │
│  净值曲线        │
└─────────────────┘
```

### 9.3 Optimize-Live 数据流

```
Live 模式正常运行
       │
       ├── K 线 → process_candle() → 信号 → Webhook → 交易
       │
       └── 全平仓触发 → MonitorOptimizeLiveCoordinator
                              │
                              ▼
                     ┌──────────────────┐
                     │ 获取全局锁         │
                     │ (跨 monitor 互斥) │
                     └────────┬─────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │ 刷新牛熊区间       │
                     │ → 计算最新训练/    │
                     │   验证窗口        │
                     └────────┬─────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │ SmartParameter    │
                     │ Optimizer         │
                     │ (Process Pool)    │
                     └────────┬─────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │ save_params_to    │
                     │ _json()           │
                     │ → params/*.json   │
                     └────────┬─────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │ load_directional  │
                     │ _params_from_json │
                     │ → 当前 config 更新 │
                     └────────┬─────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │ 释放锁             │
                     │ 继续 live 运行     │
                     └──────────────────┘
```

---

## 10. 关键设计决策

### 10.1 回测复用实盘代码

**设计**: `BacktestRunner` 不是独立的回测逻辑，而是通过**方法注入 (monkey patching)** 复用 `KlineMonitor.process_candle()`。

**原因**: 避免回测逻辑与实盘逻辑分叉，保证回测结果的真实性。

**关键 injection**:
```python
monitor.ti._get_kline_data = lambda: read from DataFrame
monitor.ti._get_current_price = lambda: DataFrame.iloc[idx].close
monitor.bt.get_fill_timestamp = lambda: DataFrame timestamp
monitor._pre_evaluate_context = direction context (both mode)
```

### 10.2 LiveRiskMonitor 解耦

**设计**: TP/SL 检查从 `process_candle()` 中分离到独立的 `LiveRiskMonitor` 线程。

**原因**: 4H K 线间隔期间价格可能大幅波动，不能等到 K 线收线再检查止损。

### 10.3 牛熊区间自动切换

**设计**: live/optimize-live 模式下，训练/验证窗口自动按 `market_regime_boundaries.json` 计算。

**原因**: 市场周期变化时，历史模式的有效性随之改变。自动切换确保优化始终使用相关的历史区间。

### 10.4 Both 模式虚拟化

**设计**: Both 模式内部短/长各维护虚拟仓位，实际执行净头寸变动。

**优势**: 
- 短/长策略可独立优化
- 避免不必要的换向交易
- 止盈止损各方向独立管理

### 10.5 多锚点坐标巡游优化

**设计**: 不需要导数的概率搜索算法，支持任意参数组合。

**优势**:
- 不依赖梯度（参数之间关系非线性）
- 天然支持离散/连续混合参数
- 重启机制避免局部最优
- 多窗口评估减少过拟合

### 10.6 Worker 预算管控

**设计**: CPU 利用率限制 + 预留核心数 (`_resolve_optimizer_worker_budget`)。

**原因**: optimize-live 在实盘运行时进行参数搜索，不能耗尽所有 CPU 影响 K 线处理。

### 10.7 配置文件签名检测

**设计**: `TradingPairRuntimeManager` 通过 JSON 序列化比较配置签名来检测变更。

**忽略字段**: 牛熊区间、回测窗口等动态刷新字段被排除在签名外，避免误触发重启。

### 10.8 时区规范

- **内部存储**: UTC
- **K 线显示**: `Asia/Shanghai` (UTC+8, 北京时间)
- **日线聚合**: 可配置时区 (默认 UTC)
- **日志时间**: 北京时间

### 10.9 参数文件写入安全性

使用**原子写入** (`os.replace`): 先写临时文件，再 rename 覆盖，防止写入中断导致参数文件损坏。

---

## 附录 A: 文件大小与复杂度

| 文件 | 行数 | 复杂度 |
|------|------|--------|
| multistrategy.py | 3132 | ⭐⭐⭐⭐⭐ KlineMonitor 核心 |
| auto_optimizer.py | 2561 | ⭐⭐⭐⭐⭐ 优化器 + 评估 + 缓存 |
| backtest_runner.py | 1365 | ⭐⭐⭐⭐ 回测引擎 |
| config.py | 1187 | ⭐⭐⭐⭐ 配置系统 |
| monitor_components.py | 1028 | ⭐⭐⭐⭐ 调度/执行/协调 |
| indicators.py | 727 | ⭐⭐⭐ 指标计算 |
| live_risk_monitor.py | 662 | ⭐⭐⭐ 风控监听 |
| multistrategy_cli.py | 583 | ⭐⭐⭐ CLI |
| daily_pattern_analyzer.py | 579 | ⭐⭐⭐ 日线形态 |
| signal_calculator.py | 391 | ⭐⭐ 信号计算 |
| both_mode_runtime.py | 371 | ⭐⭐ Both 模式 |
| combined_backtest.py | 321 | ⭐⭐ 组合回测 |
| pair_runtime_manager.py | 288 | ⭐⭐ 交易对管理 |
| kline_archive.py | 285 | ⭐⭐ K线归档 |

---

## 附录 B: 环境变量与文件路径

| 路径 | 用途 |
|------|------|
| `BStrategy/trading_pairs/` | 交易对配置目录 |
| `BStrategy/trading_pairs/params/` | 优化后参数文件 |
| `BStrategy/backtest/output/` | 回测报告输出 |
| `BStrategy/logs/pairs/` | 运行日志 |
| `BStrategy/runtime/` | 运行时状态文件 |
| `BStrategy/backtest/search_spaces/` | 参数模板 |
| `../TradeSync/accounts/` | 交易账号配置 (跨项目引用) |
| `../StrategyPromo/runtime/` | 社交推送桥接 (跨项目引用) |

---

## 附录 C: 常见场景操作指南

### 新增一个交易对

1. 复制 `BStrategy/trading_pairs/_template.pair.json` 为新的 JSON 文件
2. 修改 `symbol`, `name`, `initial_capital`, `trade_direction`, `webhook_target_account_files` 等
3. 设置 `optimize_params_file_short/long` 路径
4. 运行 `python multistrategy_cli.py --pair 新文件名` 启动

### 调整交易策略参数

1. 手动编辑 `BStrategy/trading_pairs/params/*.optimize_params.json`
2. 或运行 `python multistrategy.py --optimize --pair 名称` 自动搜索

### 查看回测结果

```bash
python multistrategy.py --backtest --pair btc.lead.json
# 报告在: BStrategy/backtest/output/
# *_replay_report.json: 详细统计
# *_replay_orders.csv: 完整订单记录
```

### 排查 optimize-live 行为

1. 检查 `BStrategy/logs/pairs/` 中对应的日志文件
2. 查看日志中的 `skipped optimize-live[short/long]` 记录
3. 如果优化被跳过，检查是否该方向最近已优化过

---

*文档生成日期: 2026-06-08*
