import os
import time
import schedule
from openai import OpenAI
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime
import json
import re
import sys
from dotenv import load_dotenv

load_dotenv()

# --- 1. 日志系统 (自动保存到文件) ---
class Logger(object):
    def __init__(self):
        if not os.path.exists('logs'):
            os.makedirs('logs')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.filename = f"logs/log_{timestamp}.log"
        self.terminal = sys.stdout
        self.log = open(self.filename, 'a', encoding='utf-8')
        print(f"📄 日志文件已创建: {self.filename}")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

# --- 2. 配置区域 ---
deepseek_client = OpenAI(
    api_key=os.getenv('DEEPSEEK_API_KEY'),
    base_url="https://api.deepseek.com"
)

exchange = ccxt.okx({
    'options': {'defaultType': 'swap'},
    'apiKey': os.getenv('OKX_API_KEY'),
    'secret': os.getenv('OKX_SECRET'),
    'password': os.getenv('OKX_PASSWORD'),
})

# TRADE_CONFIG = {
#     'symbol': 'BTC/USDT:USDT',  # OKX的合约符号格式
#     'amount': 0.01,  # 交易数量 (BTC)
#     'leverage': 2,  # 杠杆倍数
#     'timeframe': '15m',  # 使用15分钟K线（可选值：1m, 3m, 5m, 15m, 30m, 1h）
#     'test_mode': False,  # 测试模式
#     'data_points': 96,  # 24小时数据（96根15分钟K线）
#     'analysis_periods': {
#         'short_term': 20,  # 短期均线
#         'medium_term': 50,  # 中期均线
#         'long_term': 96  # 长期趋势
#     }
# }

TRADE_CONFIG = {
    # 🟢 建议新手用 DOGE，杠杆低，容错率高
    'symbol': 'DOGE/USDT:USDT', 
    'amount': 1,            # 每次交易合约张数 (DOGE通常1张=10个或100个币)
    'leverage': 3,          # 3倍杠杆 (非常安全)
    'timeframe': '15m',     # 实盘建议 15m，调试可用 1m（可选值：1m, 3m, 5m, 15m, 30m, 1h）
    'test_mode': True,      # [开关] True=模拟资金交易, False=实盘真金白银
    'data_points': 100,     # 获取K线数量
    'analysis_periods': {
        'short_term': 20,  # 短期均线
        'medium_term': 50,  # 中期均线
        'long_term': 96  # 长期趋势
    }
}

# --- 3. 全局变量 ---
price_history = []
signal_history = []
position = None # 实盘持仓缓存

# 🟢 虚拟账户 (仅在 test_mode=True 时有效)
virtual_account = {
    "balance": 100.0,     # 初始模拟本金 100 U
    "holdings": 0.0,      # 持仓张数
    "entry_price": 0.0,   # 开仓均价
    "side": None          # 'long' 或 'short'
}

# --- 4. 核心功能函数 ---

def setup_exchange():
    """初始化交易所并获取关键信息"""
    try:
        # 1. 设置杠杆
        exchange.set_leverage(
            TRADE_CONFIG['leverage'],
            TRADE_CONFIG['symbol'],
            {'mgnMode': 'cross'}
        )
        print(f"✅ 杠杆模式: 全仓 {TRADE_CONFIG['leverage']}x")

        # 2. 获取合约面值 (关键！不同币种1张合约代表的数量不同)
        markets = exchange.load_markets()
        market_info = markets[TRADE_CONFIG['symbol']]
        TRADE_CONFIG['contract_size'] = float(market_info['contractSize'])
        print(f"📏 合约面值: 1张 = {TRADE_CONFIG['contract_size']} 个币")

        # 3. 获取余额
        balance = exchange.fetch_balance()
        usdt = balance.get('USDT', {}).get('free', 0)
        print(f"💰 实盘可用余额: {usdt:.2f} USDT")
        
        return True
    except Exception as e:
        print(f"❌ 交易所初始化失败: {e}")
        return False

