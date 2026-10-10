# -*- coding: utf-8 -*-
"""系统功能骨架 — 人工维护的功能/支持状态地图（供 /skeleton 页面渲染）。

设计：
- 纯数据模块（无 IO/无第三方依赖），随开发进度手工更新；
- 每个节点 = 一项功能/服务；status 取值见 STATUS_LABELS；
- 流水线（FLOWS）描述跨模块的主要链路（展示用文案链）；
- `view_model()` 汇总为模板可直接渲染的结构。

维护约定：改动系统能力（新增服务/上线/退役/暂缓）时同步本文件与 UPDATED_AT。
"""
from __future__ import annotations

from collections import Counter

SCHEMA_VERSION = 1
UPDATED_AT = '2026-10-11'

STATUS_LABELS = {
    'live': '已上线',
    'research': '研究可用',
    'idle': '有意停用',
    'paused': '暂缓',
    'planned': '规划中',
    'retired': '已退役',
}

LAYERS = [
    {
        'id': 'interaction',
        'title': '① 交互面 · 手机 → Mac',
        'subtitle': '全功能远控与推送（无入站端口）',
        'nodes': [
            {'id': 'uu_remote', 'name': 'UU远程', 'status': 'live',
             'desc': '手机 ↔ Mac 终端全功能远控（出站式）', 'caps': ['opencode 会话', '随时启停']},
            {'id': 'opencode', 'name': 'opencode · 0-9 agents', 'status': 'live',
             'desc': '主控制面：规划/开发/审核/验证/部署/知识库/收工', 'caps': ['手机交互', '工作流编排']},
            {'id': 'dingtalk', 'name': '钉钉通知', 'status': 'live',
             'desc': '后台任务与告警推送（ops.notify）', 'caps': ['研究完成', '健康告警']},
            {'id': 'botstation', 'name': 'botstation', 'status': 'retired',
             'desc': '原 Telegram 控制通道；2026-10-09 退役（Archive）', 'caps': ['能力迁至 opencode + ops/']},
        ],
    },
    {
        'id': 'ops',
        'title': '② 后台面 · Mac ops/launchd',
        'subtitle': '无人值守：定时 + 看护 + 通知',
        'nodes': [
            {'id': 'ops_kb', 'name': 'kb-index', 'status': 'live', 'launchd': 'com.bot.kb-index',
             'desc': '每日 03:30 重建 KnowledgeBase 索引', 'caps': ['launchd']},
            {'id': 'ops_research', 'name': 'research-weekly', 'status': 'live', 'launchd': 'com.bot.research-weekly',
             'desc': '周日 04:00 参数研究周批（research runner）', 'caps': ['失败重试', '钉钉告警']},
            {'id': 'ops_health', 'name': 'health_watch', 'status': 'live', 'launchd': 'com.bot.health',
             'desc': '每 5 分钟 Mac 进程/磁盘/内存看护', 'caps': ['状态去抖']},
            {'id': 'ops_briefing', 'name': 'briefing', 'status': 'live', 'launchd': 'com.bot.briefing',
             'desc': '每日 08:30 本地模型汇总系统状态 → 钉钉', 'caps': ['qwen3:8b / Bonsai 27B', '全本地生成']},
            {'id': 'ops_xdigest', 'name': 'xdigest', 'status': 'live', 'launchd': 'com.bot.xdigest',
             'desc': '每日 21:00 X 前沿情报精选（数据/技术/可学习）→ 钉钉',
             'caps': ['17 账号池（试用制）', 'AI 精选（API+本地降级）']},
            {'id': 'ops_aiservice', 'name': 'aiservice (Mac)', 'status': 'live', 'launchd': 'com.bot.aiservice',
             'desc': 'Mac 本机 AI 网关（DeepSeek；xdigest 等本机消费者）',
             'caps': ['Key 集中', 'JSON 修复', '用量日志']},
            {'id': 'ops_research_batch', 'name': 'research-batch', 'status': 'live', 'launchd': 'com.bot.research-batch',
             'module': 'research/batch.py',
             'desc': '按批次计划（research/plans/*.json）串行深度研究队列；每日 01:00 触发', 'caps': ['单实例锁', '断点续跑', '钉钉回执']},
            {'id': 'm09', 'name': 'M-09 常驻自愈', 'status': 'planned',
             'desc': '断电自启 / 崩溃自恢复的完整演练', 'caps': ['UPS（建议）']},
        ],
    },
    {
        'id': 'research',
        'title': '③ 计算面 · Mac research/',
        'subtitle': '参数研究流水线（台账 → 评选）',
        'nodes': [
            {'id': 'catalog', 'name': '数据清单 catalog', 'status': 'research', 'module': 'KlinesData/catalog.py',
             'desc': 'K 线文件清单 + sha256 / rows / 首末时间', 'caps': ['BTC 1h/1d/3d/1w', 'ETH 仅 1h（待补齐）']},
            {'id': 'ledger', 'name': '选优台账', 'status': 'research', 'module': 'research/ledger.py',
             'desc': '全量 trial 结果 + 便宜因子（jsonl.gz）', 'caps': ['已跑通 155,647 组']},
            {'id': 'stage_a', 'name': 'Stage A 筛选', 'status': 'research', 'module': 'research/selection.py',
             'desc': '周期处方自适应闸门 → 评分 → 去重 → top 3%', 'caps': ['155k → 366 → 6']},
            {'id': 'stage_b', 'name': 'Stage B 电池', 'status': 'research', 'module': 'research/stress.py',
             'desc': '折外一致性 + 成本×1.5 + 邻域 ±1 档', 'caps': ['27s/6 候选', '评估缓存']},
            {'id': 'stage_c', 'name': 'Stage C 分级', 'status': 'research', 'module': 'research/selection_report.py',
             'desc': 'A/B/C 分级 + report.md + candidates.jsonl', 'caps': ['首跑 A3/B2/C1']},
            {'id': 'review', 'name': '候选评审材料', 'status': 'research', 'module': 'research/review.py',
             'desc': 'review.md（证据/参数/应用清单）+ 可应用参数文件 + 决定记录（annotate）',
             'caps': ['人工评审门']},
            {'id': 'pipeline', 'name': '优选流水线（SOP）', 'status': 'research', 'module': 'research/pipeline.py',
             'desc': '预检→全链→校验→回执（一条命令）；verify / dry-run',
             'caps': ['标准参数 pipeline_standard.json']},
            {'id': 'auto_select', 'name': '自动串联', 'status': 'research', 'module': 'research/auto_select.py',
             'desc': '选优结束自动 stage A 并推送摘要', 'caps': ['BOT_AUTO_SELECT']},
            {'id': 'm07b', 'name': 'M-07b walk-forward', 'status': 'research', 'module': 'research/walkforward.py',
             'desc': '折内重拟合 + 折外拼接 + 参数漂移 + lockbox 一次性揭盲',
             'caps': ['1w 需 train≥30 月', 'WF- 产物不自动清理']},
        ],
    },
    {
        'id': 'execution',
        'title': '④ 执行面 · 服务器（实时交易）',
        'subtitle': '下单 / 路由 / 展示 / 发帖',
        'nodes': [
            {'id': 'bstrategy', 'name': 'BStrategy', 'status': 'live', 'service': 'bstrategy',
             'desc': '4H 多策略带单（实盘）', 'caps': ['止损闭环', '仓位对齐']},
            {'id': 'tradesync', 'name': 'TradeSync', 'status': 'live', 'service': 'tradesync',
             'desc': '下单网关 / 账号路由', 'caps': ['Binance/Bybit/OKX/Bitget']},
            {'id': 'autodca', 'name': 'AutoDCA', 'status': 'idle', 'service': 'autodca',
             'desc': '定投执行（计划已到期，有意停用）', 'caps': ['需手动恢复']},
            {'id': 'web', 'name': 'Web 面板', 'status': 'live', 'service': 'web',
             'desc': '本页所在：交易/帖子/盈亏/系统骨架', 'caps': ['登录门禁']},
            {'id': 'promo', 'name': 'Promo', 'status': 'live', 'service': 'promo',
             'desc': '交易帖自动发布 + 内容资产', 'caps': ['AI 主笔', '屏蔽降级']},
        ],
    },
    {
        'id': 'cognition',
        'title': '⑤ 认知面 · AI / 知识',
        'subtitle': '周期判断与知识沉淀',
        'nodes': [
            {'id': 'alphaengine', 'name': 'AlphaEngine', 'status': 'live', 'service': 'alphaengine',
             'desc': '周期 / alpha 分析（AI + 知识库）', 'caps': ['影子账本', '节奏门控（关）']},
            {'id': 'aiservice', 'name': 'AIService', 'status': 'live', 'service': 'aiservice',
             'desc': '统一 AI 网关（模型/Key/用量集中）', 'caps': ['Key 轮换', '用量日志']},
            {'id': 'kb', 'name': 'KnowledgeBase + kbbot', 'status': 'live', 'service': 'kbbot',
             'desc': '知识库：评估入库 / 条目 / 项目卡', 'caps': ['kb_publish', '索引']},
            {'id': 'ai_shadow', 'name': 'AI 影子评估', 'status': 'live',
             'desc': 'BStrategy 订单事件独立评估（不参与决策）', 'caps': ['命中率基线待出']},
            {'id': 'rag', 'name': 'RAG 注入（C-05）', 'status': 'planned',
             'desc': 'KB 检索注入 AI 提示词', 'caps': []},
        ],
    },
    {
        'id': 'data',
        'title': '⑥ 数据面',
        'subtitle': '行情与回测数据',
        'nodes': [
            {'id': 'datafeed', 'name': 'DataFeed', 'status': 'live', 'service': 'datafeed',
             'desc': 'K 线归档 / /klines / /price', 'caps': ['1d 归档', '内存缓存']},
            {'id': 'klinesdata', 'name': 'KlinesData', 'status': 'research',
             'desc': '全历史数据准备（fapi + Vision 交叉核对）', 'caps': ['BTC 四周期全历史', 'ETH 待补齐']},
        ],
    },
    {
        'id': 'safety',
        'title': '⑦ 安全与监控',
        'subtitle': '告警 / 对账 / 安全债',
        'nodes': [
            {'id': 'sentinel', 'name': 'Sentinel', 'status': 'live', 'service': 'sentinel',
             'desc': '订单轻量回放对账 + 六闸门 + 全程序巡检', 'caps': ['钉钉 fact-only']},
            {'id': 'login_guard', 'name': '登录门禁', 'status': 'live',
             'desc': 'Web 默认必须登录（本页亦受保护）', 'caps': []},
            {'id': 'secrets', 'name': '密钥轮换 / 收口', 'status': 'paused',
             'desc': 'A-02 / A-03 / B2（2026-10-07 暂缓）', 'caps': ['待重启']},
        ],
    },
]

