from flask import Flask, render_template, jsonify, request, send_from_directory
import os
import json
import requests
import logging
import sys
from datetime import datetime
import threading
import time
from flask_socketio import SocketIO

# 确保数据目录存在
data_dir = os.path.join(os.path.dirname(__file__), 'data')
if not os.path.exists(data_dir):
    os.makedirs(data_dir)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
# 添加 CORS 支持
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response
socketio = SocketIO(app, cors_allowed_origins='*')


def _env_int(name, default):
    """读取正整数环境变量，非法值回退默认。"""
    raw = os.getenv(name, '')
    try:
        value = int(raw)
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    return default


MAX_TRADINGVIEW_RECORDS = _env_int('WEB_MAX_TRADINGVIEW_RECORDS', 3000)
MAX_TRADINGVIEW_ROUNDS = _env_int('WEB_MAX_TRADINGVIEW_ROUNDS', 1000)
MAX_TOP_BOTTOM_RECORDS = _env_int('WEB_MAX_TOP_BOTTOM_RECORDS', 3000)
MAX_SPOT_RECORDS = _env_int('WEB_MAX_SPOT_RECORDS', 3000)
MAX_ARBITRAGE_RECORDS = _env_int('WEB_MAX_ARBITRAGE_RECORDS', 5000)
MAX_PROFIT_CURVE_POINTS = _env_int('WEB_MAX_PROFIT_CURVE_POINTS', 4000)


def _trim_list_inplace(items, limit, keep='head'):
    """原地裁剪列表，避免历史数据无限增长。"""
    if not isinstance(items, list) or limit <= 0:
        return
    if len(items) <= limit:
        return
    if keep == 'tail':
        del items[:len(items) - limit]
    else:
        del items[limit:]


def _trim_profit_curve_points(total_profit_data):
    if not isinstance(total_profit_data, dict):
        return
    curve_data = total_profit_data.get('profit_curve_data')
    if not isinstance(curve_data, dict):
        return
    points = curve_data.get('data_points')
    _trim_list_inplace(points, MAX_PROFIT_CURVE_POINTS, keep='tail')


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_profit_curve_date(value):
    parts = str(value or '').split('-')
    if len(parts) < 2:
        return None

    try:
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2]) if len(parts) > 2 else 1
    except (TypeError, ValueError):
        return None

    if month < 1 or month > 12:
        return None
    if day < 1 or day > 31:
        day = 1
    return year, month, day


def _build_total_profit_summary(total_profit_data):
    summary = {
        'total_net_profit': 0.0,
        'total_margin': 0.0,
        'total_return_rate': 0.0,
        'yearly_return_rate': 0.0,
        'yearly_return_profit': 0.0,
        'total_principal': 0.0
    }

    if not isinstance(total_profit_data, dict):
        return summary

    curve_data = total_profit_data.get('profit_curve_data')
    if not isinstance(curve_data, dict):
        return summary

    raw_points = curve_data.get('data_points')
    if not isinstance(raw_points, list):
        return summary

    normalized_points = []
    for index, point in enumerate(raw_points):
        if not isinstance(point, dict):
            continue

        date_parts = _parse_profit_curve_date(point.get('date'))
        normalized_points.append({
            'year': date_parts[0] if date_parts else None,
            'sort_key': date_parts if date_parts else (9999, 12, 31),
            'index': index,
            'principal': _to_float(point.get('principal'), 0.0),
            'total_funds': _to_float(point.get('total_funds'), 0.0)
        })

    if not normalized_points:
        return summary

    normalized_points.sort(key=lambda point: (point['sort_key'], point['index']))

    last_point = normalized_points[-1]
    total_principal = last_point['principal']
    total_margin = last_point['total_funds']
    total_net_profit = total_margin - total_principal
    total_return_rate = (total_net_profit / total_principal * 100) if total_principal > 0 else 0.0

    current_year = datetime.now().year
    current_year_points = []
    baseline_point = None

    for point in normalized_points:
        point_year = point['year']
        if point_year == current_year:
            current_year_points.append(point)
        elif point_year is not None and point_year < current_year:
            baseline_point = point

    yearly_return_profit = 0.0
    yearly_return_rate = 0.0
    if current_year_points:
        yearly_start_point = baseline_point or current_year_points[0]
        yearly_end_point = current_year_points[-1]

        yearly_start_profit = yearly_start_point['total_funds'] - yearly_start_point['principal']
        yearly_end_profit = yearly_end_point['total_funds'] - yearly_end_point['principal']
        yearly_return_profit = yearly_end_profit - yearly_start_profit

        yearly_base_funds = yearly_start_point['total_funds']
        yearly_return_rate = (yearly_return_profit / yearly_base_funds * 100) if yearly_base_funds > 0 else 0.0

    summary.update({
        'total_net_profit': round(total_net_profit, 4),
        'total_margin': round(total_margin, 4),
        'total_return_rate': round(total_return_rate, 6),
        'yearly_return_rate': round(yearly_return_rate, 6),
        'yearly_return_profit': round(yearly_return_profit, 4),
        'total_principal': round(total_principal, 4)
    })
    return summary

