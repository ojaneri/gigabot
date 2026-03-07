"""
Bybit Memecoin AI Trading Bot
Usa Gemini para análise e decisão de trades
Configurado para TESTNET
"""

import os
import time
import hmac
import hashlib
import json
import logging
import requests
import sqlite3
import warnings
import uuid
from datetime import datetime
from dotenv import load_dotenv
from coin_manager import coin_manager

# Suppress Google API warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="google.api_core")

import google.generativeai as genai

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CONFIGURAÇÃO DINÂMICA
# ─────────────────────────────────────────────

def load_config():
    """Recarrega configurações do .env a cada ciclo"""
    load_dotenv(override=True)
    
    try:
        risk_level = int(os.getenv("RISK_LEVEL", 50))
        risk_level = max(1, min(100, risk_level)) # Clamp 1-100
    except:
        risk_level = 50

    return {
        "BYBIT_API_KEY":    os.getenv("BYBIT_API_KEY"),
        "BYBIT_API_SECRET": os.getenv("BYBIT_API_SECRET"),
        "GEMINI_API_KEY":   os.getenv("GEMINI_API_KEY"),
        "GEMINI_MODEL":     os.getenv("GEMINI_MODEL", "gemini-3.1-flash"),
        "BYBIT_BASE_URL":   "https://api-testnet.bybit.com",
        
        # Dinâmicos
        "SYMBOLS":          [s.strip() for s in os.getenv("MEMECOIN_SYMBOLS", "DOGEUSDT").split(",")],
        "TRADE_AMOUNT":     float(os.getenv("TRADE_AMOUNT_USD", 10.0)),
        "RISK_LEVEL":       risk_level,
        "MAX_TRADES":       int(os.getenv("MAX_OPEN_TRADES", 1)),
        "STOP_LOSS":        float(os.getenv("STOP_LOSS_PCT", 0.03)),
        "TAKE_PROFIT":      float(os.getenv("TAKE_PROFIT_PCT", 0.06)),
        "FREQ_CARTEIRA":    int(os.getenv("FREQ_CARTEIRA_MINUTOS", 2)) * 60,
        "FREQ_OPORTUNIDADES": int(os.getenv("FREQ_OPORTUNIDADES_MINUTOS", 10)) * 60,
        "HISTORY_MINUTES":  int(os.getenv("HISTORY_MINUTES", 120))
    }

# Carregar config inicial para setup de API
config = load_config()

if not config["GEMINI_API_KEY"]:
    log.error("❌ GEMINI_API_KEY não encontrada no arquivo .env")
    exit(1)

genai.configure(api_key=config["GEMINI_API_KEY"])
model = genai.GenerativeModel(config["GEMINI_MODEL"])

# Headers padrão
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ══════════════════════════════════════════════
# DATABASE MANAGER (SQLite)
# ══════════════════════════════════════════════