FLOWS = [
    {'id': 'order', 'name': '下单链路', 'status': 'live',
     'path': ['BStrategy / AutoDCA', 'TradeSync', '交易所 API'], 'note': '执行语义路由'},
    {'id': 'event', 'name': '事件链路', 'status': 'live',
     'path': ['BStrategy / AlphaEngine', 'Promo', 'Web / Binance Square'], 'note': 'HTTP + JSONL 兜底'},
    {'id': 'ai', 'name': 'AI 链路', 'status': 'live',
     'path': ['AlphaEngine / BStrategy / Promo', 'AIService', 'DeepSeek'], 'note': 'Key/用量集中'},
    {'id': 'market', 'name': '数据链路', 'status': 'live',
     'path': ['DataFeed', 'AlphaEngine'], 'note': '1d K 线上下文'},
    {'id': 'monitor', 'name': '监控链路', 'status': 'live',
     'path': ['Sentinel 回放对账', '六闸门/巡检', '钉钉'], 'note': '异常/新订单才推'},
    {'id': 'research', 'name': '研究链路', 'status': 'research',
     'path': ['选优（台账）', 'Stage A', 'Stage B', 'Stage C 候选池', '人工评审'], 'note': '绝不自动上线'},
    {'id': 'backoffice', 'name': '后台链路', 'status': 'live',
     'path': ['launchd', 'ops 任务', '钉钉'], 'note': '定时/告警'},
    {'id': 'interaction', 'name': '交互链路', 'status': 'live',
     'path': ['手机 UU远程', 'opencode', 'Mac / 服务器'], 'note': '出站式，无入站端口'},
]


