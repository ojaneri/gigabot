#!/bin/bash

# Configurações
BOT_SCRIPT="bot.py"
LOG_FILE="bot.log"
DB_FILE="trades.db"
PID_FILE="bot.pid"

# Cores para o terminal
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

start() {
    if [ -f $PID_FILE ] && kill -0 $(cat $PID_FILE) 2>/dev/null; then
        echo -e "${YELLOW}⚠️  O bot já está rodando (PID: $(cat $PID_FILE)).${NC}"
    else
        echo -e "${BLUE}🚀 Iniciando o bot...${NC}"
        nohup python3 $BOT_SCRIPT > $LOG_FILE 2>&1 &
        echo $! > $PID_FILE
        echo -e "${GREEN}✅ Bot iniciado com sucesso! (PID: $(cat $PID_FILE))${NC}"
    fi
}

stop() {
    if [ -f $PID_FILE ]; then
        PID=$(cat $PID_FILE)
        echo -e "${BLUE}🛑 Parando o bot (PID: $PID)...${NC}"
        kill $PID
        rm $PID_FILE
        echo -e "${GREEN}✅ Bot parado.${NC}"
    else
        # Fallback para pkill caso o arquivo pid suma
        pkill -f "python3 $BOT_SCRIPT"
        echo -e "${YELLOW}⚠️  Arquivo PID não encontrado, tentado pkill.${NC}"
    fi
}

status() {
    if [ -f $PID_FILE ] && kill -0 $(cat $PID_FILE) 2>/dev/null; then
        echo -e "${GREEN}🟢 Status: RODANDO (PID: $(cat $PID_FILE))${NC}"
        echo -e "${BLUE}Últimas 5 linhas do log:${NC}"
        tail -n 5 $LOG_FILE
    else
        echo -e "${RED}🔴 Status: PARADO${NC}"
    fi
}

models() {
    echo -e "${YELLOW}🔍 Listando modelos Gemini disponíveis:${NC}"
    python3 -c "import google.generativeai as genai; import os; from dotenv import load_dotenv; load_dotenv(); genai.configure(api_key=os.getenv('GEMINI_API_KEY')); print('\n'.join([m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]))"
}

report() {
    if [ ! -f $DB_FILE ]; then
        echo -e "${RED}❌ Erro: Banco de dados $DB_FILE não encontrado.${NC}"
        return
    fi

    echo -e "${YELLOW}📊 RELATÓRIO DE PERFORMANCE (SQLite)${NC}"
    echo "--------------------------------------------------"
    
    # Total de Trades
    TOTAL=$(sqlite3 $DB_FILE "SELECT COUNT(*) FROM trades;")
    BUYS=$(sqlite3 $DB_FILE "SELECT COUNT(*) FROM trades WHERE side='BUY';")
    SELLS=$(sqlite3 $DB_FILE "SELECT COUNT(*) FROM trades WHERE side='SELL';")
    
    # PnL Total
    PNL=$(sqlite3 $DB_FILE "SELECT SUM(pnl) FROM trades WHERE side='SELL';")
    if [ -z "$PNL" ]; then PNL="0.00"; fi

    echo -e "Total de Operações: ${BLUE}$TOTAL${NC} (Compras: $BUYS | Vendas: $SELLS)"
    
    if (( $(echo "$PNL >= 0" | bc -l) )); then
        echo -e "Lucro/Prejuízo Total: ${GREEN}\$${PNL}${NC}"
    else
        echo -e "Lucro/Prejuízo Total: ${RED}\$${PNL}${NC}"
    fi

    echo "--------------------------------------------------"
    echo -e "${BLUE}Últimos 5 trades:${NC}"
    sqlite3 -header -column $DB_FILE "SELECT timestamp, symbol, side, qty, price, pnl FROM trades ORDER BY id DESC LIMIT 5;"
}

case "$1" in
    --start)
        start
        ;;
    --stop)
        stop
        ;;
    --status)
        status
        ;;
    --restart)
        stop
        sleep 2
        start
        ;;
    --report)
        report
        ;;
    --models)
        models
        ;;
    *)
        echo "Uso: $0 {--start|--stop|--status|--restart|--report|--models}"
        exit 1
esac