# 从本地文件读取摸顶抄底策略数据
def load_top_bottom_data():
    file_path = os.path.join(data_dir, 'top_bottom_trades.json')
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"读取摸顶抄底数据失败: {e}")
    return {'trade_records': []}

# 从本地文件读取现货策略数据
def load_spot_data():
    file_path = os.path.join(data_dir, 'spot_trades.json')
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"读取现货策略数据失败: {e}")
    return {'trade_records': []}

# 从本地文件读取总仓盈亏数据
def load_total_profit_data():
    file_path = os.path.join(data_dir, 'total_profit.json')
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data['profit_summary'] = _build_total_profit_summary(data)
                return data
        except Exception as e:
            print(f"读取总仓盈亏数据失败: {e}")
    return {
        'profit_summary': {
            'total_net_profit': 0.0,
            'total_margin': 0.0,
            'total_return_rate': 0.0,
            'yearly_return_rate': 0.0,
            'yearly_return_profit': 0.0,
            'total_principal': 0.0
        },
        'trade_records': [],
        'symbol_profit_tracker': {}
    }

# 套利策略数据不再从本地文件加载，完全依赖在线数据

# 从本地文件读取TradingView策略数据
def load_tradingview_data():
    file_path = os.path.join(data_dir, 'tradingview_trades.json')
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"读取TradingView策略数据失败: {e}")
    return {'trade_records': [], 'round_records': [], 'summary': {
        'win_trades': 0,
        'lose_trades': 0,
        'total_profit': 0.0,
        'total_profit_all': 0.0,
        'initial_funds': 1000.0
    }}

# 保存TradingView策略数据到本地文件
def save_tradingview_data(data):
    file_path = os.path.join(data_dir, 'tradingview_trades.json')
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("TradingView策略数据已保存")
    except Exception as e:
        print(f"保存TradingView策略数据失败: {e}")

# 从本地文件读取套利策略数据
def load_arbitrage_data():
    file_path = os.path.join(data_dir, 'arbitrage_trades.json')
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"读取套利策略数据失败: {e}")
    return {
        'profit_summary': {
            'total_net_profit': 0.0,
            'total_margin': 0.0,
            'total_return_rate': 0.0,
            'yearly_return_rate': 0.0,
            'yearly_return_profit': 0.0,
            'initial_funds': 0.0
        },
        'trade_records': [],
    }

# 保存套利策略数据到本地文件
def save_arbitrage_data(data):
    file_path = os.path.join(data_dir, 'arbitrage_trades.json')
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("套利策略数据已保存")
    except Exception as e:
        print(f"保存套利策略数据失败: {e}")