EXTERNAL_NODES = [
    {'id': 'ext_phone', 'label': '📱 手机'},
    {'id': 'ext_exchange', 'label': '🏦 交易所 API'},
    {'id': 'ext_deepseek', 'label': '☁️ DeepSeek'},
    {'id': 'ext_square', 'label': '🌐 Binance Square'},
    {'id': 'ext_review', 'label': '👤 人工评审（红线）'},
]

EDGES = [
    {'from': 'ext_phone', 'to': 'uu_remote'},
    {'from': 'uu_remote', 'to': 'opencode'},
    {'from': 'opencode', 'to': 'ledger', 'label': '选优', 'style': 'dashed'},
    {'from': 'ledger', 'to': 'stage_a'},
    {'from': 'stage_a', 'to': 'stage_b'},
    {'from': 'stage_b', 'to': 'stage_c'},
    {'from': 'stage_c', 'to': 'ext_review', 'label': '绝不自动上线', 'style': 'dashed'},
    {'from': 'bstrategy', 'to': 'tradesync'},
    {'from': 'autodca', 'to': 'tradesync', 'label': '计划停用', 'style': 'dashed'},
    {'from': 'tradesync', 'to': 'ext_exchange'},
    {'from': 'bstrategy', 'to': 'promo', 'label': '交易事件'},
    {'from': 'alphaengine', 'to': 'promo', 'label': '分析帖'},
    {'from': 'promo', 'to': 'ext_square'},
    {'from': 'promo', 'to': 'web', 'label': '内部面板'},
    {'from': 'alphaengine', 'to': 'aiservice'},
    {'from': 'bstrategy', 'to': 'aiservice'},
    {'from': 'promo', 'to': 'aiservice'},
    {'from': 'aiservice', 'to': 'ext_deepseek'},
    {'from': 'datafeed', 'to': 'alphaengine', 'label': '1d 上下文'},
    {'from': 'sentinel', 'to': 'dingtalk', 'label': '告警'},
    {'from': 'ops_kb', 'to': 'kb'},
    {'from': 'ops_research', 'to': 'ledger', 'label': '周批'},
    {'from': 'ops_research_batch', 'to': 'pipeline', 'label': '批次队列'},
    {'from': 'ops_health', 'to': 'dingtalk'},
    {'from': 'ops_xdigest', 'to': 'ops_aiservice', 'label': 'AI 精选', 'style': 'dashed'},
    {'from': 'ops_aiservice', 'to': 'ext_deepseek'},
]


