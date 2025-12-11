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
Prepare an server, recommended: Alibaba Cloud [轻量应用服务器](https://swasnext.console.aliyun.com/buy?regionId=ap-northeast-1#/)
```
实例：
    通用型
    ¥34/月
镜像：
    系统镜像 Ubuntu
    版本：默认
地域：
    日本（东京）
购买配置：
    数量：1
    时长：1个月
    启用自动续费：
```
Change the password, then click "Remote Connection" or use VSCode (The SSH configuration is as follows) for remote connection to log in to the server.
```
Host [Public IP address]
    HostName [Public IP address]
    User root
    Port 22
```

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
1. First, set ```'test_mode': True``` to test with a simulated account,
2. Then change to ```'test_mode': False``` to start live trading.
```
python app_v2.py
```

## Code Version Analysis
[version_info.md](old_versions/version_info.md)

## Reference
- Follow on Twitter for strategy insights: https://x.com/huojichuanqi
- AI Stock Trading Competition: https://nof1.ai/
- Video Tutorial: https://www.youtube.com/watch?v=Yv-AMVaWUVg
- Using Tiered Trailing Stop-Loss/Take-Profit: https://youtu.be/-vfeyqUkuzY