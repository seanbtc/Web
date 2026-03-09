from flask import Flask, render_template, jsonify, request
import os
import json
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

# 定期检查文件更新的函数
def check_file_updates():
    top_bottom_file_path = os.path.join(data_dir, 'top_bottom_trades.json')
    spot_file_path = os.path.join(data_dir, 'spot_trades.json')
    total_profit_file_path = os.path.join(data_dir, 'total_profit.json')
    last_modified_top_bottom = 0
    last_modified_spot = 0
    last_modified_total_profit = 0
    
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
# 初始化套利策略数据
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
    'trade_details': [],
    'symbol_profit_tracker': {}
}

global_data = {
    'tradingview_data': [],  # TradingView交易数据
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
        self.tradingview_data = global_data['tradingview_data']
        self.arbitrage_data = global_data['arbitrage_data']
        self.total_profit_data = global_data['total_profit_data']
        self.top_bottom_data = global_data['top_bottom_data']
        self.spot_data = global_data['spot_data']
        self.strategy_status = global_data['strategy_status']
        self.market_data = global_data['market_data']
    
    def update_global_data(self):
        global global_data
        global_data['tradingview_data'] = self.tradingview_data
        global_data['arbitrage_data'] = self.arbitrage_data
        global_data['total_profit_data'] = self.total_profit_data
        global_data['top_bottom_data'] = self.top_bottom_data
        global_data['spot_data'] = self.spot_data
        global_data['strategy_status'] = self.strategy_status
        global_data['market_data'] = self.market_data
    
    def add_tradingview_trade(self, trade_data):
        trade_data['timestamp'] = datetime.now().isoformat()
        # 插入到列表开头，实现时间从近到远显示
        self.tradingview_data.insert(0, trade_data)
        # 限制存储的记录数量
        if len(self.tradingview_data) > 100:
            self.tradingview_data = self.tradingview_data[:100]
        self.update_global_data()
    
    def update_arbitrage_data(self, data):
        if 'profit_summary' in data:
            # 只保留需要的字段，排除round_net_profit
            profit_summary = data['profit_summary']
            filtered_summary = {
                'total_net_profit': profit_summary.get('total_net_profit', 0.0),
                'total_margin': profit_summary.get('total_margin', 1000.0),
                'total_return_rate': profit_summary.get('total_return_rate', 0.0),
                'yearly_return_rate': profit_summary.get('yearly_return_rate', profit_summary.get('round_return_rate', 0.0)),
                'yearly_return_profit': profit_summary.get('yearly_return_profit', profit_summary.get('total_net_profit', 0.0))
            }
            self.arbitrage_data['profit_summary'] = filtered_summary
        if 'trade_records' in data:
            self.arbitrage_data['trade_records'] = data['trade_records']
        if 'trade_details' in data:
            self.arbitrage_data['trade_details'] = data['trade_details']
        if 'symbol_profit_tracker' in data:
            self.arbitrage_data['symbol_profit_tracker'] = data['symbol_profit_tracker']
        self.update_global_data()
    
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
        trade_data['timestamp'] = datetime.now().isoformat()
        
        # 如果已平仓，添加平仓时间戳
        if trade_data.get('is_closed'):
            trade_data['close_timestamp'] = trade_data.get('close_timestamp', datetime.now().isoformat())
        
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
        trade_data['timestamp'] = datetime.now().isoformat()
        
        # 如果已平仓，添加平仓时间戳
        if trade_data.get('is_closed'):
            trade_data['close_timestamp'] = trade_data.get('close_timestamp', datetime.now().isoformat())
        
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

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