def build_mermaid() -> str:
    """由 LAYERS/EXTERNAL_NODES/EDGES 生成 Mermaid 流程图源码。"""
    lines = [
        '%%{init: {"flowchart": {"curve": "basis", "nodeSpacing": 30, "rankSpacing": 55, "useMaxWidth": false}}}%%',
        'flowchart TB',
        '    subgraph EXT["外部系统"]',
    ]
    for node in EXTERNAL_NODES:
        lines.append(f'        {node["id"]}(["{node["label"]}"])')
    lines.append('    end')
    for layer in LAYERS:
        lines.append(f'    subgraph {layer["id"]}["{layer["title"]}"]')
        for node in layer.get('nodes') or []:
            lines.append(f'        {node["id"]}["{node["name"]}"]')
        lines.append('    end')
    for edge in EDGES:
        arrow = '-.->' if edge.get('style') == 'dashed' else '-->'
        label = edge.get('label')
        if label:
            lines.append(f'    {edge["from"]} {arrow}|"{label}"| {edge["to"]}')
        else:
            lines.append(f'    {edge["from"]} {arrow} {edge["to"]}')
    lines.extend([
        '    classDef live fill:#dcfce7,stroke:#16a34a,color:#14532d;',
        '    classDef research fill:#dbeafe,stroke:#2563eb,color:#1e3a8a;',
        '    classDef idle fill:#e5e7eb,stroke:#6b7280,color:#374151;',
        '    classDef paused fill:#fef3c7,stroke:#d97706,color:#92400e;',
        '    classDef planned fill:#f3e8ff,stroke:#9333ea,color:#6b21a8,stroke-dasharray:5 5;',
        '    classDef retired fill:#e2e8f0,stroke:#475569,color:#334155,opacity:0.6;',
        '    classDef ext fill:#f1f5f9,stroke:#94a3b8,color:#475569;',
    ])
    grouped: dict[str, list[str]] = {}
    for node in EXTERNAL_NODES:
        grouped.setdefault('ext', []).append(node['id'])
    for layer in LAYERS:
        for node in layer.get('nodes') or []:
            grouped.setdefault(node.get('status'), []).append(node['id'])
    for status, ids in grouped.items():
        if status in STATUS_LABELS:
            lines.append(f'    class {",".join(ids)} {status};')
    ext_ids = ','.join(node['id'] for node in EXTERNAL_NODES)
    lines.append(f'    class {ext_ids} ext;')
    return '\n'.join(lines)


