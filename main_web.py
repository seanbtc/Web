from flask import Flask, render_template, jsonify, request, send_from_directory
import os
import json
import requests
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
                
                # 计算盈利摘要数据
                if 'profit_curve_data' in data and 'data_points' in data['profit_curve_data']:
                    data_points = data['profit_curve_data']['data_points']
                    if data_points:
                        # 计算总收益率
                        first_data = data_points[0]
                        last_data = data_points[-1]
                        total_principal = first_data['principal']
                        total_funds = last_data['total_funds']
                        total_net_profit = total_funds - total_principal
                        total_return_rate = (total_net_profit / total_principal * 100) if total_principal > 0 else 0
                        
                        # 计算本年收益率（以上一年12月份的总资金为本金）
                        current_year = datetime.now().year
                        last_year = current_year - 1
                        
                        # 找到上一年12月份的数据
                        last_year_december_data = None
                        for point in data_points:
                            if point['date'].startswith(f'{last_year}-12'):
                                last_year_december_data = point
                                break
                        
                        # 找到本年的数据
                        yearly_data_points = [point for point in data_points if point['date'].startswith(f'{current_year}')]
                        
                        yearly_return_rate = 0
                        yearly_return_profit = 0
                        if yearly_data_points:
                            if last_year_december_data:
                                # 以上一年12月份的总资金为本金
                                yearly_principal = last_year_december_data['total_funds']
                            else:
                                # 如果没有上一年12月份的数据，使用本年第一个数据点的本金
                                yearly_principal = yearly_data_points[0]['principal']
                            
                            last_yearly_data = yearly_data_points[-1]
                            yearly_funds = last_yearly_data['total_funds']
                            yearly_return_profit = yearly_funds - yearly_principal
                            yearly_return_rate = (yearly_return_profit / yearly_principal * 100) if yearly_principal > 0 else 0
                
                return data
        except Exception as e:
            print(f"读取总仓盈亏数据失败: {e}")
    return {
        'profit_summary': {
            'total_net_profit': 0,
            'total_margin': 0.0,
            'total_return_rate': "0%",
            'yearly_return_rate': "0%",
            'yearly_return_profit': 0
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
    return {'trade_records': [], 'summary': {
        'win_trades': 0,
        'lose_trades': 0,
        'total_profit': 0.0,
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
    last_modified_top_bottom = 0
    last_modified_spot = 0
    last_modified_total_profit = 0
    last_modified_tradingview = 0
    
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
                    data_storage.tradingview_summary = new_data.get('summary', {
                        'win_trades': 0,
                        'lose_trades': 0,
                        'total_profit': 0.0,
                        'initial_funds': 1000.0
                    })
                    data_storage.update_global_data()
                    # 广播更新
                    socketio.emit('all_data', data_storage.get_all_data())
                    print("TradingView策略数据已更新")
            
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
# 套利策略数据 - 使用默认空数据结构，完全依赖在线数据
arbitrage_data = {
    'profit_summary': {
        'total_net_profit': 0.0,
        'total_margin': 0.0,
        'total_return_rate': 0.0,
        'yearly_return_rate': 0.0,
        'yearly_return_profit': 0.0,
        'initial_funds': 0.0
    },
    'trade_records': [],
    'symbol_loss_tracker': {}
}
# 加载TradingView策略数据
tradingview_data = load_tradingview_data()
tradingview_trade_records = tradingview_data.get('trade_records', [])
tradingview_summary = tradingview_data.get('summary', {
    'win_trades': 0,
    'lose_trades': 0,
    'total_profit': 0.0,
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
                    print(f"BTC价格更新: ${btc_price}")
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
                        print(f"BTC价格更新 (CoinGecko): ${btc_price}")
        except Exception as e:
            print(f"获取BTC价格失败: {e}")
        # 每30秒获取一次价格
        time.sleep(30)

global_data = {
    'tradingview': tradingview_trade_records,  # TradingView交易数据
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
        self.tradingview_summary = global_data['tradingview_summary']
        self.arbitrage_data = global_data['arbitrage_data']
        self.total_profit_data = global_data['total_profit_data']
        self.top_bottom_data = global_data['top_bottom_data']
        self.spot_data = global_data['spot_data']
        self.strategy_status = global_data['strategy_status']
        self.market_data = global_data['market_data']
    
    def update_global_data(self):
        global global_data
        global_data['tradingview'] = self.tradingview_data
        global_data['tradingview_summary'] = self.tradingview_summary
        global_data['arbitrage_data'] = self.arbitrage_data
        global_data['total_profit_data'] = self.total_profit_data
        global_data['top_bottom_data'] = self.top_bottom_data
        global_data['spot_data'] = self.spot_data
        global_data['strategy_status'] = self.strategy_status
        global_data['market_data'] = self.market_data
    
    def add_tradingview_trade(self, trade_data):
        trade_data['timestamp'] = datetime.now().strftime('%Y-%m-%d-%H:%M:%S')
        # 插入到列表开头，实现时间从近到远显示
        self.tradingview_data.insert(0, trade_data)
        # 限制存储的记录数量
        if len(self.tradingview_data) > 100:
            self.tradingview_data = self.tradingview_data[:100]
        
        # 更新tradingview_summary数据
        if 'win_trades' in trade_data:
            self.tradingview_summary['win_trades'] = trade_data['win_trades']
        if 'lose_trades' in trade_data:
            self.tradingview_summary['lose_trades'] = trade_data['lose_trades']
        if 'total_profit' in trade_data:
            self.tradingview_summary['total_profit'] = trade_data['total_profit']
        if 'initial_funds' in trade_data:
            self.tradingview_summary['initial_funds'] = trade_data['initial_funds']
        
        self.update_global_data()
        # 保存TradingView策略数据到本地文件
        save_tradingview_data({
            'trade_records': self.tradingview_data,
            'summary': self.tradingview_summary
        })
    
    def update_arbitrage_data(self, data):
        if 'profit_summary' in data:
            # 直接使用传过来的profit_summary数据，不做处理
            self.arbitrage_data['profit_summary'] = data['profit_summary']
        
        new_records = []
        
        if 'trade_details' in data:
            # 从trade_details中提取交易记录信息
            trade_details = data['trade_details']
            for detail in trade_details:
                # 构建交易记录
                # 只添加卖单的交易记录
                # 这里假设当close_avg_price > open_avg_price时是卖单
                if detail['close_avg_price'] > detail['open_avg_price']:
                    record = {
                        'symbol': detail['symbol'],
                        'open_side': 'SELL',
                        'quantity': detail['open_executed_qty'],
                        'open_price': detail['open_avg_price'],
                        'close_price': detail['close_avg_price'],
                        'net_profit': detail['net_profit'],
                        'timestamp': detail['open_time_cn'],
                        'order_id': detail.get('order_id', f"{datetime.now().timestamp()}")
                    }
                    new_records.append(record)
        elif 'trade_records' in data:
            # 为每条交易记录添加时间戳
            for record in data['trade_records']:
                # 只添加卖单的交易记录
                if record.get('open_side') == 'SELL':
                    if 'timestamp' not in record:
                        # 使用更精确的时间戳，包含毫秒
                        record['timestamp'] = datetime.now().strftime('%Y-%m-%d-%H:%M:%S.%f')[:-3]
                        # 添加微小延迟，确保时间戳不同
                        time.sleep(0.001)
                    if 'order_id' not in record:
                        # 添加唯一订单ID
                        record['order_id'] = f"{datetime.now().timestamp()}"
                    new_records.append(record)
        
        # 去重处理：根据订单ID或更精确的标识符生成唯一标识符
        if new_records:
            # 先获取现有记录的唯一标识符集合
            existing_ids = set()
            for record in self.arbitrage_data['trade_records']:
                # 使用订单ID作为主要唯一标识符，如果没有则使用其他信息组合
                if 'order_id' in record:
                    record_id = record['order_id']
                else:
                    # 使用交易对、时间戳、开仓价格、平仓价格、净利润和数量组合作为唯一标识符
                    record_id = f"{record.get('symbol', '')}_{record.get('timestamp', '')}_{record.get('open_price', '')}_{record.get('close_price', '')}_{record.get('net_profit', '')}_{record.get('quantity', '')}"
                existing_ids.add(record_id)
            
            # 过滤掉重复的新记录
            unique_new_records = []
            for record in new_records:
                if 'order_id' in record:
                    record_id = record['order_id']
                else:
                    # 使用交易对、时间戳、开仓价格、平仓价格、净利润和数量组合作为唯一标识符
                    record_id = f"{record.get('symbol', '')}_{record.get('timestamp', '')}_{record.get('open_price', '')}_{record.get('close_price', '')}_{record.get('net_profit', '')}_{record.get('quantity', '')}"
                if record_id not in existing_ids:
                    unique_new_records.append(record)
                    existing_ids.add(record_id)
            
            # 将唯一的新记录添加到现有列表中
            if unique_new_records:
                self.arbitrage_data['trade_records'].extend(unique_new_records)
                # 限制存储的记录数量，保持文件大小合理
                if len(self.arbitrage_data['trade_records']) > 100:
                    self.arbitrage_data['trade_records'] = self.arbitrage_data['trade_records'][-100:]
        
        if 'symbol_loss_tracker' in data:
            self.arbitrage_data['symbol_loss_tracker'] = data['symbol_loss_tracker']
        
        self.update_global_data()
        # 保存套利策略数据到本地文件
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
        
        # 限制存储的记录数量
        if len(self.top_bottom_data['trade_records']) > 100:
            self.top_bottom_data['trade_records'] = self.top_bottom_data['trade_records'][:100]
        
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
        
        # 限制存储的记录数量
        if len(self.spot_data['trade_records']) > 100:
            self.spot_data['trade_records'] = self.spot_data['trade_records'][:100]
        
        self.update_global_data()
        return True
    
    def get_all_data(self):
        return {
            'tradingview': self.tradingview_data,
            'tradingview_summary': self.tradingview_summary,
            'arbitrage': self.arbitrage_data,
            'total_profit': self.total_profit_data,
            'top_bottom': self.top_bottom_data,
            'spot': self.spot_data,
            'strategy_status': self.strategy_status,
            'market_data': self.market_data
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
    print('Client connected')
    socketio.emit('all_data', data_storage.get_all_data())

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

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
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
