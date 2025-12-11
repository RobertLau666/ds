# TradingBot
**TradingBot** is a stock trading bot that uses large language models (such as DeepSeek).

## Configuration
### set_env.sh
Download ```.env``` from my Google Drive or create a new ```.env``` file with your API keys. Place it in the project root directory.
```
DEEPSEEK_API_KEY=
BINANCE_API_KEY=
BINANCE_SECRET=
OKX_API_KEY=
OKX_SECRET=
OKX_PASSWORD=
```

### Environment Setup
Prepare an Ubuntu server (recommended: Alibaba Cloud, Japan/Hong Kong/Singapore regions - [Lightweight Cloud Server](https://swasnext.console.aliyun.com/buy?regionId=ap-northeast-1#/))

```
# Install conda
wget https://repo.anaconda.com/archive/Anaconda3-2024.10-1-Linux-x86_64.sh
bash Anaconda3-2024.10-1-Linux-x86_64.sh
source ~/.bashrc

# Create virtual environment
conda create -n ds python=3.10
conda activate ds
pip install -r requirements.txt
```

## Run
1. Remove all "tag" parameters from the code. This tag indicates to OKX that the user was referred by code owner 60b...CDE, resulting in the code owner receiving a portion of your trading fees as commission.
2. First, set 'test_mode': True to test with a simulated account
3. Then change to 'test_mode': False to start live trading
```
python my_deepseek_ok_plus_indicators_v2.py
```

## Code Version Analysis
[version_info.md](old_vesions/version_info.md)

## Reference
- Follow on Twitter for strategy insights: https://x.com/huojichuanqi
- AI Stock Trading Competition: https://nof1.ai/
- Video Tutorial: https://www.youtube.com/watch?v=Yv-AMVaWUVg
- Using Tiered Trailing Stop-Loss/Take-Profit: https://youtu.be/-vfeyqUkuzY