def calculate_technical_indicators(df):
    """计算丰富指标 (喂给DeepSeek的数据源)"""
    try:
        close = df['close']
        high = df['high']
        low = df['low']

        # 1. 均线系统 (判断趋势)
        df['sma_5'] = close.rolling(5).mean()
        df['sma_20'] = close.rolling(20).mean()
        df['sma_50'] = close.rolling(50).mean() # 牛熊分界

        # 2. MACD (判断动能)
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        # 3. RSI (判断超买超卖)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # 4. 布林带 (判断波动区间)
        mid = close.rolling(20).mean()
        std = close.rolling(20).std()
        df['bb_upper'] = mid + 2 * std
        df['bb_lower'] = mid - 2 * std
        # 计算价格在布林带的位置 (0=下轨, 0.5=中轨, 1=上轨)
        df['bb_pct'] = (close - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # 5. ATR (平均真实波幅 - 用于止损计算)
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()

        df = df.fillna(0)
        return df
    except Exception as e:
        print(f"指标计算出错: {e}")
        return df

def get_market_data():
    """获取并处理市场数据"""
    try:
        ohlcv = exchange.fetch_ohlcv(
            TRADE_CONFIG['symbol'], 
            TRADE_CONFIG['timeframe'], 
            limit=TRADE_CONFIG['data_points']
        )
        df = pd.DataFrame(ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
        df['ts'] = pd.to_datetime(df['ts'], unit='ms')
        
        df = calculate_technical_indicators(df)
        
        if len(df) < 20: return None

        curr = df.iloc[-1]
        
        # 趋势简单预判 (供Prompt参考)
        trend_status = "震荡"
        if curr['close'] > curr['sma_20'] > curr['sma_50']: trend_status = "多头排列(上涨)"
        if curr['close'] < curr['sma_20'] < curr['sma_50']: trend_status = "空头排列(下跌)"

        return {
            'price': curr['close'],
            'ts': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'indicators': {
                'rsi': round(curr['rsi'], 2),
                'macd': round(curr['macd'], 4),
                'macd_hist': round(curr['macd_hist'], 4),
                'bb_pct': round(curr['bb_pct'], 2),
                'atr': round(curr['atr'], 4),
                'trend': trend_status,
                'sma20_dist': round((curr['close'] - curr['sma_20'])/curr['sma_20']*100, 2)
            },
            'kline_history': df.tail(6).to_dict('records') # 最近6根K线
        }
    except Exception as e:
        print(f"数据获取失败: {e}")
        return None

def get_real_position():
    """获取OKX实盘持仓"""
    try:
        positions = exchange.fetch_positions([TRADE_CONFIG['symbol']])
        for pos in positions:
            if pos['symbol'] == TRADE_CONFIG['symbol']:
                amt = float(pos['contracts'])
                if amt > 0:
                    return {
                        'side': pos['side'], 
                        'size': amt,
                        'pnl': float(pos['unrealizedPnl'])
                    }
        return None
    except:
        return None

# --- 5. DeepSeek 分析核心 (Prompt优化版) ---

def analyze_market(data):
    """请求DeepSeek分析"""
    
    # 1. 准备持仓信息 (根据模式选择来源)
    if TRADE_CONFIG['test_mode']:
        pos = virtual_account
        if pos['side']:
            # 虚拟盈亏计算
            diff = (data['price'] - pos['entry_price']) if pos['side'] == 'long' else (pos['entry_price'] - data['price'])
            pnl = diff * pos['holdings'] * TRADE_CONFIG['contract_size']
            pos_str = f"{pos['side']}仓 {pos['holdings']}张 (浮盈 {pnl:.2f} U)"
        else:
            pos_str = "空仓 (无持仓)"
    else:
        real_pos = get_real_position()
        if real_pos:
            pos_str = f"{real_pos['side']}仓 {real_pos['size']}张 (浮盈 {real_pos['pnl']:.2f} U)"
        else:
            pos_str = "空仓"

    # 2. 构建 K线数据字符串
    kline_txt = ""
    for k in data['kline_history']:
        # 简单的K线描述: 时间 收盘价 涨跌幅
        change = (k['close'] - k['open']) / k['open'] * 100
        kline_txt += f"[{k['ts'].strftime('%H:%M')}] 收:{k['close']:.4f} 涨跌:{change:+.2f}% Vol:{k['vol']:.0f}\n"

    # 3. 构建 增强型 Prompt (关键！)
    # 告诉AI具体数据，而不是模糊的概念，有助于它做数学判断
    ind = data['indicators']
    
    prompt = f"""
    【角色设定】
    你是一名华尔街资深量化交易员，擅长趋势跟踪与波段交易。你的目标是本金安全第一，其次才是盈利。
    
    【市场快照】
    交易标的：{TRADE_CONFIG['symbol']} ({TRADE_CONFIG['timeframe']})
    当前价格：{data['price']}
    当前持仓：{pos_str}
    
    【技术面仪表盘】
    1. 趋势状态：{ind['trend']} (价格与SMA20偏离: {ind['sma20_dist']}%)
    2. 动能(MACD)：{ind['macd']} (柱状图: {ind['macd_hist']} {'增强' if abs(ind['macd_hist'])>0.0001 else '微弱'})
    3. 强弱(RSI)：{ind['rsi']} (超买>70, 超卖<30, 50为中轴)
    4. 波动(布林)：位置 {ind['bb_pct']} (0接近下轨反弹可能, 1接近上轨压力)
    5. 波动率(ATR)：{ind['atr']} (用于评估止损距离)

    【最近K线数据】
    {kline_txt}
    
    【交易逻辑要求】
    1. **顺势而为**：如果趋势是多头排列，优先寻找做多机会；空头反之。
    2. **震荡过滤**：如果布林带收口且MACD粘合，视为震荡，建议 HOLD。
    3. **不频繁交易**：只有当至少2个指标共振时才开单。
    4. **止损原则**：建议止损设置在当前价格 ± 2*ATR 的位置。

    【输出任务】
    分析上述数据，给出明确交易指令。
    返回严格的JSON格式：
    {{
        "signal": "BUY" (做多) 或 "SELL" (做空) 或 "HOLD" (观望),
        "reason": "50字以内的硬核逻辑分析，以及简要分析理由(包含趋势判断和技术依据)",
        "stop_loss": 建议止损价 (数字或null),
        "take_profit": 建议止盈价 (数字或null),
        "confidence": "HIGH" (高) 或 "MEDIUM" (中) 或 "LOW" (低)
    }}
    """

    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个只输出JSON的量化交易引擎，不要输出任何Markdown格式。"},
                {"role": "user", "content": prompt}
            ],
            stream=False,
            temperature=0.1 # 低温度保证输出稳定
        )
        
        raw_content = response.choices[0].message.content
        print(f"DeepSeek原始回复: {raw_content}")
        # 清洗可能存在的 markdown 符号
        clean_content = re.sub(r'```json|```', '', raw_content).strip()
        
        result = json.loads(clean_content)
        
        # 简单校验
        if result.get('signal') not in ['BUY', 'SELL', 'HOLD']:
            result['signal'] = 'HOLD'
            result['reason'] = 'AI返回格式异常，强制观望'
            
        return result

    except Exception as e:
        print(f"🧠 DeepSeek 思考失败: {e}")
        return {"signal": "HOLD", "reason": "API连接错误", "confidence": "LOW"}

