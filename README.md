# ds
## 简介
- 个人喜欢玩黑箱文化，你们不一样，别上头。
- 搞这个目的是先确定ds的一些东西，不是商业化产品，主体思路是围绕试验证伪去的
- 关注推特了解思路来龙去脉：https://x.com/huojichuanqi
- 注意为了简化逻辑，记得改 单向持仓  单向持仓 单向持仓
- 目前最有价值的就是ds+指标方案，但是基础版本是本地算好给他，我们正在尝试用ds直接分析指标，但是效果没看出来
- 情绪指标那边要收费了，有兴趣的只能直接联系商用了： TG：@Sam4sea
- 打赏地址（TRC20）：TUunBuqQ1ZDYt9WrA3ZarndFPQgefXqZAM

## 教程
1. 视频教程：https://www.youtube.com/watch?v=Yv-AMVaWUVg
2. 配合分档移动止盈止损：https://youtu.be/-vfeyqUkuzY

## 配置内容
### set_env.sh
Download [.env](https://drive.google.com/file/d/1e6_sHdstP1mFR8n9Ch6kJTH17jjAtLSs/view?usp=drive_link) or set API KEY in a new created file ```.env``` under project root dir.
```
DEEPSEEK_API_KEY=
BINANCE_API_KEY=
BINANCE_SECRET=
OKX_API_KEY=
OKX_SECRET=
OKX_PASSWORD=
```

### 环境配置
准备一台ubuntu服务器 推荐阿里云 香港或者新加坡 轻云服务器
```
# Install conda
wget https://repo.anaconda.com/archive/Anaconda3-2024.10-1-Linux-x86_64.sh
bash Anaconda3-2024.10-1-Linux-x86_64.sh
source /root/anaconda3/etc/profile.d/conda.sh 
echo ". /root/anaconda3/etc/profile.d/conda.sh" >> ~/.bashrc

# create virtual environment
conda create -n ds python=3.10
conda activate ds
pip install -r requirements.txt
# apt-get update 更新镜像源
# apt-get upgrade 必要库的一个升级
# apt install npm 安装npm
# npm install pm2 -g 使用npm安装pm2
# conda create -n trail3 python=4.10
```

### Run
1. 去除代码中的所有"tag"参数，它的作用是：当你的机器人带着这个 tag 去 OKX 下单时，OKX 系统会判定：“这个用户是由代码持有者 60bb4a8d3416BCDE 带来的”。结果就是：你每笔交易支付的手续费中，会有一部分被 OKX 分给写这个代码的人。
2. 先修改'test_mode': True, 测试一下
```
python deepseek_ok_带指标plus版本.py
```



### 代码版本分析
经过仔细对比分析，这四个版本中，deepseek_ok_带指标plus版本.py (第3个文件) 和 deepseek_ok_带市场情绪+指标版本.py (第2个文件) 明显优于另外两个。
如果非要选一个目前最稳健、最适合实盘的，我推荐 deepseek_ok_带指标plus版本.py（即“带指标Plus版”）。
以下是详细的评测和对比分析：
1. 版本横向对比评测
| 特性 | 1. 基础版（deepseek_ok版本） | 2. 情绪+指标版（带市场情绪+指标） | 3. 指标Plus版（带指标plus） | 4. Binance版（deepseek.py） |
|------|------------------------------|----------------------------------|-------------------------------|-------------------------------|
| 交易所 | OKX | OKX | OKX | Binance |
| 数据投喂 | 极少（仅5根K线 + 简单均线） | 极丰富（RSI, MACD, 布林带, 趋势, 情绪） | 丰富（同上，但无外部情绪数据） | 极少 |
| 技术分析 | 靠 DeepSeek 瞎猜 | Python 算好指标喂给 AI | Python 算好指标喂给 AI | 靠 DeepSeek 瞎猜 |
| 交易逻辑 | 简单买/卖/平 | 智能仓位（动态调整手数）+ 加减仓 | 固定手数 + 保证金检查 | 简单买/卖/平 |
| 执行时机 | 随时运行（K线未收盘） | 整点等待（等待15分钟收盘） | 整点等待（等待15分钟收盘） | 随时运行 |
| 外部依赖 | 无 | 高（依赖 cryptoracle API 获取情绪） | 无（仅依赖交易所数据） | 无 |
| 稳定性 | 高（代码少） | 中（情绪 API 可能挂掉） | 高（自给自足） | 高 |

2. 为什么不用另外两个？
- ❌ deepseek_ok版本.py (基础版)：
太简陋：它只给了 AI 最近 5 根 K 线的价格。DeepSeek 不是数学家，它很难光看几个数字就算出 RSI 或 MACD。
幻觉风险：因为缺乏硬性指标支撑，AI 很容易产生“我觉得要涨”的幻觉。
Prompt 问题：使用的是“救救生病的母亲”这种玄学提示词，虽然有趣但不专业。
- ❌ deepseek.py (Binance版)：
如果你是用 OKX，这个代码直接用不了。逻辑和基础版一样简陋。

3. 为什么推荐 带指标plus版本 而不是 情绪版？
虽然 带市场情绪+指标版本 (文件2) 看起来功能最强大（有智能仓位、有市场情绪），但我认为 带指标plus版本 (文件3) 更适合长期运行，原因如下：
- A. 外部 API 的风险 (文件2的硬伤)
文件2依赖一个外部 API 获取情绪数据：
code
Python
API_URL = "https://service.cryptoracle.network/..."
API_KEY = "7ad48a56-..." # 这是一个硬编码的Key
失效风险：这个 Key 看起来是公开共享的，随时可能因为请求过多被封禁，或者服务商接口改版。
阻塞风险：如果这个 API 请求超时，整个机器人会卡住，导致错过下单时机。
文件3移除了这个依赖，完全依靠 K 线计算出的技术指标（RSI, MACD等），这些数据永远是实时的、可靠的。
- B. 智能仓位的双刃剑 (文件2的风险)
文件2有一个 calculate_intelligent_position 函数，会根据“信心”调整下单金额（比如高信心下 1.5 倍，低信心下 0.5 倍）。
风险：DeepSeek 可能会错误地给出“HIGH”信心。如果是错误的判断加上 1.5 倍的仓位，亏损会放大。
文件3使用固定手数 (amount: 0.01)，虽然赚得可能慢点，但在不可预测的行情中更容易控制回撤。
- C. 时间对齐 (文件2和3都有)
文件2和3都增加了 wait_for_next_period 函数。
这是一个巨大的改进。它确保机器人在 10:00:01, 10:15:01 这种时间点运行。
这意味着 AI 分析的是已经收盘确定的 K 线，而不是还在跳动的 K 线，大大提高了准确率。

4. 最终建议与优化步骤
我建议你使用 deepseek_ok_带指标plus版本.py (第3个文件) 作为基础，但需要做一点微小的修改以达到最佳状态：
- 步骤 1：清理返佣代码
哪怕你选了最好的代码，里面的 tag 依然存在。请务必删除：
搜索 'tag': '60bb4a8d3416BCDE' 并删除。
保留 reduceOnly: True。
- 步骤 2：微调提示词 (Prompt)
文件3的 Prompt 已经很好了，但可以把文件2里的这一条加进去（如果文件3没写的话）：
"趋势(均线排列) > RSI > MACD > 布林带"
- 步骤 3：关于智能仓位 (可选)
如果你非常想要文件2里的“智能仓位”功能（根据信心加减仓），你可以把文件2里的 calculate_intelligent_position 函数复制到文件3里用，但是建议把倍数调低一点（例如最大 1.2 倍），防止 AI 发疯。

结论：
直接运行 deepseek_ok_带指标plus版本.py 是最安全、最稳健的选择。它不需要外部情绪数据，计算指标扎实，且包含资金安全检查。