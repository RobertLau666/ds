import os
import time
import schedule
from openai import OpenAI
import ccxt
import pandas as pd
from datetime import datetime
import json
import re
import sys
from dotenv import load_dotenv

load_dotenv()

# --- 新增：日志记录类 ---
class Logger(object):
    def __init__(self):
        # 创建 logs 文件夹
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        # 生成带时间戳的文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.filename = f"logs/log_{timestamp}.log"
        
        self.terminal = sys.stdout
        self.log = open(self.filename, 'a', encoding='utf-8')
        print(f"📄 日志将同时输出到控制台和文件: {self.filename}")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()  # 立即写入文件，防止程序崩溃丢失日志

    def flush(self):
        self.terminal.flush()
        self.log.flush()

# 初始化DeepSeek客户端
deepseek_client = OpenAI(
    api_key=os.getenv('DEEPSEEK_API_KEY'),
    base_url="https://api.deepseek.com"
)

# 初始化OKX交易所
exchange = ccxt.okx({
    'options': {
        'defaultType': 'swap',  # OKX使用swap表示永续合约
    },
    'apiKey': os.getenv('OKX_API_KEY'),
    'secret': os.getenv('OKX_SECRET'),
    'password': os.getenv('OKX_PASSWORD'),
})

# 交易参数配置
TRADE_CONFIG = {
    'symbol': 'BTC/USDT:USDT',  
    'amount': 0.01,         # 0.01 BTC 约等于 900 U 价值
    'leverage': 10,         # 必须10倍，否则100U本金买不起
    'timeframe': '15m',     # 周期
    'test_mode': True,      # <--- 已修改：开启测试模式，先看效果
    'data_points': 96,
    'analysis_periods': {
        'short_term': 20,
        'medium_term': 50,
        'long_term': 96
    }
}

# 全局变量
price_history = []
signal_history = []
position = None


def setup_exchange():
    """设置交易所参数"""
    try:
        # OKX设置杠杆
        exchange.set_leverage(
            TRADE_CONFIG['leverage'],
            TRADE_CONFIG['symbol'],
            {'mgnMode': 'cross'}  # 全仓模式
        )
        print(f"设置杠杆倍数: {TRADE_CONFIG['leverage']}x")

        # 获取余额
        balance = exchange.fetch_balance()
        usdt_balance = balance.get('USDT', {}).get('free', 0)
        print(f"当前USDT余额: {usdt_balance:.2f}")

        return True
    except Exception as e:
        print(f"交易所设置失败: {e}")
        return False


def calculate_technical_indicators(df):
    """计算技术指标"""
    try:
        # 移动平均线
        df['sma_5'] = df['close'].rolling(window=5, min_periods=1).mean()
        df['sma_20'] = df['close'].rolling(window=20, min_periods=1).mean()
        df['sma_50'] = df['close'].rolling(window=50, min_periods=1).mean()

        # MACD
        df['ema_12'] = df['close'].ewm(span=12).mean()
        df['ema_26'] = df['close'].ewm(span=26).mean()
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # 布林带
        df['bb_middle'] = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # 支撑阻力
        df['resistance'] = df['high'].rolling(20).max()
        df['support'] = df['low'].rolling(20).min()

        df = df.bfill().ffill()
        return df
    except Exception as e:
        print(f"技术指标计算失败: {e}")
        return df


def get_market_trend(df):
    """判断市场趋势"""
    try:
        current_price = df['close'].iloc[-1]
        trend_short = "上涨" if current_price > df['sma_20'].iloc[-1] else "下跌"
        trend_medium = "上涨" if current_price > df['sma_50'].iloc[-1] else "下跌"
        macd_trend = "bullish" if df['macd'].iloc[-1] > df['macd_signal'].iloc[-1] else "bearish"

        if trend_short == "上涨" and trend_medium == "上涨":
            overall_trend = "强势上涨"
        elif trend_short == "下跌" and trend_medium == "下跌":
            overall_trend = "强势下跌"
        else:
            overall_trend = "震荡整理"

        return {
            'short_term': trend_short,
            'medium_term': trend_medium,
            'macd': macd_trend,
            'overall': overall_trend
        }
    except Exception as e:
        return {}


