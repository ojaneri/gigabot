<?php
// Configuração
date_default_timezone_set('America/Sao_Paulo');
$dbPath = __DIR__ . '/trades.db';
$jsonPath = __DIR__ . '/dashboard_data.json';
$envPath = __DIR__ . '/.env';
$db = new SQLite3($dbPath);

// Handle Save Config
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['action']) && $_POST['action'] === 'save_config') {
    $newConfig = "";
    $lines = file($envPath);
    $keysToUpdate = [
        'MEMECOIN_SYMBOLS' => $_POST['MEMECOIN_SYMBOLS'],
        'TRADE_AMOUNT_USD' => $_POST['TRADE_AMOUNT_USD'],
        'RISK_LEVEL' => $_POST['RISK_LEVEL'],
        'MAX_OPEN_TRADES' => $_POST['MAX_OPEN_TRADES'],
        'STOP_LOSS_PCT' => $_POST['STOP_LOSS_PCT'],
        'TAKE_PROFIT_PCT' => $_POST['TAKE_PROFIT_PCT'],
        'FREQ_CARTEIRA_MINUTOS' => $_POST['FREQ_CARTEIRA_MINUTOS'],
        'FREQ_OPORTUNIDADES_MINUTOS' => $_POST['FREQ_OPORTUNIDADES_MINUTOS'],
        'HISTORY_MINUTES' => $_POST['HISTORY_MINUTES'],
    ];
    foreach ($lines as $line) {
        $trimmed = trim($line);
        if (empty($trimmed) || strpos($trimmed, '#') === 0) { $newConfig .= $line; continue; }
        $parts = explode('=', $trimmed, 2);
        $key = $parts[0];
        if (array_key_exists($key, $keysToUpdate)) {
            $newConfig .= $key . "=" . $keysToUpdate[$key] . "\n";
            unset($keysToUpdate[$key]);
        } else { $newConfig .= $line; }
    }
    foreach ($keysToUpdate as $key => $val) { $newConfig .= $key . "=" . $val . "\n"; }
    file_put_contents($envPath, $newConfig);
    header("Location: index.php"); exit;
}

// Read Config for Modal
$envContent = file_get_contents($envPath);
$env = [];
foreach (explode("\n", $envContent) as $line) {
    $line = trim($line);
    if ($line && $line[0] !== '#') {
        list($key, $val) = explode('=', $line, 2) + [NULL, NULL];
        if ($key) $env[$key] = $val;
    }
}

// Read Real-time Data
$dashboardData = ['wallet' => ['USDT' => 0], 'positions' => [], 'last_update' => 'N/A'];
if (file_exists($jsonPath)) {
    $dashboardData = json_decode(file_get_contents($jsonPath), true);
}
$usdtBalance = isset($dashboardData['wallet']['USDT']) ? $dashboardData['wallet']['USDT'] : 0;

// Stats from DB
$totalPnl = $db->querySingle("SELECT SUM(pnl) FROM trades WHERE side='SELL'") ?: 0;
$totalTrades = $db->querySingle("SELECT COUNT(*) FROM trades WHERE side='SELL'");
$wins = $db->querySingle("SELECT COUNT(*) FROM trades WHERE side='SELL' AND pnl > 0");
$winRate = $totalTrades > 0 ? ($wins / $totalTrades) * 100 : 0;

// Transactions (SELL ONLY = Finalizadas)
$finalizedTrades = [];
$res = $db->query("SELECT * FROM trades WHERE side='SELL' ORDER BY id DESC LIMIT 10");
while ($row = $res->fetchArray(SQLITE3_ASSOC)) $finalizedTrades[] = $row;

// Analyses History (Todas as decisões da IA)
$analyses = [];
$resAnalyses = $db->query("SELECT * FROM analyses ORDER BY id DESC LIMIT 15");
while ($row = $resAnalyses->fetchArray(SQLITE3_ASSOC)) $analyses[] = $row;

// Chart Data
$chartData = [];
$runningTotal = 0;
$chartRes = $db->query("SELECT strftime('%Y-%m-%d %H:00', timestamp) as time_slot, SUM(pnl) as session_pnl FROM trades WHERE side='SELL' GROUP BY time_slot ORDER BY time_slot ASC");
while ($row = $chartRes->fetchArray(SQLITE3_ASSOC)) {
    $runningTotal += $row['session_pnl'];
    $chartData[] = ['x' => $row['time_slot'], 'y' => $runningTotal];
}

