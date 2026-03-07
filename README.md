# 🤖 GigaBot AI Memecoin Trader

GigaBot is an autonomous trading bot for Bybit (Spot) that uses **Google Gemini AI** to analyze market trends and execute trades. It features a modern PHP dashboard for real-time monitoring and dynamic configuration.

## 🚀 Key Features

*   **AI-Powered Analysis:** Uses Gemini Pro to interpret 2 hours of incremental candle data, RSI, trends, and market liquidity.
*   **Multi-Asset Management:** Monitors multiple memecoins simultaneously with individual scheduling.
*   **Dual-Frequency Engine:** High-frequency checks for active wallet positions (Stop Loss/Take Profit) and lower frequency for new opportunities.
*   **Auto-Funding:** Automatically detects and transfers USDT from Funding to Trading Unified accounts when needed.
*   **Modern Dashboard:** Real-time Tailwind CSS interface with performance charts, AI reasoning logs, and clickable TradingView charts.
*   **Hot Reload:** Change configurations in the `.env` via UI without restarting the Python process.

---

## 🛠️ Installation

### 1. Requirements
*   Python 3.10+
*   PHP 8.0+ (with SQLite support)
*   Bybit API Keys (Testnet or Mainnet)
*   Google Gemini API Key

### 2. Setup
Clone the repository and install dependencies:
```bash
git clone https://github.com/ojaneri/gigabot.git
cd gigabot
pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the root directory:
```env
BYBIT_API_KEY=your_bybit_key
BYBIT_API_SECRET=your_bybit_secret
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-1.5-pro-preview

# Trading Params
MEMECOIN_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,PEPEUSDT
TRADE_AMOUNT_USD=15.0
RISK_LEVEL=50
MAX_OPEN_TRADES=3
STOP_LOSS_PCT=0.05
TAKE_PROFIT_PCT=0.10

# Scheduling
FREQ_CARTEIRA_MINUTOS=2
FREQ_OPORTUNIDADES_MINUTOS=10
HISTORY_MINUTES=120
```

### 4. Proxies (Optional)
If you need to use proxies to bypass regional restrictions (Bybit blocks some countries like the US), create a `proxies.json`:
```json
[
  {
    "ip": "1.2.3.4",
    "port": "8080",
    "user": "username",
    "pass": "password"
  }
]
```

---

## 🚦 How to Use

### Start the Bot
Use the provided shell script to manage the process:
```bash
chmod +x run.sh
./run.sh --start
```

Commands:
*   `./run.sh --start`: Start in background.
*   `./run.sh --stop`: Stop the bot.
*   `./run.sh --restart`: Apply code changes.
*   `./run.sh --status`: Check if it's running.

### Access the Dashboard
Point your web server (Apache/Nginx) to the root folder and open `index.php`.
*   **Monitor:** View real-time PnL, active positions, and AI logic.
*   **Configure:** Use the **Config** button to edit `.env` parameters dynamically.

---

## 📊 Database Structure
The bot uses a local SQLite database (`trades.db`) with three main tables:
1.  `trades`: Stores all executed buy/sell orders.
2.  `analyses`: Logs every decision made by Gemini (Buy/Sell/Hold) including the reasoning.
3.  `klines`: Caches incremental market data to save API credits and provide history to the AI.

---

## 🛡️ Security
*   **Credentials:** Never commit your `.env` or `proxies.json`. They are ignored by default in `.gitignore`.
*   **Testnet:** Always start on Bybit Testnet to validate strategies before moving to Mainnet.

## 📄 License
MIT License. Created by [Janeri Systems](https://janeri.com.br).