# --- 6. 交易执行函数 (双模式) ---

def execute_trade(signal, current_price):
    """执行交易指令"""
    sig = signal['signal']
    reason = signal.get('reason', '无')
    conf = signal.get('confidence', 'LOW')
    
    print(f"🤖 AI指令: 【{sig}】 信心:{conf}")
    print(f"📝 逻辑: {reason}")
    if signal.get('stop_loss'):
        print(f"🛑 建议止损: {signal['stop_loss']}")

    # 过滤低信心信号
    if conf == 'LOW' and sig != 'HOLD':
        print("⚠️ 信心不足，放弃操作")
        return

    # ---------------- 模式 A: 模拟账户 (Test Mode) ----------------
    if TRADE_CONFIG['test_mode']:
        global virtual_account
        v_pos = virtual_account
        contract_val = TRADE_CONFIG['contract_size']
        
        print(f"🧪 [模拟账户] 余额: {v_pos['balance']:.2f} U")

        # 模拟买入
        if sig == 'BUY':
            # 平空
            if v_pos['side'] == 'short':
                pnl = (v_pos['entry_price'] - current_price) * v_pos['holdings'] * contract_val
                v_pos['balance'] += pnl
                print(f"🔄 模拟平空 | 盈亏: {pnl:+.2f} U")
                v_pos['side'] = None
            
            # 开多
            if v_pos['side'] is None:
                cost = current_price * TRADE_CONFIG['amount'] * contract_val / TRADE_CONFIG['leverage']
                if cost > v_pos['balance']:
                    print("⚠️ 模拟余额不足")
                else:
                    v_pos['side'] = 'long'
                    v_pos['entry_price'] = current_price
                    v_pos['holdings'] = TRADE_CONFIG['amount']
                    print(f"🚀 模拟开多 | 均价: {current_price}")

        # 模拟卖出
        elif sig == 'SELL':
            # 平多
            if v_pos['side'] == 'long':
                pnl = (current_price - v_pos['entry_price']) * v_pos['holdings'] * contract_val
                v_pos['balance'] += pnl
                print(f"🔄 模拟平多 | 盈亏: {pnl:+.2f} U")
                v_pos['side'] = None
            
            # 开空
            if v_pos['side'] is None:
                cost = current_price * TRADE_CONFIG['amount'] * contract_val / TRADE_CONFIG['leverage']
                if cost > v_pos['balance']:
                    print("⚠️ 模拟余额不足")
                else:
                    v_pos['side'] = 'short'
                    v_pos['entry_price'] = current_price
                    v_pos['holdings'] = TRADE_CONFIG['amount']
                    print(f"🐻 模拟开空 | 均价: {current_price}")
        
        return

    # ---------------- 模式 B: 实盘账户 (Live Mode) ----------------
    try:
        real_pos = get_real_position()
        
        # 资金检查 (放宽到95%)
        bal = exchange.fetch_balance()['USDT']['free']
        cost = current_price * TRADE_CONFIG['amount'] * TRADE_CONFIG['contract_size'] / TRADE_CONFIG['leverage']
        
        if cost > bal * 0.95:
            print(f"💸 实盘余额不足! 需{cost:.2f}, 有{bal:.2f}")
            return

        # 执行下单
        if sig == 'BUY':
            if real_pos and real_pos['side'] == 'short':
                print("🔄 实盘平空...")
                exchange.create_market_order(TRADE_CONFIG['symbol'], 'buy', real_pos['size'], params={'reduceOnly': True})
                time.sleep(2)
            
            if not real_pos or real_pos['side'] == 'short':
                print("🚀 实盘开多...")
                exchange.create_market_order(TRADE_CONFIG['symbol'], 'buy', TRADE_CONFIG['amount'])

        elif sig == 'SELL':
            if real_pos and real_pos['side'] == 'long':
                print("🔄 实盘平多...")
                exchange.create_market_order(TRADE_CONFIG['symbol'], 'sell', real_pos['size'], params={'reduceOnly': True})
                time.sleep(2)
            
            if not real_pos or real_pos['side'] == 'long':
                print("🐻 实盘开空...")
                exchange.create_market_order(TRADE_CONFIG['symbol'], 'sell', TRADE_CONFIG['amount'])

    except Exception as e:
        print(f"❌ 实盘下单错误: {e}")