function formatUSD($val) { return '$' . number_format($val, 2, '.', ','); }
?>
<!DOCTYPE html>
<html lang="pt-BR" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="30">
    <title>GigaBot Dashboard v2.2</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        tailwind.config = { darkMode: 'class', theme: { extend: { colors: { gray: { 900: '#0f172a', 800: '#1e293b', 700: '#334155' } } } } }
    </script>
    <style>
        .glass { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.05); }
        .modal { transition: opacity 0.25s ease; }
        body.modal-active { overflow-x: hidden; overflow-y: visible !important; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: #0f172a; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 10px; }
    </style>
</head>
<body class="bg-gray-900 text-slate-200 font-sans antialiased min-h-screen">

    <!-- Navbar -->
    <nav class="border-b border-gray-700 bg-gray-900/50 backdrop-blur-md sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex items-center justify-between h-16">
                <div class="flex items-center gap-3">
                    <div class="bg-indigo-600 p-2 rounded-lg">
                        <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                    </div>
                    <span class="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-cyan-400">
                        GigaBot <span class="text-xs text-gray-400 font-mono border border-gray-700 rounded px-1 ml-1">v2.2</span>
                    </span>
                </div>
                <div class="flex items-center gap-4">
                    <span class="text-sm font-mono text-emerald-400 bg-emerald-900/30 px-3 py-1 rounded border border-emerald-500/30">
                        Saldo: <?php echo formatUSD($usdtBalance); ?>
                    </span>
                    <button onclick="toggleModal('configModal')" class="bg-gray-700 hover:bg-gray-600 text-white px-3 py-1.5 rounded-md text-sm font-medium transition flex items-center gap-2">
                        Config
                    </button>
                </div>
            </div>
        </div>
    </nav>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        
        <!-- Stats Row -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div class="glass rounded-2xl p-6 border-l-4 border-indigo-500">
                <p class="text-sm font-medium text-gray-400">Lucro Realizado</p>
                <p class="mt-2 text-3xl font-bold <?php echo $totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'; ?>"><?php echo formatUSD($totalPnl); ?></p>
            </div>
            <div class="glass rounded-2xl p-6 border-l-4 border-cyan-500">
                <p class="text-sm font-medium text-gray-400">Win Rate</p>
                <p class="mt-2 text-3xl font-bold text-white"><?php echo number_format($winRate, 1); ?>%</p>
            </div>
            <div class="glass rounded-2xl p-6 border-l-4 border-amber-500">
                <p class="text-sm font-medium text-gray-400">Posições Abertas</p>
                <p class="mt-2 text-3xl font-bold text-amber-400"><?php echo count($dashboardData['positions']); ?></p>
            </div>
            <div class="glass rounded-2xl p-6 border-l-4 border-purple-500">
                <p class="text-sm font-medium text-gray-400">Total Trades</p>
                <p class="mt-2 text-3xl font-bold text-white"><?php echo $totalTrades; ?></p>
            </div>
        </div>

        <!-- Active Configuration Status Bar -->
        <div class="flex flex-wrap gap-4 text-xs font-mono">
            <div class="glass px-4 py-2 rounded-full border border-gray-700/50 flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-indigo-500 animate-pulse"></span>
                <span class="text-gray-500 uppercase font-bold">Monitorando:</span>
                <span class="text-indigo-300"><?php echo count(explode(',', $env['MEMECOIN_SYMBOLS'] ?? '')); ?> ativos</span>
            </div>
            <div class="glass px-4 py-2 rounded-full border border-gray-700/50 flex items-center gap-2">
                <span class="text-gray-500 uppercase font-bold">Risk:</span>
                <span class="text-amber-400"><?php echo $env['RISK_LEVEL'] ?? '50'; ?>/100</span>
            </div>
            <div class="glass px-4 py-2 rounded-full border border-gray-700/50 flex items-center gap-2">
                <span class="text-gray-500 uppercase font-bold">Freq Carteira:</span>
                <span class="text-cyan-400"><?php echo $env['FREQ_CARTEIRA_MINUTOS'] ?? '2'; ?>m</span>
            </div>
            <div class="glass px-4 py-2 rounded-full border border-gray-700/50 flex items-center gap-2">
                <span class="text-gray-500 uppercase font-bold">Freq Oportun:</span>
                <span class="text-cyan-400"><?php echo $env['FREQ_OPORTUNIDADES_MINUTOS'] ?? '10'; ?>m</span>
            </div>
            <div class="glass px-4 py-2 rounded-full border border-gray-700/50 flex items-center gap-2">
                <span class="text-gray-500 uppercase font-bold">Histórico:</span>
                <span class="text-purple-400"><?php echo $env['HISTORY_MINUTES'] ?? '120'; ?>m</span>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <!-- Chart (Evolution) -->
            <div class="glass rounded-2xl p-6 lg:col-span-2 shadow-xl">
                <h3 class="text-lg font-semibold text-white mb-6 flex items-center gap-2">
                    <svg class="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"></path></svg>
                    Performance Acumulada
                </h3>
                <div class="relative h-80 w-full"><canvas id="pnlChart"></canvas></div>
            </div>

            <!-- Active Positions (Detailed) -->
            <div class="glass rounded-2xl p-6 shadow-xl">
                <h3 class="text-lg font-semibold text-white mb-6 flex items-center gap-2">
                    <svg class="w-5 h-5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"></path></svg>
                    Carteira Atual
                </h3>
                <?php if (empty($dashboardData['positions'])): ?>
                    <p class="text-gray-500 text-center py-20 italic text-sm">Nenhum ativo em hold no momento.</p>
                <?php else: ?>
                    <div class="space-y-4">
                        <?php foreach ($dashboardData['positions'] as $pos): ?>
                        <div class="bg-gray-800/40 p-4 rounded-xl border border-gray-700/50 hover:border-indigo-500/30 transition">
                            <div class="flex justify-between mb-2">
                                <a href="https://www.tradingview.com/chart/?symbol=BYBIT:<?php echo $pos['symbol']; ?>" target="_blank" class="font-bold text-white text-lg hover:text-indigo-400 transition flex items-center gap-1">
                                    <?php echo $pos['symbol']; ?>
                                    <svg class="w-3 h-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path></svg>
                                </a>
                                <span class="text-xs text-gray-500 font-mono"><?php echo date('d/m H:i', strtotime($pos['opened_at'])); ?></span>
                            </div>
                            <div class="grid grid-cols-2 gap-2 text-sm">
                                <div><p class="text-gray-500 text-[10px] uppercase font-bold">Entrada</p><p class="text-indigo-300 font-mono"><?php echo number_format($pos['entry_price'], 6); ?></p></div>
                                <div class="text-right">
                                    <p class="text-gray-500 text-[10px] uppercase font-bold">Preço Atual</p>
                                    <p class="text-emerald-400 font-bold font-mono">
                                        <?php echo number_format($pos['last_market_price'] ?? $pos['entry_price'], 6); ?>
                                    </p>
                                </div>
                                <div class="mt-1">
                                    <p class="text-gray-500 text-[10px] uppercase font-bold">PnL Est.</p>
                                    <?php 
                                        $entry = $pos['entry_price'];
                                        $current = $pos['last_market_price'] ?? $entry;
                                        $pnl_p = (($current - $entry) / $entry) * 100;
                                    ?>
                                    <p class="font-mono text-xs <?php echo $pnl_p >= 0 ? 'text-emerald-500' : 'text-rose-500'; ?>">
                                        <?php echo ($pnl_p >= 0 ? '+' : '') . number_format($pnl_p, 2); ?>%
                                    </p>
                                </div>
                                <div class="mt-1 text-right">
                                    <p class="text-gray-500 text-[10px] uppercase font-bold">Último Check</p>
                                    <p class="text-gray-400 font-mono text-[10px]">
                                        <?php echo isset($pos['last_price_time']) ? date('H:i:s', strtotime($pos['last_price_time'])) : '-'; ?>
                                    </p>
                                </div>
                                <div class="mt-2"><p class="text-gray-500 text-[10px] uppercase font-bold">Stop Loss</p><p class="text-rose-400/80 font-mono text-xs"><?php echo number_format($pos['stop_loss'], 6); ?></p></div>
                                <div class="mt-2 text-right"><p class="text-gray-500 text-[10px] uppercase font-bold">Take Profit</p><p class="text-emerald-400/80 font-mono text-xs"><?php echo number_format($pos['take_profit'], 6); ?></p></div>
                            </div>
                            <div class="mt-3 pt-2 border-t border-gray-700/30 flex justify-between items-center">
                                <span class="text-gray-500 text-[10px] uppercase font-bold">Quantidade</span>
                                <div class="text-right">
                                    <span class="text-cyan-400 font-mono text-xs"><?php echo number_format($pos['qty'], 4); ?></span>
                                    <span class="text-gray-400 text-[10px] ml-1">
                                        (USD <?php echo number_format($pos['qty'] * ($pos['last_market_price'] ?? $pos['entry_price']), 2); ?>)
                                    </span>
                                </div>
                            </div>
                        </div>
                        <?php endforeach; ?>
                    </div>
                <?php endif; ?>
            </div>
        </div>

        <!-- Latest AI Analyses (New Block) -->
        <div class="glass rounded-2xl overflow-hidden shadow-xl">
            <div class="p-6 border-b border-gray-700 bg-gray-800/30">
                <h3 class="text-lg font-semibold text-white flex items-center gap-2">
                    <svg class="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"></path></svg>
                    Cérebro Gemini: Últimas Análises
                </h3>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-sm text-left">
                    <thead class="text-xs text-gray-500 uppercase bg-gray-900/50">
                        <tr>
                            <th class="px-6 py-3">Hora</th>
                            <th class="px-6 py-3">Moeda</th>
                            <th class="px-6 py-3">Decisão</th>
                            <th class="px-6 py-3 text-right">Preço</th>
                            <th class="px-6 py-3">Raciocínio da IA</th>
                            <th class="px-6 py-3">Execução</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-800">
                        <?php foreach ($analyses as $a): ?>
                        <tr class="hover:bg-gray-800/20 transition group">
                            <td class="px-6 py-4 font-mono text-[11px] text-gray-500"><?php echo date('H:i:s', strtotime($a['timestamp'])); ?></td>
                            <td class="px-6 py-4 font-bold text-gray-300">
                                <a href="https://www.tradingview.com/chart/?symbol=BYBIT:<?php echo $a['symbol']; ?>" target="_blank" class="hover:text-indigo-400 transition">
                                    <?php echo $a['symbol']; ?>
                                </a>
                            </td>
                            <td class="px-6 py-4">
                                <span class="px-2 py-0.5 rounded text-[10px] font-black uppercase <?php 
                                    echo $a['action'] === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' : ($a['action'] === 'SELL' ? 'bg-rose-500/20 text-rose-400' : 'bg-gray-700 text-gray-400'); 
                                ?>">
                                    <?php echo $a['action']; ?>
                                </span>
                            </td>
                            <td class="px-6 py-4">
                                <div class="w-12 bg-gray-700 rounded-full h-1.5 mt-1">
                                    <div class="bg-indigo-500 h-1.5 rounded-full" style="width: <?php echo ($a['confidence'] ?? 0)*100; ?>%"></div>
                                </div>
                            </td>
                            <td class="px-6 py-4 text-right font-mono text-xs text-gray-500"><?php echo number_format($a['price'], 6); ?></td>
                            <td class="px-6 py-4 text-xs text-gray-400 italic leading-relaxed group-hover:text-gray-300 max-w-xs truncate" title="<?php echo htmlspecialchars($a['reason']); ?>">
                                <?php echo htmlspecialchars($a['reason']); ?>
                            </td>
                            <td class="px-6 py-4">
                                <?php if ($a['result'] === 'SUCCESS'): ?>
                                    <span class="text-emerald-500 text-[10px] font-bold">✅ OK</span>
                                <?php elseif ($a['result']): ?>
                                    <span class="text-rose-500 text-[10px] font-medium italic" title="<?php echo htmlspecialchars($a['result']); ?>">
                                        ❌ <?php echo substr($a['result'], 0, 20); ?>...
                                    </span>
                                <?php else: ?>
                                    <span class="text-gray-600 text-[10px]">-</span>
                                <?php endif; ?>
                            </td>
                        </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Finalized Transactions -->
        <div class="glass rounded-2xl overflow-hidden shadow-xl">
             <div class="p-6 border-b border-gray-700 bg-gray-800/30 flex justify-between items-center">
                <h3 class="text-lg font-semibold text-white flex items-center gap-2">
                    <svg class="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    Histórico de Lucros (Trades Finalizados)
                </h3>
             </div>
             <div class="overflow-x-auto">
                <table class="w-full text-sm text-left">
                    <thead class="text-xs text-gray-500 uppercase bg-gray-900/50">
                        <tr>
                            <th class="px-6 py-3">Data/Hora</th>
                            <th class="px-6 py-3">Par</th>
                            <th class="px-6 py-3 text-right">Preço Venda</th>
                            <th class="px-6 py-3 text-right">Qtd</th>
                            <th class="px-6 py-3 text-right">Resultado (PnL)</th>
                            <th class="px-6 py-3">Motivo Fechamento</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-800">
                        <?php foreach ($finalizedTrades as $t): ?>
                        <tr class="hover:bg-emerald-500/5 transition">
                            <td class="px-6 py-4 font-mono text-xs text-gray-500"><?php echo date('d/m H:i', strtotime($t['timestamp'])); ?></td>
                            <td class="px-6 py-4 font-bold text-white">
                                <a href="https://www.tradingview.com/chart/?symbol=BYBIT:<?php echo $t['symbol']; ?>" target="_blank" class="hover:text-indigo-400 transition">
                                    <?php echo $t['symbol']; ?>
                                </a>
                            </td>
                            <td class="px-6 py-4 text-right font-mono text-gray-300"><?php echo number_format($t['price'], 6); ?></td>
                            <td class="px-6 py-4 text-right font-mono text-gray-400"><?php echo number_format($t['qty'], 2); ?></td>
                            <td class="px-6 py-4 text-right font-mono font-bold <?php echo $t['pnl'] > 0 ? 'text-emerald-400' : 'text-rose-400'; ?>">
                                <?php echo formatUSD($t['pnl']); ?>
                            </td>
                            <td class="px-6 py-4 text-xs text-gray-500 uppercase font-bold"><?php echo $t['reason']; ?></td>
                        </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </div>

    </main>

    <!-- Modal Configuration (Preserved) -->
    <div id="configModal" class="modal opacity-0 pointer-events-none fixed w-full h-full top-0 left-0 flex items-center justify-center z-50">
        <div class="modal-overlay absolute w-full h-full bg-black opacity-60"></div>
        <div class="modal-container bg-gray-800 w-11/12 md:max-w-md mx-auto rounded-xl shadow-2xl z-50 overflow-y-auto max-h-[90vh]">
            <div class="modal-content py-6 text-left px-8">
                <div class="flex justify-between items-center pb-6 border-b border-gray-700">
                    <p class="text-xl font-bold text-white">Configurações do Bot</p>
                    <div class="modal-close cursor-pointer" onclick="toggleModal('configModal')">
                        <svg class="fill-current text-white" width="18" height="18" viewBox="0 0 18 18"><path d="M14.53 4.53l-1.06-1.06L9 7.94 4.53 3.47 3.47 4.53 7.94 9l-4.47 4.47 1.06 1.06L9 10.06l4.47 4.47 1.06-1.06L10.06 9z"></path></svg>
                    </div>
                </div>
                <form action="index.php" method="POST" class="mt-6 space-y-4">
                    <input type="hidden" name="action" value="save_config">
                    <div><label class="block text-gray-400 text-[10px] uppercase font-bold mb-1">Moedas Monitoradas (CSV)</label><input name="MEMECOIN_SYMBOLS" type="text" value="<?php echo htmlspecialchars($env['MEMECOIN_SYMBOLS'] ?? ''); ?>" class="w-full bg-gray-900 text-white border border-gray-700 rounded-lg py-2 px-3 focus:border-indigo-500 outline-none transition"></div>
                    <div class="grid grid-cols-2 gap-4">
                        <div><label class="block text-gray-400 text-[10px] uppercase font-bold mb-1">Valor/Trade ($)</label><input name="TRADE_AMOUNT_USD" type="number" step="0.1" value="<?php echo $env['TRADE_AMOUNT_USD'] ?? ''; ?>" class="w-full bg-gray-900 text-white border border-gray-700 rounded-lg py-2 px-3 outline-none"></div>
                        <div><label class="block text-gray-400 text-[10px] uppercase font-bold mb-1">Risco (1-100)</label><input name="RISK_LEVEL" type="number" min="1" max="100" value="<?php echo $env['RISK_LEVEL'] ?? ''; ?>" class="w-full bg-gray-900 text-white border border-gray-700 rounded-lg py-2 px-3 outline-none"></div>
                    </div>
                    <div class="grid grid-cols-2 gap-4">
                        <div><label class="block text-gray-400 text-[10px] uppercase font-bold mb-1">Freq. Carteira (Min)</label><input name="FREQ_CARTEIRA_MINUTOS" type="number" value="<?php echo $env['FREQ_CARTEIRA_MINUTOS'] ?? ''; ?>" class="w-full bg-gray-900 text-white border border-gray-700 rounded-lg py-2 px-3 outline-none"></div>
                        <div><label class="block text-gray-400 text-[10px] uppercase font-bold mb-1">Freq. Oportun. (Min)</label><input name="FREQ_OPORTUNIDADES_MINUTOS" type="number" value="<?php echo $env['FREQ_OPORTUNIDADES_MINUTOS'] ?? ''; ?>" class="w-full bg-gray-900 text-white border border-gray-700 rounded-lg py-2 px-3 outline-none"></div>
                    </div>
                    <div class="grid grid-cols-2 gap-4">
                        <div><label class="block text-gray-400 text-[10px] uppercase font-bold mb-1">Max Operações</label><input name="MAX_OPEN_TRADES" type="number" value="<?php echo $env['MAX_OPEN_TRADES'] ?? ''; ?>" class="w-full bg-gray-900 text-white border border-gray-700 rounded-lg py-2 px-3 outline-none"></div>
                        <div><label class="block text-gray-400 text-[10px] uppercase font-bold mb-1">Histórico (Mins)</label><input name="HISTORY_MINUTES" type="number" value="<?php echo $env['HISTORY_MINUTES'] ?? '120'; ?>" class="w-full bg-gray-900 text-white border border-gray-700 rounded-lg py-2 px-3 outline-none"></div>
                    </div>
                    <div class="grid grid-cols-2 gap-4 border-t border-gray-700 pt-4">
                        <div><label class="block text-gray-400 text-[10px] uppercase font-bold mb-1">Stop Loss (%)</label><input name="STOP_LOSS_PCT" type="number" step="0.01" value="<?php echo $env['STOP_LOSS_PCT'] ?? ''; ?>" class="w-full bg-gray-900 text-white border border-gray-700 rounded-lg py-2 px-3 outline-none"></div>
                        <div><label class="block text-gray-400 text-[10px] uppercase font-bold mb-1">Take Profit (%)</label><input name="TAKE_PROFIT_PCT" type="number" step="0.01" value="<?php echo $env['TAKE_PROFIT_PCT'] ?? ''; ?>" class="w-full bg-gray-900 text-white border border-gray-700 rounded-lg py-2 px-3 outline-none"></div>
                    </div>
                    <div class="pt-4"><button type="submit" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 rounded-lg shadow-lg transition transform hover:-translate-y-0.5">Aplicar Novas Configurações</button></div>
                </form>
            </div>
        </div>
    </div>

    <script>
        function toggleModal(id){ document.getElementById(id).classList.toggle('opacity-0'); document.getElementById(id).classList.toggle('pointer-events-none'); document.body.classList.toggle('modal-active'); }
        
        const ctx = document.getElementById('pnlChart').getContext('2d');
        const chartData = <?php echo json_encode($chartData); ?>;
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: chartData.map(d => d.x),
                datasets: [{
                    label: 'PnL Acumulado',
                    data: chartData.map(d => d.y),
                    borderColor: '#818cf8', backgroundColor: 'rgba(129, 140, 248, 0.1)',
                    borderWidth: 3, tension: 0.4, fill: true, pointRadius: 2
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false }, ticks: { color: '#64748b', maxTicksLimit: 8 } },
                    y: { grid: { color: '#1e293b' }, ticks: { color: '#64748b', callback: v => '$'+v } }
                }
            }
        });
    </script>
</body>
</html>
