/**
 * BLACKOUT — Terminal de commandes (Galactic High-Tech)
 */

const Terminal = (() => {
    const STORAGE_KEY = 'blackout_terminal_height';
    const DEFAULT_HEIGHT = 380;
    const MIN_HEIGHT = 160;
    const MAX_HEIGHT = 800;

    let outputEl, inputEl, panelEl, resizeHandleEl, suggestionsEl;
    let history = [], historyIdx = -1;
    let suggestions = [], selectedSuggestionIdx = -1;

    const COMMANDS = ['help', 'status', 'shop', 'install', 'upgrade', 'zones', 'clear', 'hack', 'nmap', 'phishing', 'modules'];

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
        suggestionsEl = document.getElementById('terminal-suggestions');
        resizeHandleEl = document.getElementById('terminal-resize-handle');
        if (!outputEl || !inputEl || !panelEl) return;

        if (suggestionsEl) {
            suggestionsEl.classList.add('terminal-suggestions');
        }

        setupResizeControls();

        inputEl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { 
                if (selectedSuggestionIdx >= 0 && suggestions.length > 0) {
                    e.preventDefault();
                    applySuggestion(suggestions[selectedSuggestionIdx]);
                } else {
                    handleCommand(); 
                }
            }
            else if (e.key === 'Tab') { 
                e.preventDefault(); 
                if (suggestions.length > 0) {
                    selectedSuggestionIdx = (selectedSuggestionIdx + 1) % suggestions.length;
                    renderSuggestions();
                } else {
                    handleAutocomplete(); 
                }
            }
            else if (e.key === 'ArrowUp') { 
                if (suggestions.length > 0) {
                    e.preventDefault();
                    selectedSuggestionIdx = (selectedSuggestionIdx - 1 + suggestions.length) % suggestions.length;
                    renderSuggestions();
                } else {
                    e.preventDefault(); handleHistory(-1); 
                }
            }
            else if (e.key === 'ArrowDown') { 
                if (suggestions.length > 0) {
                    e.preventDefault();
                    selectedSuggestionIdx = (selectedSuggestionIdx + 1) % suggestions.length;
                    renderSuggestions();
                } else {
                    e.preventDefault(); handleHistory(1); 
                }
            }
            else if (e.ctrlKey && e.key === 'l') {
                e.preventDefault();
                outputEl.innerHTML = '';
                print('\x1b[2m--- UPLINK_ESTABLISHED // VECTOR: BLACKOUT ---\x1b[0m');
            }
            else if (e.key === 'Escape') {
                clearSuggestions();
            }
        });

        inputEl.addEventListener('input', () => {
            updateSuggestions();
        });

        panelEl.addEventListener('click', () => inputEl.focus());

        WS.on('command_result', (data) => {
            let type = 'system';
            if (data.output) {
                if (data.output.includes('═══ MODULES D\'ÉVOLUTION')) type = 'shop';
                else if (data.output.includes('BLACKOUT TERMINAL')) type = 'help';
            }
            
            if (data.output) print(data.output, type);
            if (data.error) print(`Erreur: ${data.error}`, 'error');
        });

        WS.on('qte_event', (data) => {
            if (data.message) {
                print(`\x1b[1;33m${data.message}\x1b[0m`, 'system');
            }
            if (data.event === 'prompt' && data.remaining_ticks !== undefined) {
                print(`Tapez la commande dans les ${data.remaining_ticks} prochains ticks pour obtenir le bonus.`, 'system');
            }
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
        print(`root@blackout:~# ${line}`, 'highlight');
        inputEl.value = '';
        clearSuggestions();

        const parts = line.split(' '), cmd = parts[0].toLowerCase();
        if (cmd === 'clear') {
            outputEl.innerHTML = '';
        } else if (cmd === 'modules' || cmd === 'shop') {
            print(Upgrades.getAvailableModulesText(), 'shop');
        } else {
            WS.send('command', { line });
        }
    }

    function updateSuggestions() {
        const line = inputEl.value;
        if (!line) { clearSuggestions(); return; }
        
        const parts = line.split(' ');
        suggestions = [];

        if (parts.length === 1) {
            const cmdPart = parts[0].toLowerCase();
            suggestions = COMMANDS.filter(c => c.startsWith(cmdPart)).map(c => ({ text: c, value: c + ' ' }));
        } else if (parts.length === 2 && (parts[0].toLowerCase() === 'install' || parts[0].toLowerCase() === 'upgrade')) {
            const matches = Upgrades.matchUpgrade(parts[1]);
            suggestions = matches.map(m => ({ text: `${m.name} (${m.id})`, value: `${parts[0]} ${m.id}` }));
        }

        if (suggestions.length === 0) {
            clearSuggestions();
        } else {
            selectedSuggestionIdx = -1;
            renderSuggestions();
        }
    }

    function renderSuggestions() {
        if (!suggestionsEl) return;
        suggestionsEl.classList.remove('hidden');
        const lastPart = inputEl.value.split(' ').pop();
        
        suggestionsEl.innerHTML = suggestions.map((s, idx) => {
            let displayText = s.text;
            if (lastPart && s.text.toLowerCase().startsWith(lastPart.toLowerCase())) {
                displayText = `<b>${s.text.substring(0, lastPart.length)}</b>${s.text.substring(lastPart.length)}`;
            }
            return `<div class="suggestion-item ${idx === selectedSuggestionIdx ? 'active' : ''}" data-idx="${idx}">${displayText}</div>`;
        }).join('');

        suggestionsEl.querySelectorAll('.suggestion-item').forEach(el => {
            el.addEventListener('click', () => {
                applySuggestion(suggestions[parseInt(el.dataset.idx)]);
            });
        });
    }

    function clearSuggestions() {
        suggestions = [];
        selectedSuggestionIdx = -1;
        if (suggestionsEl) {
            suggestionsEl.classList.add('hidden');
            suggestionsEl.innerHTML = '';
        }
    }

    function applySuggestion(s) {
        inputEl.value = s.value;
        clearSuggestions();
        inputEl.focus();
    }

    function handleAutocomplete() {
        const line = inputEl.value;
        if (!line) {
            suggestions = COMMANDS.map(c => ({ text: c, value: c + ' ' }));
            renderSuggestions();
            return;
        }
        updateSuggestions();
        if (suggestions.length === 1) {
            applySuggestion(suggestions[0]);
        } else if (suggestions.length > 1) {
            selectedSuggestionIdx = 0;
            renderSuggestions();
        }
    }


    function handleHistory(dir) {
        if (history.length === 0) return;
        if (historyIdx === -1) historyIdx = history.length;
        historyIdx = Math.max(0, Math.min(history.length, historyIdx + dir));
        inputEl.value = (historyIdx < history.length) ? history[historyIdx] : '';
        clearSuggestions();
    }

    function print(text, type = 'line') {
        if (!outputEl) return;
        
        // Treat 'shop' and 'help' as single blocks to avoid stacking multiple divs
        if (type === 'shop' || type === 'help') {
            const el = document.createElement('div');
            el.className = `terminal-line terminal-${type}`;
            el.innerHTML = formatText(text);
            outputEl.appendChild(el);
        } else {
            const lines = String(text ?? '').split('\n');
            lines.forEach(lt => {
                const el = document.createElement('div');
                el.className = `terminal-line terminal-${type}`;
                el.innerHTML = formatText(lt);
                outputEl.appendChild(el);
            });
        }
        outputEl.scrollTop = outputEl.scrollHeight;
    }

    function formatText(text) {
        let lt = String(text ?? '');
        lt = lt.replace(/\x1b\[1;31m/g, '<span style="color:#ff0055; font-weight:bold;">');
        lt = lt.replace(/\x1b\[1;33m/g, '<span style="color:#ffcc00; font-weight:bold;">');
        lt = lt.replace(/\x1b\[1;34m/g, '<span style="color:#00f2ff; font-weight:bold;">');
        lt = lt.replace(/\x1b\[1;36m/g, '<span style="color:#00ff99; font-weight:bold;">');
        lt = lt.replace(/\x1b\[1m/g, '<span style="font-weight:bold;">');
        lt = lt.replace(/\x1b\[2m/g, '<span style="opacity:0.6;">');
        lt = lt.replace(/\x1b\[0m/g, '</span>');
        return lt;
    }

    return { init, print };
})();