def get_btc_ohlcv_enhanced():
    """获取K线数据并计算指标"""
    try:
        ohlcv = exchange.fetch_ohlcv(TRADE_CONFIG['symbol'], TRADE_CONFIG['timeframe'], limit=TRADE_CONFIG['data_points'])
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        df = calculate_technical_indicators(df)
        
        # 确保数据足够
        if len(df) < 5:
            return None

        current_data = df.iloc[-1]
        previous_data = df.iloc[-2]

        return {
            'price': current_data['close'],
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'high': current_data['high'],
            'low': current_data['low'],
            'volume': current_data['volume'],
            'price_change': ((current_data['close'] - previous_data['close']) / previous_data['close']) * 100,
            'kline_data': df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].tail(10).to_dict('records'),
            'technical_data': {
                'rsi': current_data.get('rsi', 0),
                'macd': current_data.get('macd', 0),
                'bb_position': current_data.get('bb_position', 0),
                'sma_5': current_data.get('sma_5', 0),
                'sma_20': current_data.get('sma_20', 0),
                'sma_50': current_data.get('sma_50', 0)
            },
            'trend_analysis': get_market_trend(df)
        }
    except Exception as e:
        print(f"获取K线数据失败: {e}")
        return None


def get_current_position():
    """获取当前持仓"""
    try:
        positions = exchange.fetch_positions([TRADE_CONFIG['symbol']])
        for pos in positions:
            if pos['symbol'] == TRADE_CONFIG['symbol']:
                contracts = float(pos['contracts']) if pos['contracts'] else 0
                if contracts > 0:
                    return {
                        'side': pos['side'],
                        'size': contracts,
                        'entry_price': float(pos['entryPrice']) if pos['entryPrice'] else 0,
                        'unrealized_pnl': float(pos['unrealizedPnl']) if pos['unrealizedPnl'] else 0
                    }
        return None
    except Exception as e:
        print(f"获取持仓失败: {e}")
        return None


def safe_json_parse(json_str):
    """安全解析JSON"""
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        try:
            # 简单的修复尝试
            json_str = json_str.replace("'", '"')
            json_str = re.sub(r'(\w+):', r'"\1":', json_str)
            return json.loads(json_str)
        except:
            return None


def create_fallback_signal(price_data):
    """备用信号"""
    return {
        "signal": "HOLD",
        "reason": "技术分析数据不足或解析失败，保守观望",
        "stop_loss": None,
        "take_profit": None,
        "confidence": "LOW",
        "is_fallback": True
    }