class DatabaseManager:
    def __init__(self, db_path="trades.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    side TEXT,
                    qty REAL,
                    price REAL,
                    cost REAL,
                    pnl REAL,
                    reason TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    action TEXT,
                    confidence REAL,
                    risk TEXT,
                    reason TEXT,
                    price REAL,
                    result TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS klines (
                    symbol TEXT,
                    timestamp INTEGER,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    PRIMARY KEY (symbol, timestamp)
                )
            """)
            conn.commit()

    def log_trade(self, symbol, side, qty, price, pnl=0.0, reason=""):
        cost = qty * price
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO trades (symbol, side, qty, price, cost, pnl, reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (symbol, side, qty, price, cost, pnl, reason))
                conn.commit()
            log.info(f"💾 Trade salvo no Banco: {side} {qty} {symbol} @ {price}")
        except Exception as e:
            log.error(f"❌ Erro ao salvar no SQLite: {e}")

    def log_analysis(self, symbol, action, confidence, risk, reason, price, result=""):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO analyses (symbol, action, confidence, risk, reason, price, result)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (symbol, action, confidence, risk, reason, price, result))
                conn.commit()
        except Exception as e:
            log.error(f"❌ Erro ao salvar análise no SQLite: {e}")

    def save_klines(self, symbol, kline_list):
        """Salva candles no banco ignorando duplicatas"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for k in kline_list:
                    # k = [timestamp, open, high, low, close, volume, turnover]
                    cursor.execute("""
                        INSERT OR IGNORE INTO klines (symbol, timestamp, open, high, low, close, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (symbol, int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])))
                conn.commit()
        except Exception as e:
            log.error(f"❌ Erro ao salvar klines: {e}")

    def get_latest_kline_timestamp(self, symbol):
        """Retorna o timestamp do último candle salvo"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                res = conn.execute("SELECT MAX(timestamp) FROM klines WHERE symbol=?", (symbol,)).fetchone()
                return res[0] if res[0] else 0
        except:
            return 0

    def get_history(self, symbol, minutes):
        """Retorna os últimos N minutos de candles do banco"""
        limit_ts = int((time.time() - (minutes * 60)) * 1000)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                res = cursor.execute("""
                    SELECT timestamp, open, high, low, close, volume 
                    FROM klines 
                    WHERE symbol=? AND timestamp >= ? 
                    ORDER BY timestamp ASC
                """, (symbol, limit_ts)).fetchall()
                return res
        except Exception as e:
            log.error(f"Erro ao buscar histórico: {e}")
            return []

    def get_open_positions(self):
        """Tenta reconstruir posições abertas baseando-se no histórico de trades"""
        positions = {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Buscar moedas que têm mais compras que vendas (simplificado)
                # Ou moedas cujo último trade foi BUY e não houve SELL posterior
                cursor = conn.cursor()
                symbols = cursor.execute("SELECT DISTINCT symbol FROM trades").fetchall()
                for (sym,) in symbols:
                    # Somar Qty: Buy (+) / Sell (-)
                    qty_bal = cursor.execute("SELECT SUM(CASE WHEN side='BUY' THEN qty ELSE -qty END) FROM trades WHERE symbol=?", (sym,)).fetchone()[0]
                    if qty_bal and qty_bal > 0.000001:
                        # Pegar o último preço de compra como entry_price
                        last_buy = cursor.execute("SELECT price, timestamp FROM trades WHERE symbol=? AND side='BUY' ORDER BY id DESC LIMIT 1", (sym,)).fetchone()
                        if last_buy:
                            positions[sym] = {
                                "qty": qty_bal,
                                "price": last_buy[0],
                                "timestamp": last_buy[1]
                            }
            return positions
        except Exception as e:
            log.error(f"Erro ao recuperar posições: {e}")
            return {}

db = DatabaseManager()

# ══════════════════════════════════════════════
# PROXY MANAGER
# ══════════════════════════════════════════════

class ProxyManager:
    def __init__(self, file_path="proxies.json"):
        self.file_path = file_path
        self.proxies = self._load_proxies()
        self.current_index = 0

    def _load_proxies(self):
        try:
            with open(self.file_path, "r") as f:
                proxies = json.load(f)
                return sorted(proxies, key=lambda p: p.get('working', False), reverse=True)
        except Exception as e:
            log.error(f"Erro ao carregar proxies: {e}")
            return []

    def get_next_proxy(self):
        if not self.proxies:
            return None
        proxy = self.proxies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxies)
        
        proxy_url = f"http://{proxy['user']}:{proxy['pass']}@{proxy['ip']}:{proxy['port']}"
        return {
            "http": proxy_url,
            "https": proxy_url
        }

    def mark_working(self, proxy_data):
        try:
            updated = False
            for p in self.proxies:
                if p['ip'] == proxy_data['ip'] and p['port'] == proxy_data['port']:
                    if not p.get('working'):
                        p['working'] = True
                        updated = True
                    p['last_success'] = datetime.utcnow().isoformat()
            
            if updated:
                with open(self.file_path, "w") as f:
                    json.dump(self.proxies, f, indent=2)
        except Exception as e:
            log.error(f"Erro ao salvar proxy status: {e}")

proxy_manager = ProxyManager()

# ══════════════════════════════════════════════
# BYBIT API
# ══════════════════════════════════════════════

def _sign(params: dict, secret: str, timestamp: str, recv_window: str = "5000") -> str:
    param_str = timestamp + config["BYBIT_API_KEY"] + recv_window + "&".join(
        f"{k}={v}" for k, v in sorted(params.items())
    )
    return hmac.new(secret.encode(), param_str.encode(), hashlib.sha256).hexdigest()

def bybit_request(method: str, endpoint: str, params: dict = None, body: dict = None) -> dict:
    ts = str(int(time.time() * 1000))
    recv_window = "5000"
    
    headers = {
        **DEFAULT_HEADERS,
        "X-BAPI-API-KEY": config["BYBIT_API_KEY"],
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-RECV-WINDOW": recv_window,
    }

    url = f"{config['BYBIT_BASE_URL']}{endpoint}"
    body_str = ""

    if method == "GET":
        params = params or {}
        sig = _sign(params, config["BYBIT_API_SECRET"], ts, recv_window)
        headers["X-BAPI-SIGN"] = sig
    else:
        body_str = json.dumps(body or {})
        param_str = ts + config["BYBIT_API_KEY"] + recv_window + body_str
        sig = hmac.new(config["BYBIT_API_SECRET"].encode(), param_str.encode(), hashlib.sha256).hexdigest()
        headers["X-BAPI-SIGN"] = sig
        headers["Content-Type"] = "application/json"

    max_retries = len(proxy_manager.proxies) if proxy_manager.proxies else 1
    
    for _ in range(max_retries):
        proxies = proxy_manager.get_next_proxy()
        try:
            if method == "GET":
                resp = requests.get(url, params=params, headers=headers, timeout=5, proxies=proxies)
            else:
                resp = requests.post(url, data=body_str, headers=headers, timeout=5, proxies=proxies)
            
            if resp.status_code == 200:
                if proxies:
                    current_proxy = proxy_manager.proxies[(proxy_manager.current_index - 1) % len(proxy_manager.proxies)]
                    proxy_manager.mark_working(current_proxy)
                return resp.json()
            
            log.warning(f"⚠️ Erro HTTP {resp.status_code} com proxy. Tentando próximo...")
        except Exception as e:
            log.warning(f"⚠️ Erro de conexão com proxy: {e}. Tentando próximo...")
    
    raise Exception("Esgotadas as tentativas de proxy para esta requisição.")

def bybit_get(endpoint: str, params: dict = None) -> dict:
    return bybit_request("GET", endpoint, params=params)

def bybit_post(endpoint: str, body: dict) -> dict:
    return bybit_request("POST", endpoint, body=body)

# ── Dados de mercado ──────────────────────────

def get_ticker(symbol: str) -> dict:
    data = bybit_get("/v5/market/tickers", {"category": "spot", "symbol": symbol})
    if not data.get("result") or not data["result"].get("list"):
        raise ValueError(f"Símbolo {symbol} não encontrado ou sem dados de ticker.")
    return data["result"]["list"][0]

def get_klines(symbol: str, interval: str = "1", limit: int = 200, start_time: int = None) -> list:
    params = {
        "category": "spot", 
        "symbol": symbol,
        "interval": interval, 
        "limit": str(limit)
    }
    if start_time:
        params["start"] = str(start_time + 1) # Começa 1ms depois do último

    data = bybit_get("/v5/market/kline", params)
    if not data.get("result") or not data["result"].get("list"):
         return []
    return data["result"]["list"]

def get_orderbook(symbol: str, limit: int = 10) -> dict:
    data = bybit_get("/v5/market/orderbook", {
        "category": "spot", "symbol": symbol, "limit": str(limit)
    })
    return data["result"]

def get_wallet_balance() -> dict:
    # 1. Tentar ler saldo da conta de Trading (Unified)
    data = bybit_get("/v5/account/wallet-balance", {"accountType": "UNIFIED"})
    unified_bal = 0.0
    
    if not data.get("result") or not data["result"].get("list"):
         log.warning("⚠️ Erro ao ler saldo Unified ou resposta vazia.")
    else:
        coins = data["result"]["list"][0]["coin"]
        usdt_asset = next((c for c in coins if c["coin"] == "USDT"), None)
        if usdt_asset:
            unified_bal = float(usdt_asset["walletBalance"])
        
    log.info(f"💰 Saldo Unified: {unified_bal} USDT")

    # 2. Se saldo for baixo, verificar Funding e tentar transferir
    if unified_bal < config["TRADE_AMOUNT"]:
        log.info("Checking Funding Balance...")
        try:
            funding_bal = get_funding_balance()
            log.info(f"💰 Saldo Funding: {funding_bal} USDT")
            if funding_bal > 1.0: # Mínimo para transferir
                log.info(f"💰 Saldo encontrado no Funding ({funding_bal} USDT). Transferindo para Trading...")
                transfer_from_fund_to_unified(funding_bal)
                # Recarregar saldo Unified após transferência
                time.sleep(2)
                return get_wallet_balance() 
        except Exception as e:
            log.error(f"Erro ao verificar/transferir Funding: {e}")

    return {"USDT": unified_bal}

def get_funding_balance() -> float:
    """Checa saldo USDT na conta de Funding"""
    data = bybit_get("/v5/asset/transfer/query-account-coins-balance", {
        "accountType": "FUND",
        "coin": "USDT"
    })
    if data["retCode"] == 0 and data["result"]["balance"]:
        return float(data["result"]["balance"][0]["walletBalance"])
    return 0.0

def transfer_from_fund_to_unified(amount: float):
    """Transfere fundos do Funding para Unified"""
    # Deixar um pouco no funding se quiser, ou transferir tudo. Aqui transfere tudo.
    # amount precisa ser string
    body = {
        "transferId": str(uuid.uuid4()),
        "coin": "USDT",
        "amount": str(amount),
        "fromAccountType": "FUND",
        "toAccountType": "UNIFIED"
    }
    resp = bybit_post("/v5/asset/transfer/inter-transfer", body)
    if resp["retCode"] == 0:
        log.info(f"✅ Transferência de {amount} USDT realizada com sucesso!")
    else:
        log.error(f"❌ Falha na transferência: {resp}")

def place_market_order(symbol: str, side: str, qty: str) -> dict:
    return bybit_post("/v5/order/create", {
        "category": "spot",
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "qty": qty,
    })

# ══════════════════════════════════════════════
# ANÁLISE TÉCNICA
# ══════════════════════════════════════════════

def calc_sma(closes: list[float], period: int) -> float:
    if len(closes) < period:
        return 0.0
    return sum(closes[-period:]) / period

def calc_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]
    avg_gain = sum(gains[-period:]) / period if gains else 0
    avg_loss = sum(losses[-period:]) / period if losses else 0
    
    if avg_gain == 0 and avg_loss == 0:
        return 50.0 # Estagnado
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def build_market_summary(symbol: str) -> dict:
    # 1. Ticker e Orderbook (Tempo real)
    ticker = get_ticker(symbol)
    ob = get_orderbook(symbol, limit=5)
    price = float(ticker["lastPrice"])

    # 2. Sincronização Incremental de Candles (Intervalo de 1 minuto)
    last_ts = db.get_latest_kline_timestamp(symbol)
    
    # Se não tem nada, pegar os últimos 200
    new_klines = get_klines(symbol, interval="1", limit=200, start_time=last_ts)
    if new_klines:
        db.save_klines(symbol, new_klines)
    
    # 3. Buscar histórico do banco (definido no .env)
    history = db.get_history(symbol, config["HISTORY_MINUTES"])
    if not history:
        raise ValueError(f"Histórico insuficiente para {symbol}")

    # 4. Cálculos Técnicos baseados no histórico do banco
    closes = [row[4] for row in history]
    volumes = [row[5] for row in history]

    sma9 = calc_sma(closes, 9)
    sma21 = calc_sma(closes, 21)
    rsi = calc_rsi(closes)
    change = float(ticker.get("price24hPcnt", 0)) * 100

    best_bid = float(ob["b"][0][0]) if ob["b"] else 0
    best_ask = float(ob["a"][0][0]) if ob["a"] else 0
    spread = ((best_ask - best_bid) / best_bid * 100) if best_bid else 0

    # 5. Formatar histórico simplificado para a IA
    # Envia apenas timestamp (formatado), close e volume para economizar tokens
    formatted_history = [
        {
            "time": datetime.fromtimestamp(row[0]/1000).strftime('%H:%M'),
            "c": row[4],
            "v": row[5]
        } 
        for row in history[-60:] # Envia os últimos 60 pontos para não estourar contexto, ou conforme config
    ]

    return {
        "symbol": symbol,
        "price": price,
        "rsi_14": round(rsi, 2),
        "trend": "alta" if sma9 > sma21 else "baixa",
        "spread_pct": round(spread, 4),
        "history_points": len(history),
        "history_window_minutes": config["HISTORY_MINUTES"],
        "recent_candles": formatted_history,
        "change_24h_pct": round(change, 2),
        "volume_24h": float(ticker.get("volume24h", 0)),
    }

# ══════════════════════════════════════════════
# DECISÃO via GEMINI
# ══════════════════════════════════════════════

def get_ai_params(risk_level: int):
    """Calcula parâmetros dinâmicos baseados no risco (1-100)"""
    # 1 (conservador) -> min_conf=0.9, rsi_buy < 30
    # 100 (agressivo) -> min_conf=0.4, rsi_buy < 60
    
    min_confidence = 0.9 - (risk_level * 0.005)  # 0.9 -> 0.4
    min_confidence = max(0.4, min(0.9, min_confidence))

    buy_rsi_limit = 30 + (risk_level * 0.3)      # 30 -> 60
    
    return min_confidence, buy_rsi_limit

def ask_gemini(market: dict, wallet: dict, open_position: bool, risk_level: int) -> dict:
    min_conf, buy_rsi = get_ai_params(risk_level)
    
    # Log para confirmar envio de dados
    num_candles = len(market.get("recent_candles", []))
    log.info(f"🧠 Enviando dados para Gemini ({market['symbol']}): Price={market['price']}, RSI={market['rsi_14']}, Candles={num_candles}")
    
    system_prompt = f"""Você é um trader quantitativo de memecoins.
Nível de Risco atual: {risk_level}/100.
Parametros: Confiança Mínima > {min_conf:.2f}, RSI Compra < {buy_rsi:.0f}.

Regras:
- Risco BAIXO (1-30): Seja MUITO seletivo. Só RSI extremo.
- Risco ALTO (70-100): Aceite setups mais arriscados, momentum trades.
- Responda SOMENTE JSON: {{"action": "BUY/SELL/HOLD", "confidence": 0.0-1.0, "reason": "txt", "risk": "L/M/H"}}
"""
    
    user_msg = f"""
{system_prompt}
Dados ({market['symbol']}):
{json.dumps(market, indent=2)}
Carteira USDT: {wallet.get('USDT', 0):.2f}
Posição Aberta: {'Sim' if open_position else 'Não'}
"""
    try:
        response = model.generate_content(user_msg)
        raw = response.text.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines[0].startswith("```"): raw = "\n".join(lines[1:-1])
        return json.loads(raw)
    except Exception as e:
        log.error(f"Gemini error: {e}")
        return {"action": "HOLD", "confidence": 0, "reason": "Error", "risk": "HIGH"}

# ══════════════════════════════════════════════
# GESTÃO DE POSIÇÃO
# ══════════════════════════════════════════════

class Position:
    def __init__(self, symbol: str, entry_price: float, qty: float, sl_pct: float, tp_pct: float):
        self.symbol       = symbol
        self.entry_price  = entry_price
        self.qty          = qty
        self.sl_pct       = sl_pct
        self.tp_pct       = tp_pct
        self.stop_loss    = entry_price * (1 - sl_pct)
        self.take_profit  = entry_price * (1 + tp_pct)
        self.opened_at    = datetime.now()

    def update_targets(self, sl_pct: float, tp_pct: float):
        """Atualiza SL/TP dinamicamente se o config mudar"""
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.stop_loss    = self.entry_price * (1 - sl_pct)
        self.take_profit  = self.entry_price * (1 + tp_pct)

    def should_close(self, current_price: float) -> tuple[bool, str]:
        if current_price <= self.stop_loss:
            return True, "STOP_LOSS"
        if current_price >= self.take_profit:
            return True, "TAKE_PROFIT"
        return False, ""

    def pnl_pct(self, current_price: float) -> float:
        return (current_price - self.entry_price) / self.entry_price * 100

    def pnl_usd(self, current_price: float) -> float:
        return (current_price - self.entry_price) * self.qty

def save_dashboard_data(wallet: dict, positions: dict):
    """Salva dados em tempo real para o dashboard PHP"""
    try:
        pos_list = []
        for p in positions.values():
            opened_str = p.opened_at.isoformat() if hasattr(p.opened_at, 'isoformat') else str(p.opened_at)
            
            # Garantir que last_price_time seja string
            lp_time = p.last_price_time if hasattr(p, 'last_price_time') else datetime.now().isoformat()
            if not isinstance(lp_time, str):
                lp_time = lp_time.isoformat()

            pos_list.append({
                "symbol": p.symbol,
                "entry_price": float(p.entry_price),
                "qty": float(p.qty),
                "stop_loss": float(p.stop_loss),
                "take_profit": float(p.take_profit),
                "opened_at": opened_str,
                "last_market_price": float(getattr(p, 'last_market_price', p.entry_price)),
                "last_price_time": lp_time
            })

        data = {
            "last_update": datetime.now().isoformat(),
            "wallet": wallet,
            "positions": pos_list
        }
        
        # Serializar primeiro para evitar arquivos corrompidos
        json_str = json.dumps(data, indent=2)
        
        with open("dashboard_data.json", "w") as f:
            f.write(json_str)
        
        try:
            os.chmod("dashboard_data.json", 0o666)
        except:
            pass
            
    except Exception as e:
        log.error(f"❌ Erro crítico ao salvar dashboard_data: {e}")
        import traceback
        log.error(traceback.format_exc())

# ══════════════════════════════════════════════
# LOOP PRINCIPAL
# ══════════════════════════════════════════════

def run():
    global config
    positions: dict[str, Position] = {} 
    
    # Recuperar posições abertas do banco de dados na inicialização
    saved_positions = db.get_open_positions()
    for sym, data in saved_positions.items():
        positions[sym] = Position(sym, data["price"], data["qty"], config["STOP_LOSS"], config["TAKE_PROFIT"])
        # Ajustar data de abertura se disponível
        try:
            positions[sym].opened_at = datetime.strptime(data["timestamp"], '%Y-%m-%d %H:%M:%S')
        except:
            pass
    
    last_analysis: dict[str, float] = {} # Armazena o timestamp da última análise de cada símbolo

    log.info("🚀 Bot Iniciado! Recuperadas %d posições. Frequências: Carteira=%dm, Oportunidades=%dm", 
             len(positions), config["FREQ_CARTEIRA"]//60, config["FREQ_OPORTUNIDADES"]//60)

    while True:
        try:
            # 1. Recarregar Config
            config = load_config()
            risk_level = config["RISK_LEVEL"]
            now = time.time()
            
            # Atualizar SL/TP das posições existentes
            for sym, pos in positions.items():
                pos.update_targets(config["STOP_LOSS"], config["TAKE_PROFIT"])

            wallet = get_wallet_balance()
            save_dashboard_data(wallet, positions)
            
            # 2. Definir lista total de símbolos
            all_symbols = list(set(config["SYMBOLS"] + list(positions.keys())))

            for symbol in all_symbols:
                if not symbol: continue
                
                # Pular se já sabemos que é inválido (apenas se não tivermos posição aberta)
                if coin_manager.is_invalid(symbol) and symbol not in positions:
                    continue

                # Determinar intervalo necessário para este símbolo
                is_in_wallet = symbol in positions
                interval = config["FREQ_CARTEIRA"] if is_in_wallet else config["FREQ_OPORTUNIDADES"]
                
                # Verificar se já passou o tempo necessário desde a última análise
                time_since_last = now - last_analysis.get(symbol, 0)
                
                if time_since_last < interval:
                    continue # Ainda não está na hora de analisar este ativo

                try:
                    log.info(f"🔍 Analisando {symbol} ({'CARTEIRA' if is_in_wallet else 'OPORTUNIDADE'})...")
                    market = build_market_summary(symbol)
                    coin_manager.mark_valid(symbol)
                    price = market["price"]
                    
                    # Atualizar timestamp da última análise
                    last_analysis[symbol] = now
                    
                    # A. Verificar Posição Existente
                    if is_in_wallet:
                        pos = positions[symbol]
                        # Atualizar dados de mercado em tempo real na posição para o Dashboard
                        pos.last_market_price = price
                        pos.last_price_time = datetime.now().isoformat()
                        
                        close, reason = pos.should_close(price)
                        pnl = pos.pnl_pct(price)
                        log.info(f"   📉 POSIÇÃO {symbol}: PnL {pnl:.2f}%")
                        
                        if close:
                            log.info(f"   🔴 FECHANDO {symbol} ({reason})")
                            res = place_market_order(symbol, "Sell", f"{pos.qty:.4f}")
                            log.info(f"   📦 Resposta SELL {symbol}: {res}")
                            if res.get("retCode") == 0:
                                db.log_trade(symbol, "SELL", pos.qty, price, pos.pnl_usd(price), reason)
                                del positions[symbol]
                                save_dashboard_data(wallet, positions) # Atualiza Dashboard
                            else:
                                log.error(f"   ❌ Erro ao fechar {symbol}: {res.get('retMsg')}")
                        else:
                            decision = ask_gemini(market, wallet, True, risk_level)
                            action = decision["action"]
                            res_msg = ""
                            
                            if action == "SELL" and decision["confidence"] > 0.7:
                                log.info(f"   🧠 IA sugere saída antecipada de {symbol}: {decision['reason']}")
                                res = place_market_order(symbol, "Sell", f"{pos.qty:.4f}")
                                log.info(f"   📦 Resposta SELL (AI) {symbol}: {res}")
                                res_msg = res.get("retMsg", "Unknown Error")
                                if res.get("retCode") == 0:
                                    db.log_trade(symbol, "SELL", pos.qty, price, pos.pnl_usd(price), "AI_EXIT")
                                    del positions[symbol]
                                    save_dashboard_data(wallet, positions)
                                    res_msg = "SUCCESS"
                                else:
                                    log.error(f"   ❌ Erro na saída AI {symbol}: {res_msg}")
                            
                            db.log_analysis(symbol, action, decision["confidence"], decision["risk"], decision["reason"], price, res_msg)
                        continue

                    # B. Verificar Novas Entradas
                    if symbol not in config["SYMBOLS"]:
                        continue

                    if len(positions) >= config["MAX_TRADES"]:
                        continue

                    decision = ask_gemini(market, wallet, False, risk_level)
                    action = decision["action"]
                    res_msg = ""
                    
                    min_conf, _ = get_ai_params(risk_level)
                    log.info(f"   🧠 IA: {action} ({decision.get('confidence')})")

                    if action == "BUY" and decision["confidence"] >= min_conf:
                        if wallet.get("USDT", 0) < config["TRADE_AMOUNT"]:
                            log.warning("   ⚠️ Saldo USDT insuficiente.")
                            res_msg = "Saldo Insuficiente"
                        else:
                            # Para compra a mercado no SPOT V5, o 'qty' é o valor em USDT
                            amount_usdt = config["TRADE_AMOUNT"]
                            log.info(f"   🟢 COMPRANDO {symbol} (Gasto: {amount_usdt} USDT)")
                            res = place_market_order(symbol, "Buy", str(amount_usdt))
                            log.info(f"   📦 Resposta BUY {symbol}: {res}")
                            res_msg = res.get("retMsg", "Unknown Error")
                            
                            if res.get("retCode") == 0:
                                # Precisamos do preço real de execução ou estimamos
                                # O 'qty' no DB deve ser a quantidade de moedas compradas
                                coin_qty = amount_usdt / price 
                                db.log_trade(symbol, "BUY", coin_qty, price, 0, decision["reason"])
                                positions[symbol] = Position(
                                    symbol, price, coin_qty, config["STOP_LOSS"], config["TAKE_PROFIT"]
                                )
                                save_dashboard_data(wallet, positions)
                                res_msg = "SUCCESS"
                            else:
                                log.error(f"   ❌ Erro na compra {symbol}: {res_msg}")
                    
                    db.log_analysis(symbol, action, decision["confidence"], decision["risk"], decision["reason"], price, res_msg)

                except ValueError as ve:
                    if "Símbolo" in str(ve) and "não encontrado" in str(ve):
                        coin_manager.mark_invalid(symbol)
                    else:
                        log.error(f"Erro em {symbol}: {ve}")
                except Exception as e:
                    log.error(f"Erro em {symbol}: {e}")
            
            # Dorme por um tempo curto para não fritar a CPU e permitir verificações granulares
            time.sleep(10)
        
        except Exception as e:
            log.exception(f"Erro no loop principal: {e}")
            time.sleep(30)

if __name__ == "__main__":
    run()