# 定期检查文件更新的函数
def check_file_updates():
    top_bottom_file_path = os.path.join(data_dir, 'top_bottom_trades.json')
    spot_file_path = os.path.join(data_dir, 'spot_trades.json')
    total_profit_file_path = os.path.join(data_dir, 'total_profit.json')
    tradingview_file_path = os.path.join(data_dir, 'tradingview_trades.json')
    arbitrage_file_path = os.path.join(data_dir, 'arbitrage_trades.json')
    last_modified_top_bottom = 0
    last_modified_spot = 0
    last_modified_total_profit = 0
    last_modified_tradingview = 0
    last_modified_arbitrage = 0
    
    while True:
        try:
            # 检查摸顶抄底策略文件
            if os.path.exists(top_bottom_file_path):
                current_modified = os.path.getmtime(top_bottom_file_path)
                if current_modified > last_modified_top_bottom:
                    last_modified_top_bottom = current_modified
                    # 重新加载数据
                    new_data = load_top_bottom_data()
                    # 更新仓位状态
                    data_storage.top_bottom_data['position_status'] = new_data.get('position_status', '摸顶做空')
                    data_storage.top_bottom_data['position_quantity'] = new_data.get('position_quantity', 0.1)
                    data_storage.top_bottom_data['position_avg_price'] = new_data.get('position_avg_price', 11600.0)
                    data_storage.top_bottom_data['position_symbol'] = new_data.get('position_symbol', 'BTCUSDT')
                    data_storage.top_bottom_data['trade_records'] = new_data.get('trade_records', [])
                    # 更新策略状态
                    data_storage.strategy_status['top_bottom'] = new_data.get('position_status', '摸顶做空')
                    data_storage.update_global_data()
                    # 广播更新
                    socketio.emit('all_data', data_storage.get_all_data())
                    print("摸顶抄底数据已更新")
            
            # 检查现货策略文件
            if os.path.exists(spot_file_path):
                current_modified = os.path.getmtime(spot_file_path)
                if current_modified > last_modified_spot:
                    last_modified_spot = current_modified
                    # 重新加载数据
                    new_data = load_spot_data()
                    # 更新仓位状态
                    data_storage.spot_data['position_quantity'] = new_data.get('position_quantity', 0.0)
                    data_storage.spot_data['position_avg_price'] = new_data.get('position_avg_price', 0.0)
                    data_storage.spot_data['position_symbol'] = new_data.get('position_symbol', 'BTCUSDT')
                    data_storage.spot_data['trade_records'] = new_data.get('trade_records', [])
                    data_storage.update_global_data()
                    # 广播更新
                    socketio.emit('all_data', data_storage.get_all_data())
                    print("现货策略数据已更新")
            
            # 检查总仓盈亏数据文件
            if os.path.exists(total_profit_file_path):
                current_modified = os.path.getmtime(total_profit_file_path)
                if current_modified > last_modified_total_profit:
                    last_modified_total_profit = current_modified
                    # 重新加载数据
                    new_data = load_total_profit_data()
                    # 更新总仓盈亏数据
                    data_storage.total_profit_data = new_data
                    data_storage.update_global_data()
                    # 广播更新
                    socketio.emit('all_data', data_storage.get_all_data())
                    print("总仓盈亏数据已更新")
            

            
            # 检查TradingView策略数据文件
            if os.path.exists(tradingview_file_path):
                current_modified = os.path.getmtime(tradingview_file_path)
                if current_modified > last_modified_tradingview:
                    last_modified_tradingview = current_modified
                    # 重新加载数据
                    new_data = load_tradingview_data()
                    # 更新TradingView策略数据
                    data_storage.tradingview_data = new_data.get('trade_records', [])
                    data_storage.tradingview_rounds = new_data.get('round_records', [])
                    data_storage.tradingview_summary = new_data.get('summary', {
                        'win_trades': 0,
                        'lose_trades': 0,
                        'total_profit': 0.0,
                        'total_profit_all': 0.0,
                        'initial_funds': 1000.0
                    })
                    data_storage.update_global_data()
                    # 广播更新
                    socketio.emit('all_data', data_storage.get_all_data())
                    print("TradingView策略数据已更新")
            
            # 检查套利策略数据文件
            if os.path.exists(arbitrage_file_path):
                current_modified = os.path.getmtime(arbitrage_file_path)
                if current_modified > last_modified_arbitrage:
                    last_modified_arbitrage = current_modified
                    # 重新加载数据
                    new_data = load_arbitrage_data()
                    # 更新套利策略数据
                    data_storage.arbitrage_data = new_data
                    data_storage.update_global_data()
                    # 广播更新
                    socketio.emit('all_data', data_storage.get_all_data())
                    print("套利策略数据已更新")
            
            # 每5秒检查一次
            time.sleep(5)
        except Exception as e:
            print(f"检查文件更新失败: {e}")
            time.sleep(5)

# 全局数据存储
# 加载摸顶抄底策略数据
top_bottom_file_data = load_top_bottom_data()
# 加载现货策略数据
spot_file_data = load_spot_data()
# 加载总仓盈亏数据
total_profit_data = load_total_profit_data()
# 加载套利策略数据
arbitrage_data = load_arbitrage_data()
# 加载TradingView策略数据
tradingview_data = load_tradingview_data()
tradingview_trade_records = tradingview_data.get('trade_records', [])
tradingview_round_records = tradingview_data.get('round_records', [])
tradingview_summary = tradingview_data.get('summary', {
    'win_trades': 0,
    'lose_trades': 0,
    'total_profit': 0.0,
    'total_profit_all': 0.0,
    'initial_funds': 1000.0
})