def analyze_with_deepseek(price_data):
    """DeepSeek分析核心"""
    
    # 1. 安全处理持仓文本
    current_pos = get_current_position()
    if current_pos:
        position_text = f"{current_pos['side']}仓, 数量: {current_pos['size']}"
        pnl_value = f"{current_pos['unrealized_pnl']:.2f}"
    else:
        position_text = "无持仓"
        pnl_value = "0.00"

    # 构建Prompt
    tech = price_data['technical_data']
    trend = price_data['trend_analysis']
    
    kline_str = ""
    for i, k in enumerate(price_data['kline_data'][-5:]):
        kline_str += f"K线{i}: 开{k['open']} 收{k['close']} 涨跌{((k['close']-k['open'])/k['open']*100):.2f}%\n"

    prompt = f"""
    角色：加密货币交易专家。
    资产：{TRADE_CONFIG['symbol']} | 周期：{TRADE_CONFIG['timeframe']}
    
    【行情数据】
    现价：${price_data['price']:,.2f} | 涨跌幅：{price_data['price_change']:.2f}%
    持仓状态：{position_text} | 浮动盈亏：{pnl_value} USDT
    
    【近期K线】
    {kline_str}
    
    【技术指标】
    RSI(14)：{tech['rsi']:.1f}
    布林带位置：{tech['bb_position']:.2f} (0=下轨, 0.5=中轨, 1=上轨)
    MACD趋势：{trend.get('macd', 'N/A')}
    整体趋势：{trend.get('overall', 'N/A')}
    
    【指令】
    请根据上述数据判断交易方向。
    如果是HOLD，止损止盈可以填 null。
    请严格返回JSON格式：
    {{
        "signal": "BUY" 或 "SELL" 或 "HOLD",
        "reason": "简短理由",
        "stop_loss": 具体数字或null,
        "take_profit": 具体数字或null,
        "confidence": "HIGH" 或 "MEDIUM" 或 "LOW"
    }}
    """

    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个严格输出JSON的量化交易助手。"},
                {"role": "user", "content": prompt}
            ],
            stream=False,
            temperature=0.1
        )
        
        result = response.choices[0].message.content
        print(f"DeepSeek原始回复: {result}")
        
        # 提取JSON
        start = result.find('{')
        end = result.rfind('}') + 1
        if start == -1 or end == 0:
            return create_fallback_signal(price_data)
            
        signal_data = safe_json_parse(result[start:end])
        
        # 验证必需字段（安全检查）
        required_fields = ['signal', 'reason', 'stop_loss', 'take_profit', 'confidence']
        is_valid = True
        for field in required_fields:
            if field not in signal_data:
                is_valid = False
                break
            # 只有非HOLD信号才严格检查价格是否为数字
            if signal_data['signal'] != 'HOLD' and field in ['stop_loss', 'take_profit']:
                if signal_data[field] is None:
                    is_valid = False
        
        if not is_valid:
             print("⚠️ 返回数据格式校验未通过，转HOLD")
             return create_fallback_signal(price_data)
            
        # 记录历史
        signal_data['timestamp'] = price_data['timestamp']
        signal_history.append(signal_data)
        if len(signal_history) > 30:
            signal_history.pop(0)
            
        return signal_data
        
    except Exception as e:
        print(f"DeepSeek请求异常: {e}")
        return create_fallback_signal(price_data)