def validate() -> list[str]:
    """数据完整性校验；返回问题列表（空 = OK）。供测试与页面自检使用。"""
    problems: list[str] = []
    seen: set[str] = set()
    for layer in LAYERS:
        for node in layer.get('nodes') or []:
            node_id = str(node.get('id') or '')
            if not node_id:
                problems.append(f"layer {layer.get('id')}: 节点缺少 id")
                continue
            if node_id in seen:
                problems.append(f'节点 id 重复: {node_id}')
            seen.add(node_id)
            if node.get('status') not in STATUS_LABELS:
                problems.append(f'节点 {node_id} 状态非法: {node.get("status")!r}')
    for flow in FLOWS:
        if flow.get('status') not in STATUS_LABELS:
            problems.append(f"流水线 {flow.get('id')} 状态非法: {flow.get('status')!r}")
        if not flow.get('path'):
            problems.append(f"流水线 {flow.get('id')} 缺少 path")
    known = seen | {node['id'] for node in EXTERNAL_NODES}
    for edge in EDGES:
        for side in ('from', 'to'):
            if edge.get(side) not in known:
                problems.append(
                    f"链路边 {edge.get('from')}->{edge.get('to')} 引用了未知节点: {edge.get(side)!r}")
    return problems


def view_model() -> dict:
    """模板渲染视图模型：层/管线/状态统计/标签。"""
    counter: Counter = Counter()
    for layer in LAYERS:
        for node in layer.get('nodes') or []:
            counter[node.get('status')] += 1
    return {
        'schema_version': SCHEMA_VERSION,
        'updated_at': UPDATED_AT,
        'status_labels': STATUS_LABELS,
        'layers': LAYERS,
        'flows': FLOWS,
        'mermaid': build_mermaid(),
        'counts': [
            {'key': key, 'label': STATUS_LABELS[key], 'count': counter.get(key, 0)}
            for key in STATUS_LABELS
            if counter.get(key, 0)
        ],
        'total_nodes': sum(counter.values()),
    }