# 定期获取BTC价格的函数
def fetch_btc_price():
    # 延迟启动，确保服务已经完全启动
    time.sleep(10)
    
    while True:
        try:
            # 尝试使用Binance API
            response = requests.get('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT', timeout=3)
            if response.status_code == 200:
                data = response.json()
                if 'price' in data:
                    btc_price = float(data['price'])
                    # 更新市场数据
                    data_storage.update_market_data({'btc_price': btc_price})
                    # 广播更新
                    socketio.emit('all_data', data_storage.get_all_data())
                    # print(f"BTC价格更新: ${btc_price}")
            else:
                # 如果Binance API失败，尝试使用CoinGecko API
                response = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd', timeout=3)
                if response.status_code == 200:
                    data = response.json()
                    if 'bitcoin' in data and 'usd' in data['bitcoin']:
                        btc_price = float(data['bitcoin']['usd'])
                        # 更新市场数据
                        data_storage.update_market_data({'btc_price': btc_price})
                        # 广播更新
                        socketio.emit('all_data', data_storage.get_all_data())
                        # print(f"BTC价格更新 (CoinGecko): ${btc_price}")
        except Exception as e:
            print(f"获取BTC价格失败: {e}")
        # 每30秒获取一次价格
        time.sleep(30)

global_data = {
    'tradingview': tradingview_trade_records,  # TradingView交易数据
    'tradingview_rounds': tradingview_round_records,  # TradingView过去几轮盈利记录
    'tradingview_summary': tradingview_summary,  # TradingView策略盈亏摘要
    'arbitrage_data': arbitrage_data,  # 套利策略数据
    'total_profit_data': total_profit_data,  # 总仓盈亏数据
    'top_bottom_data': {
        'position_status': top_bottom_file_data.get('position_status', '摸顶做空'),  # 当前仓位状态：摸顶做空/抄底做多
        'position_quantity': top_bottom_file_data.get('position_quantity', 0.17),  # 当前仓位数量
        'position_avg_price': top_bottom_file_data.get('position_avg_price', 116900.0),  # 当前仓位均价
        'position_symbol': top_bottom_file_data.get('position_symbol', 'BTCUSDT'),  # 交易对
        'trade_records': top_bottom_file_data.get('trade_records', [])  # 从本地文件读取交易记录
    },
    'spot_data': {
        'position_quantity': spot_file_data.get('position_quantity', 0.0),  # 当前仓位数量
        'position_avg_price': spot_file_data.get('position_avg_price', 0.0),  # 当前仓位均价
        'position_symbol': spot_file_data.get('position_symbol', 'BTCUSDT'),  # 交易对
        'trade_records': spot_file_data.get('trade_records', [])  # 从本地文件读取交易记录
    },
    'strategy_status': {
        'tradingview': '做空',  # 4H多空策略状态：做空/做多/暂停
        'arbitrage': '运行',     # 套利策略状态：运行/暂停
        'top_bottom': top_bottom_file_data.get('position_status', '摸顶做空'),  # 摸顶抄底策略状态：摸顶做空/抄底做多/空仓
        'spot': '空仓'           # 现货策略状态：运行满仓/建仓/空仓
    },
    'market_data': {
        'cycle': '熊',  # 牛熊周期判断：牛/熊
        'btc_price': 68000.0  # 当前BTCUSDT价格
    }
}