def execute_trade(signal_data, price_data):
    """执行交易"""
    current_position = get_current_position()
    
    # --- 安全打印逻辑 ---
    sig = signal_data.get('signal', 'N/A')
    conf = signal_data.get('confidence', 'N/A')
    reason = signal_data.get('reason', 'N/A')
    
    sl = signal_data.get('stop_loss')
    tp = signal_data.get('take_profit')
    
    sl_str = f"${sl:,.2f}" if (sl is not None and isinstance(sl, (int, float))) else "N/A"
    tp_str = f"${tp:,.2f}" if (tp is not None and isinstance(tp, (int, float))) else "N/A"

    print(f"🤖 信号: {sig} | 信心: {conf}")
    print(f"📝 理由: {reason}")
    print(f"🛑 止损: {sl_str} | 🎯 止盈: {tp_str}")
    print(f"💼 当前持仓: {current_position}")
    
    if TRADE_CONFIG['test_mode']:
        print("🧪 测试模式：不执行真实下单 (只模拟逻辑)")
        # 即使是测试模式，也模拟检查一下资金是否足够
        balance = exchange.fetch_balance()
        usdt_balance = balance.get('USDT', {}).get('free', 0)
        required_margin = price_data['price'] * TRADE_CONFIG['amount'] / TRADE_CONFIG['leverage']
        # <--- 修改点：这里改为0.95，模拟你的资金状况
        if required_margin > usdt_balance * 0.95: 
            print(f"⚠️ [模拟检测] 警告：保证金可能不足 (需:{required_margin:.2f}, 有:{usdt_balance:.2f})")
        return

    # 风险管理：低信心不交易
    if conf == 'LOW' and sig != 'HOLD':
        print("⚠️ 信心不足，跳过交易")
        return

    try:
        # 获取余额检查
        balance = exchange.fetch_balance()
        usdt_balance = balance.get('USDT', {}).get('free', 0)
        required_margin = price_data['price'] * TRADE_CONFIG['amount'] / TRADE_CONFIG['leverage']

        # <--- 修改点：放宽资金限制到 95% --->
        if required_margin > usdt_balance * 0.95:
            print(f"⚠️ 保证金不足，跳过交易。需要: {required_margin:.2f} USDT, 可用: {usdt_balance:.2f} USDT")
            return

        # 简单交易逻辑
        if sig == 'BUY':
            if current_position and current_position['side'] == 'short':
                print("🔄 平空仓...")
                exchange.create_market_order(TRADE_CONFIG['symbol'], 'buy', current_position['size'], params={'reduceOnly': True})
                time.sleep(1)
            
            if not current_position or current_position['side'] == 'short':
                print("🚀 开多仓...")
                exchange.create_market_order(TRADE_CONFIG['symbol'], 'buy', TRADE_CONFIG['amount'], params={})
                
        elif sig == 'SELL':
            if current_position and current_position['side'] == 'long':
                print("🔄 平多仓...")
                exchange.create_market_order(TRADE_CONFIG['symbol'], 'sell', current_position['size'], params={'reduceOnly': True})
                time.sleep(1)
            
            if not current_position or current_position['side'] == 'long':
                print("🐻 开空仓...")
                exchange.create_market_order(TRADE_CONFIG['symbol'], 'sell', TRADE_CONFIG['amount'], params={})

    except Exception as e:
        print(f"❌ 下单失败: {e}")


def wait_for_next_period():
    """智能等待"""
    now = datetime.now()
    tf = TRADE_CONFIG['timeframe']
    
    if tf == '1m':
        seconds = 60 - now.second
        print(f"⏳ [调试] 等待 {seconds} 秒到下一分钟...")
        return seconds
    
    next_min = ((now.minute // 15) + 1) * 15
    if next_min == 60: next_min = 0
    
    wait_min = next_min - now.minute if next_min > now.minute else (60 - now.minute + next_min)
    seconds = wait_min * 60 - now.second
    
    print(f"⏳ 等待 {wait_min-1 if now.second>0 else wait_min}分 {60-now.second if now.second>0 else 0}秒 到整点...")
    return seconds


def trading_bot():
    """主循环"""
    wait_sec = wait_for_next_period()
    if wait_sec > 0:
        time.sleep(wait_sec)

    print("\n" + "="*50)
    print(f"⏰ 执行时间: {datetime.now().strftime('%H:%M:%S')}")
    
    price_data = get_btc_ohlcv_enhanced()
    if not price_data:
        print("❌ 获取数据失败")
        return

    print(f"💎 {TRADE_CONFIG['symbol']} 现价: ${price_data['price']:,.2f}")
    
    signal_data = analyze_with_deepseek(price_data)
    execute_trade(signal_data, price_data)


def main():
    # --- 初始化日志 ---
    # 这会把所有 print 输出同时写到文件里
    sys.stdout = Logger()
    
    print(f"🤖 DeepSeek 交易机器人启动 | 周期: {TRADE_CONFIG['timeframe']}")
    print(f"🧪 测试模式: {'开启' if TRADE_CONFIG['test_mode'] else '关闭'}")
    
    if not setup_exchange():
        print("❌ 交易所连接失败，请检查API Key")
        return

    while True:
        try:
            trading_bot()
            time.sleep(5) 
        except KeyboardInterrupt:
            print("🛑 机器人已停止")
            break
        except Exception as e:
            print(f"⚠️ 主循环报错: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(10)

if __name__ == "__main__":
    main()