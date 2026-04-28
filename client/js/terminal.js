/**
 * BLACKOUT — Terminal de commandes (Galactic High-Tech)
 */

const Terminal = (() => {
    const STORAGE_KEY = 'blackout_terminal_height';
    const DEFAULT_HEIGHT = 380;
    const MIN_HEIGHT = 160;
    const MAX_HEIGHT = 800;

    let outputEl, inputEl, panelEl, resizeHandleEl;
    let history = [], historyIdx = -1;

    function clampHeight(height) { return Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, height)); }
    function applyPanelHeight(height) {
        if (!panelEl) return;
        const clamped = clampHeight(height);
        panelEl.style.height = `${clamped}px`;
        localStorage.setItem(STORAGE_KEY, String(clamped));
        window.dispatchEvent(new Event('resize'));
    }

    function setupResizeControls() {
        const saved = localStorage.getItem(STORAGE_KEY);
        setTimeout(() => applyPanelHeight(saved ? parseInt(saved) : DEFAULT_HEIGHT), 100);

        document.getElementById('terminal-shrink')?.addEventListener('click', () => applyPanelHeight(panelEl.offsetHeight - 60));
        document.getElementById('terminal-reset')?.addEventListener('click', () => applyPanelHeight(DEFAULT_HEIGHT));
        document.getElementById('terminal-grow')?.addEventListener('click', () => applyPanelHeight(panelEl.offsetHeight + 60));

        let dragging = false, startY = 0, startHeight = 0;
        resizeHandleEl?.addEventListener('mousedown', (e) => {
            e.preventDefault(); dragging = true; startY = e.clientY; startHeight = panelEl.offsetHeight;
            document.body.classList.add('terminal-resizing');
        });
        window.addEventListener('mousemove', (e) => {
            if (!dragging) return;
            const delta = startY - e.clientY;
            applyPanelHeight(startHeight + delta);
        });
        window.addEventListener('mouseup', () => { dragging = false; document.body.classList.remove('terminal-resizing'); });
    }

    function init() {
        outputEl = document.getElementById('terminal-output');
        inputEl = document.getElementById('terminal-input');
        panelEl = document.getElementById('terminal-panel');
        resizeHandleEl = document.getElementById('terminal-resize-handle');
        if (!outputEl || !inputEl || !panelEl) return;

        setupResizeControls();

        inputEl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { handleCommand(); }
            else if (e.key === 'Tab') { e.preventDefault(); handleAutocomplete(); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); handleHistory(-1); }
            else if (e.key === 'ArrowDown') { e.preventDefault(); handleHistory(1); }
        });

        panelEl.addEventListener('click', () => inputEl.focus());

        WS.on('command_result', (data) => {
            if (data.output) print(data.output, 'system');
            if (data.error) print(`Erreur: ${data.error}`, 'error');
        });

        printBanner();
        print('\x1b[2m--- UPLINK_ESTABLISHED // VECTOR: BLACKOUT ---\x1b[0m');
        print('Tapez "help" pour voir les protocoles système.');
    }

    function printBanner() {
        const banner = `
██████╗ ██╗      █████╗  ██████╗██╗  ██╗ ██████╗ ██╗   ██╗████████╗
██╔══██╗██║     ██╔══██╗██╔════╝██║ ██╔╝██╔═══██╗██║   ██║╚══██╔══╝
██████╔╝██║     ███████║██║     █████╔╝ ██║   ██║██║   ██║   ██║   
██╔══██╗██║     ██╔══██║██║     ██╔═██╗ ██║   ██║██║   ██║   ██║   
██████╔╝███████╗██║  ██║╚██████╗██║  ██╗╚██████╔╝╚██████╔╝   ██║   
╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝    ╚═╝`;
        
        if (!outputEl) return;
        const el = document.createElement('div');
        el.className = 'ascii-banner';
        el.style.whiteSpace = 'pre';
        el.innerHTML = `<span style="color:#00f2ff; font-weight:bold;">${banner}</span>`;
        outputEl.appendChild(el);
    }

    function handleCommand() {
        const line = inputEl.value.trim(); if (!line) return;
        history.push(line); historyIdx = -1;
        print(`root@blackout:~# ${line}`);
        inputEl.value = '';

        const parts = line.split(' '), cmd = parts[0].toLowerCase(), args = parts.slice(1);
        if (cmd === 'clear') outputEl.innerHTML = '';
        else if (cmd === 'modules' || cmd === 'shop') print(Upgrades.getAvailableModulesText(), 'system');
        else if (cmd === 'status') handleStatus();
        else if (cmd === 'install') {
            if (args.length === 0) print("Usage: install [id|nom]", "error");
            else handleInstall(args[0]);
        } else WS.send('command', { line });
    }

    function handleInstall(target) {
        let up = Upgrades.getUpgradeById(target);
        if (!up) up = Upgrades.matchUpgrade(target)[0];
        
        if (!up) { print(`[ERROR] Module '${target}' introuvable.`, "error"); return; }
        
        // Empêcher l'achat si déjà acquis
        const s = Game.getState();
        if (s?.purchased_upgrades.includes(up.id)) {
            print(`[INFO] Module '${up.name}' déjà injecté.`, "system");
            return;
        }

        // Calcul du coût avec bonus éventuels
        let finalCost = up.cost;
        // Si l'upgrade est de type gateway et qu'on a un discount (exemple théorique pour extensions futures)
        // ... (logique à adapter selon besoin spécifique)

        print(`[WAIT] Initialisation de l'injection du module '${up.name}'...`);
        let prog = 0;
        const iv = setInterval(() => {
            prog += 25; const bar = '█'.repeat(prog/10).padEnd(10, '░');
            print(`[PROG] Injection : [${bar}] ${prog}%`, 'system');
            if (prog >= 100) { 
                clearInterval(iv); 
                WS.send('buy_upgrade', { upgrade_id: parseInt(up.id) }); 
            }
        }, 200);
    }

    function handleStatus() {
        const s = Game.getState(); if (!s) return;
        let out = `\n\x1b[1;36m═══ SYSTEM_STATUS ═══\x1b[0m\n`;
        out += `Malware  : \x1b[1m${s.malware_class.toUpperCase()}\x1b[0m\n`;
        out += `CPU      : \x1b[1;33m${Math.floor(s.cpu_cycles)}\x1b[0m Cycles\n`;
        out += `Méfiance : \x1b[1;31m${Math.floor(s.suspicion)}%\x1b[0m\n`;
        out += `Réseau   : ${s.infected_count}/${s.total_nodes} compromis\n`;
        
        // Stats de secteurs
        const discovered = new Set(s.nodes.filter(n => n.infected).map(n => n.sector_id)).size;
        out += `Secteurs : ${discovered}/17 découverts\n`;
        if (s.porosity_mod > 0) out += `Porosité : +${(s.porosity_mod*100).toFixed(0)}% (SIGNAL_BOOST)\n`;
        
        print(out, 'system');
    }

    function handleAutocomplete() {
        const line = inputEl.value;
        const parts = line.split(' ');
        
        if (parts.length === 2 && parts[0].toLowerCase() === 'install') {
            const matches = Upgrades.matchUpgrade(parts[1]);
            if (matches.length === 1) {
                inputEl.value = `install ${matches[0].name.toLowerCase().replace(/ /g, '_')}`;
            } else if (matches.length > 1) {
                print("Suggestions: " + matches.map(m => `\x1b[1m${m.name}\x1b[0m`).join(', '), 'system');
            }
        } else if (parts.length === 1) {
            const cmds = ['help', 'status', 'modules', 'shop', 'install', 'clear', 'hack', 'nmap', 'ps', 'whoami'];
            const matches = cmds.filter(c => c.startsWith(parts[0].toLowerCase()));
            if (matches.length === 1) inputEl.value = matches[0] + ' ';
        }
    }

    function handleHistory(dir) {
        if (history.length === 0) return;
        if (historyIdx === -1) historyIdx = history.length;
        historyIdx = Math.max(0, Math.min(history.length, historyIdx + dir));
        inputEl.value = (historyIdx < history.length) ? history[historyIdx] : '';
    }

    function print(text, type = 'line') {
        if (!outputEl) return;
        const lines = String(text ?? '').split('\n');
        lines.forEach(lt => {
            const el = document.createElement('div'); el.className = `terminal-line terminal-${type}`;
            lt = lt.replace(/\x1b\[1;31m/g, '<span style="color:#ff0055; font-weight:bold;">');
            lt = lt.replace(/\x1b\[1;33m/g, '<span style="color:#ffcc00; font-weight:bold;">');
            lt = lt.replace(/\x1b\[1;34m/g, '<span style="color:#00f2ff; font-weight:bold;">');
            lt = lt.replace(/\x1b\[1;36m/g, '<span style="color:#00ff99; font-weight:bold;">');
            lt = lt.replace(/\x1b\[1m/g, '<span style="font-weight:bold;">');
            lt = lt.replace(/\x1b\[2m/g, '<span style="opacity:0.6;">');
            lt = lt.replace(/\x1b\[0m/g, '</span>');
            el.innerHTML = lt; outputEl.appendChild(el);
        });
        outputEl.scrollTop = outputEl.scrollHeight;
    }

    return { init, print };
})();