# --- 7. 主循环 ---
def wait_until_next_candle():
    """通用型K线对齐函数：支持任意分钟周期的精准对齐"""
    now = datetime.now()
    tf_str = TRADE_CONFIG['timeframe']
    
    # 1. 解析周期 (提取分钟数)
    if tf_str.endswith('m'):
        interval_min = int(tf_str[:-1]) # '15m' -> 15
    elif tf_str.endswith('h'):
        interval_min = int(tf_str[:-1]) * 60 # '1h' -> 60
    else:
        # 如果是其他奇怪的周期（如1d），默认睡1分钟
        print(f"⚠️ 未知周期格式 {tf_str}，默认等待1分钟")
        return 60

    # 2. 计算下一个整点分钟
    # 例如当前 13:12, 周期 5m -> 下个点是 13:15
    # 例如当前 13:12, 周期 15m -> 下个点是 13:15
    current_total_min = now.minute
    
    # 下一个周期的分钟数
    next_cycle_min = ((current_total_min // interval_min) + 1) * interval_min
    
    # 计算需要等待的分钟数
    wait_minutes = next_cycle_min - current_total_min
    
    # 如果下一个周期跨越了小时（比如 55分 + 15分 = 70分），逻辑依然成立，因为我们只关心差值
    # 但为了精确计算秒数，我们将其转换为秒
    
    # 核心算法：(需要等待的完整分钟数 - 1) * 60 + (60 - 当前秒数)
    # 减1是因为当前这1分钟还没过完
    
    seconds = (wait_minutes - 1) * 60 + (60 - now.second)
    
    # 防止极端情况（比如刚好在00秒运行，可能算出负数或0）
    if seconds <= 0:
        seconds += interval_min * 60

    print(f"⏳ 周期[{tf_str}] | 当前 {now.strftime('%H:%M:%S')} | 等待 {int(seconds/60)}分 {seconds%60}秒 到达下一K线...")
    return seconds

def job():
    print("\n" + "="*50)
    print(f"⏰ {datetime.now().strftime('%H:%M:%S')} K线收盘，开始执行策略")
    
    data = get_market_data()
    if not data:
        print("⚠️ 数据获取失败，跳过本次")
        return

    print(f"💎 标的: {TRADE_CONFIG['symbol']} | 现价: {data['price']}")
    
    decision = analyze_market(data)
    execute_trade(decision, data['price'])
    print("="*50 + "\n")

def main():
    # 启用日志
    sys.stdout = Logger()
    
    print("🤖 DeepSeek 智能交易机器人 V3.1 (整点对齐版)")
    print(f"⚙️ 模式: {'🧪 模拟测试' if TRADE_CONFIG['test_mode'] else '💸 实盘交易'}")
    print(f"📊 周期: {TRADE_CONFIG['timeframe']}")
    
    if not setup_exchange():
        print("❌ 无法启动，请检查API配置")
        return

    # 1. 启动时先立刻跑一次，看一眼当前状态
    print("🚀 启动立即执行一次分析...")
    job()

    # 2. 进入死循环，永远等待下一个整点
    while True:
        try:
            # 计算需要睡多久
            sleep_sec = wait_until_next_candle()
            
            # 睡觉 (为了防止睡过头，稍微多睡1秒确保K线生成)
            time.sleep(sleep_sec + 2) 
            
            # 睡醒了，干活
            job()
            
        except KeyboardInterrupt:
            print("🛑 程序已停止")
            break
        except Exception as e:
            print(f"⚠️ 主进程错误: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()