# 数据存储类
class DataStorage:
    def __init__(self):
        self.tradingview_data = global_data['tradingview']
        self.tradingview_rounds = global_data.get('tradingview_rounds', [])
        self.tradingview_summary = global_data['tradingview_summary']
        self.arbitrage_data = global_data['arbitrage_data']
        self.total_profit_data = global_data['total_profit_data']
        self.top_bottom_data = global_data['top_bottom_data']
        self.spot_data = global_data['spot_data']
        self.strategy_status = global_data['strategy_status']
        self.market_data = global_data['market_data']
        self.arbitrage_start_time = None  # 套利策略启动时间
        self._apply_memory_limits()

    def _apply_memory_limits(self):
        _trim_list_inplace(self.tradingview_data, MAX_TRADINGVIEW_RECORDS, keep='head')
        _trim_list_inplace(self.tradingview_rounds, MAX_TRADINGVIEW_ROUNDS, keep='head')

        if isinstance(self.top_bottom_data, dict):
            _trim_list_inplace(self.top_bottom_data.get('trade_records'), MAX_TOP_BOTTOM_RECORDS, keep='head')
        if isinstance(self.spot_data, dict):
            _trim_list_inplace(self.spot_data.get('trade_records'), MAX_SPOT_RECORDS, keep='head')

        if isinstance(self.arbitrage_data, dict):
            records = self.arbitrage_data.get('trade_records')
            if isinstance(records, list) and len(records) > MAX_ARBITRAGE_RECORDS:
                summary = self.arbitrage_data.get('profit_summary')
                if not isinstance(summary, dict):
                    summary = {}
                    self.arbitrage_data['profit_summary'] = summary

                drop_count = len(records) - MAX_ARBITRAGE_RECORDS
                dropped = records[:drop_count]
                archived = _to_float(summary.get('archived_net_profit', 0.0), 0.0)
                archived += sum(_to_float(item.get('net_profit', 0.0), 0.0) for item in dropped)

                del records[:drop_count]
                summary['archived_net_profit'] = round(archived, 4)
                summary['retained_record_count'] = len(records)

        _trim_profit_curve_points(self.total_profit_data)
        if isinstance(self.total_profit_data, dict):
            self.total_profit_data['profit_summary'] = _build_total_profit_summary(self.total_profit_data)
    
    def update_global_data(self):
        global global_data
        self._apply_memory_limits()
        global_data['tradingview'] = self.tradingview_data
        global_data['tradingview_rounds'] = self.tradingview_rounds
        global_data['tradingview_summary'] = self.tradingview_summary
        global_data['arbitrage_data'] = self.arbitrage_data
        global_data['total_profit_data'] = self.total_profit_data
        global_data['top_bottom_data'] = self.top_bottom_data
        global_data['spot_data'] = self.spot_data
        global_data['strategy_status'] = self.strategy_status
        global_data['market_data'] = self.market_data
        global_data['arbitrage_start_time'] = self.arbitrage_start_time
    
    def add_tradingview_trade(self, trade_data):
        trade_data['timestamp'] = datetime.now().strftime('%Y-%m-%d-%H:%M:%S')
        trade_data.setdefault('strategy_type', 'legacy_tradingview')
        trade_data.setdefault('strategy_label', '4H策略')
        trade_data.setdefault('web_mode', 'tradingview')
        trade_data.setdefault('web_category', 'tradingview')
        trade_data.setdefault('web_strategy_label', '4H策略')
        trade_data.setdefault('account_id', 'default')
        trade_data.setdefault('account_label', '默认账号')
        trade_data.setdefault('account_profile', 'default.json')
        # 插入到列表开头，实现时间从近到远显示
        self.tradingview_data.insert(0, trade_data)

        # 支持通过接口附带更新过去几轮盈利记录
        if isinstance(trade_data.get('round_record'), dict):
            self.tradingview_rounds.insert(0, trade_data['round_record'])
        if isinstance(trade_data.get('round_records'), list):
            self.tradingview_rounds = trade_data['round_records']
        
        # 更新tradingview_summary数据
        if 'win_trades' in trade_data:
            self.tradingview_summary['win_trades'] = trade_data['win_trades']
        if 'lose_trades' in trade_data:
            self.tradingview_summary['lose_trades'] = trade_data['lose_trades']
        if 'total_profit' in trade_data:
            self.tradingview_summary['total_profit'] = trade_data['total_profit']
        if 'total_profit_all' in trade_data:
            self.tradingview_summary['total_profit_all'] = trade_data['total_profit_all']
        if 'initial_funds' in trade_data:
            self.tradingview_summary['initial_funds'] = trade_data['initial_funds']

        self._apply_memory_limits()
        
        self.update_global_data()
        # 保存TradingView策略数据到本地文件
        save_tradingview_data({
            'trade_records': self.tradingview_data,
            'round_records': self.tradingview_rounds,
            'summary': self.tradingview_summary
        })
    
    def update_arbitrage_data(self, data):
        """更新套利数据：只以唯一订单的 net_profit 作为总额计算来源。"""
        arbitrage_data_file = os.path.join(data_dir, 'arbitrage_trades.json')
        existing_data = {}
        if os.path.exists(arbitrage_data_file):
            try:
                with open(arbitrage_data_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except Exception as e:
                print(f"⚠️ 读取套利策略数据文件异常：{e}")

        def build_record(detail):
            symbol = detail.get('symbol', 'UNKNOWN')
            close_time = detail.get('close_time_cn') or detail.get('timestamp') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            close_order_id = detail.get('close_order_id') or detail.get('order_id')
            order_id = str(close_order_id) if close_order_id else f"{symbol}_{close_time}"
            return {
                'symbol': symbol,
                'open_side': detail.get('open_side', 'SELL'),
                'quantity': _to_float(detail.get('open_executed_qty', detail.get('quantity', 0))),
                'open_price': _to_float(detail.get('open_avg_price', detail.get('open_price', 0))),
                'close_price': _to_float(detail.get('close_avg_price', detail.get('close_price', 0))),
                'net_profit': _to_float(detail.get('net_profit', 0)),
                'timestamp': close_time,
                'order_id': order_id
            }

        if not isinstance(self.arbitrage_data, dict):
            self.arbitrage_data = {}
        self.arbitrage_data.setdefault('trade_records', [])
        self.arbitrage_data.setdefault('profit_summary', {})

        # 启动时间只保留首次有效值，避免后续请求覆盖
        self.arbitrage_start_time = (
            existing_data.get('start_time')
            or self.arbitrage_data.get('start_time')
            or data.get('start_time')
        )
        if self.arbitrage_start_time:
            self.arbitrage_data['start_time'] = self.arbitrage_start_time

        incoming_summary = data.get('profit_summary', {}) if isinstance(data.get('profit_summary'), dict) else {}
        current_summary = self.arbitrage_data.get('profit_summary', {}) if isinstance(self.arbitrage_data.get('profit_summary'), dict) else {}
        existing_summary = existing_data.get('profit_summary', {}) if isinstance(existing_data.get('profit_summary'), dict) else {}

        # 初始资金优先使用本地已填写值，其次才使用请求中的值
        initial_funds = _to_float(
            existing_summary.get(
                'initial_funds',
                current_summary.get('initial_funds', incoming_summary.get('initial_funds', 500.0))
            ),
            500.0
        )

        # 先规范化已有记录并按 order_id 去重
        normalized_records = []
        existing_ids = set()
        for record in self.arbitrage_data.get('trade_records', []):
            normalized = build_record(record)
            if normalized['order_id'] in existing_ids:
                continue
            existing_ids.add(normalized['order_id'])
            normalized_records.append(normalized)
        self.arbitrage_data['trade_records'] = normalized_records

        # 只接收订单明细，汇总完全由订单 net_profit 自动重算
        incoming_records = data.get('trade_details') or data.get('trade_records') or []
        added_records = 0
        duplicate_records = 0
        added_symbols = []

        for detail in incoming_records:
            record = build_record(detail)
            if record['order_id'] in existing_ids:
                duplicate_records += 1
                continue
            existing_ids.add(record['order_id'])
            self.arbitrage_data['trade_records'].append(record)
            added_records += 1
            added_symbols.append(record['symbol'])

        archived_net_profit = _to_float(
            current_summary.get('archived_net_profit', existing_summary.get('archived_net_profit', 0.0)),
            0.0
        )

        # 套利记录按最新优先保留尾部，同时将被裁剪部分利润归档，保证累计收益不丢失。
        records = self.arbitrage_data['trade_records']
        if len(records) > MAX_ARBITRAGE_RECORDS:
            drop_count = len(records) - MAX_ARBITRAGE_RECORDS
            dropped_records = records[:drop_count]
            archived_net_profit += sum(_to_float(item.get('net_profit', 0.0)) for item in dropped_records)
            del records[:drop_count]

        retained_net_profit = sum(_to_float(record.get('net_profit', 0.0)) for record in records)
        total_net_profit = archived_net_profit + retained_net_profit
        total_margin = initial_funds + total_net_profit
        total_return_rate = (total_net_profit / initial_funds * 100) if initial_funds > 0 else 0.0

        profit_summary = {
            'total_net_profit': round(total_net_profit, 4),
            'initial_funds': initial_funds,
            'total_margin': round(total_margin, 4),
            'total_return_rate': round(total_return_rate, 6),
            'archived_net_profit': round(archived_net_profit, 4),
            'retained_record_count': len(records)
        }

        # 非核心扩展字段只做透传，不参与总额计算
        for key in ['yearly_return_rate', 'yearly_return_profit', 'round_net_profit', 'round_return_rate']:
            if key in incoming_summary:
                profit_summary[key] = incoming_summary[key]
            elif key in current_summary:
                profit_summary[key] = current_summary[key]
            elif key in existing_summary:
                profit_summary[key] = existing_summary[key]

        self.arbitrage_data['profit_summary'] = profit_summary

        symbol_summary = ','.join(added_symbols[:5]) if added_symbols else '无新增交易'
        if len(added_symbols) > 5:
            symbol_summary += f" 等{len(added_symbols)}个"

        new_profit = sum(_to_float(record.get('net_profit', 0.0)) for record in self.arbitrage_data['trade_records'][-added_records:]) if added_records > 0 else 0.0
        print(
            f"套利更新 | 收到:{len(incoming_records)} 新增:{added_records} 重复:{duplicate_records} "
            f"新增净收益:{new_profit:.4f}USDT"
        )
        print(
            f"套利汇总 | 交易对:{symbol_summary} 总盈利:{total_net_profit:.4f}USDT "
            f"总保证金:{total_margin:.4f}USDT 收益率:{total_return_rate:.6f}%"
        )

        self.update_global_data()
        save_arbitrage_data(self.arbitrage_data)
    
    def update_strategy_status(self, strategy, status):
        if strategy in self.strategy_status:
            self.strategy_status[strategy] = status
            self.update_global_data()
            return True
        return False
    
    def update_market_data(self, data):
        if 'cycle' in data:
            self.market_data['cycle'] = data['cycle']
        if 'btc_price' in data:
            self.market_data['btc_price'] = data['btc_price']
        self.update_global_data()
        return True
    
    def update_top_bottom_data(self, data):
        if 'position_status' in data:
            self.top_bottom_data['position_status'] = data['position_status']
        if 'position_quantity' in data:
            self.top_bottom_data['position_quantity'] = data['position_quantity']
        if 'position_avg_price' in data:
            self.top_bottom_data['position_avg_price'] = data['position_avg_price']
        if 'position_symbol' in data:
            self.top_bottom_data['position_symbol'] = data['position_symbol']
        if 'trade_records' in data:
            self.top_bottom_data['trade_records'] = data['trade_records']
        self.update_global_data()
        return True
    
    def add_top_bottom_trade(self, trade_data):
        # 确保trade_data包含必要的字段
        required_fields = ['mode', 'quantity', 'avg_price', 'is_closed', 'profit']
        for field in required_fields:
            if field not in trade_data:
                return False
        
        # 添加时间戳
        trade_data['timestamp'] = datetime.now().strftime('%Y-%m-%d-%H:%M:%S')
        
        # 如果已平仓，添加平仓时间戳
        if trade_data.get('is_closed'):
            trade_data['close_timestamp'] = trade_data.get('close_timestamp', datetime.now().strftime('%Y-%m-%d-%H:%M:%S'))
        
        # 插入到列表开头，实现时间从近到远显示
        self.top_bottom_data['trade_records'].insert(0, trade_data)
        _trim_list_inplace(self.top_bottom_data.get('trade_records'), MAX_TOP_BOTTOM_RECORDS, keep='head')
        
        self.update_global_data()
        return True
    
    def update_spot_data(self, data):
        if 'position_quantity' in data:
            self.spot_data['position_quantity'] = data['position_quantity']
        if 'position_avg_price' in data:
            self.spot_data['position_avg_price'] = data['position_avg_price']
        if 'position_symbol' in data:
            self.spot_data['position_symbol'] = data['position_symbol']
        if 'trade_records' in data:
            self.spot_data['trade_records'] = data['trade_records']
        self.update_global_data()
        return True
    
    def add_spot_trade(self, trade_data):
        # 确保trade_data包含必要的字段
        required_fields = ['quantity', 'avg_price', 'is_closed', 'profit']
        for field in required_fields:
            if field not in trade_data:
                return False
        
        # 添加时间戳
        trade_data['timestamp'] = datetime.now().strftime('%Y-%m-%d-%H:%M:%S')
        
        # 如果已平仓，添加平仓时间戳
        if trade_data.get('is_closed'):
            trade_data['close_timestamp'] = trade_data.get('close_timestamp', datetime.now().strftime('%Y-%m-%d-%H:%M:%S'))
        
        # 插入到列表开头，实现时间从近到远显示
        self.spot_data['trade_records'].insert(0, trade_data)
        _trim_list_inplace(self.spot_data.get('trade_records'), MAX_SPOT_RECORDS, keep='head')
        
        self.update_global_data()
        return True
    
    def get_all_data(self):
        return {
            'tradingview': self.tradingview_data,
            'tradingview_rounds': self.tradingview_rounds,
            'tradingview_summary': self.tradingview_summary,
            'arbitrage': self.arbitrage_data,
            'total_profit': self.total_profit_data,
            'top_bottom': self.top_bottom_data,
            'spot': self.spot_data,
            'strategy_status': self.strategy_status,
            'market_data': self.market_data,
            'arbitrage_start_time': self.arbitrage_start_time
        }

# 初始化数据存储
data_storage = DataStorage()

# 启动文件更新检查线程
file_update_thread = threading.Thread(target=check_file_updates, daemon=True)
file_update_thread.start()

# 启动获取BTC价格的线程
btc_price_thread = threading.Thread(target=fetch_btc_price, daemon=True)
btc_price_thread.start()

# WebSocket事件处理
@socketio.on('connect')
def handle_connect():
    # print('Client connected')
    socketio.emit('all_data', data_storage.get_all_data())

@socketio.on('disconnect')
def handle_disconnect():
    pass

# API端点
@app.route('/api/update_tradingview', methods=['POST'])
def update_tradingview_data():
    data = request.json
    if data:
        data_storage.add_tradingview_trade(data)
        socketio.emit('all_data', data_storage.get_all_data())
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/update_arbitrage', methods=['POST'])
def update_arbitrage_data():
    data = request.json
    if data:
        data_storage.update_arbitrage_data(data)
        socketio.emit('all_data', data_storage.get_all_data())
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/get_data', methods=['GET'])
def get_data():
    return jsonify(data_storage.get_all_data())

@app.route('/api/update_strategy_status', methods=['POST'])
def update_strategy_status():
    data = request.json
    if data and 'strategy' in data and 'status' in data:
        success = data_storage.update_strategy_status(data['strategy'], data['status'])
        if success:
            socketio.emit('all_data', data_storage.get_all_data())
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/update_market_data', methods=['POST'])
def update_market_data():
    data = request.json
    if data:
        success = data_storage.update_market_data(data)
        if success:
            socketio.emit('all_data', data_storage.get_all_data())
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/update_top_bottom', methods=['POST'])
def update_top_bottom_data():
    data = request.json
    if data:
        success = data_storage.update_top_bottom_data(data)
        if success:
            socketio.emit('all_data', data_storage.get_all_data())
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/add_top_bottom_trade', methods=['POST'])
def add_top_bottom_trade():
    data = request.json
    if data:
        success = data_storage.add_top_bottom_trade(data)
        if success:
            socketio.emit('all_data', data_storage.get_all_data())
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/update_spot', methods=['POST'])
def update_spot_data():
    data = request.json
    if data:
        success = data_storage.update_spot_data(data)
        if success:
            socketio.emit('all_data', data_storage.get_all_data())
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/add_spot_trade', methods=['POST'])
def add_spot_trade():
    data = request.json
    if data:
        success = data_storage.add_spot_trade(data)
        if success:
            socketio.emit('all_data', data_storage.get_all_data())
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

# 主页
@app.route('/')
def index():
    return render_template('index.html')

# 上下文处理器
@app.context_processor
def inject_datetime():
    return {'current_datetime': datetime.now()}

# 为data目录添加静态文件路由
@app.route('/data/<path:filename>')
def serve_data_file(filename):
    return send_from_directory(data_dir, filename)

# 为static目录添加静态文件路由
@app.route('/static/<path:filename>')
def serve_static_file(filename):
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    return send_from_directory(static_dir, filename)

if __name__ == '__main__':
    class FilteredStderr:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def write(self, message):
            if not message:
                return

            if 'Bad request version' in message:
                return
            if 'code 400, message' in message:
                return

            # 过滤含有控制字符的异常协议噪音行
            has_ctrl = any((ord(ch) < 32 and ch not in '\r\n\t') for ch in message)
            if has_ctrl:
                return

            self.wrapped.write(message)

        def flush(self):
            self.wrapped.flush()

    # 降低普通请求日志级别，并屏蔽异常协议扫描噪音
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.logger.disabled = True
    sys.stderr = FilteredStderr(sys.stderr)
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, log_output=False)
