/**
 * BLACKOUT — Terminal de commandes (façon hacking)
 * Permet de saisir des commandes texte qui pilotent des actions côté serveur.
 */

const Terminal = (() => {
    const STORAGE_KEY = 'blackout_terminal_height';
    const DEFAULT_HEIGHT = 220;
    const MIN_HEIGHT = 140;
    const MAX_HEIGHT = 560;

    let outputEl;
    let inputEl;
    let panelEl;
    let resizeHandleEl;

    function clampHeight(height) {
        return Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, height));
    }

    function getStoredHeight() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            const value = parseInt(raw || '', 10);
            return Number.isFinite(value) ? value : null;
        } catch (_) {
            return null;
        }
    }

    function persistHeight(height) {
        try {
            localStorage.setItem(STORAGE_KEY, String(height));
        } catch (_) {
            // Ignore storage errors (privacy mode, blocked storage, etc.)
        }
    }

    function applyPanelHeight(height) {
        if (!panelEl) return;
        const clamped = clampHeight(height);
        panelEl.style.height = `${clamped}px`;
        persistHeight(clamped);
    }

    function setupResizeControls() {
        if (!panelEl) return;

        const saved = getStoredHeight();
        applyPanelHeight(saved ?? DEFAULT_HEIGHT);

        const shrinkBtn = document.getElementById('terminal-shrink');
        const resetBtn = document.getElementById('terminal-reset');
        const growBtn = document.getElementById('terminal-grow');

        shrinkBtn?.addEventListener('click', () => {
            applyPanelHeight(panelEl.offsetHeight - 24);
        });
        resetBtn?.addEventListener('click', () => {
            applyPanelHeight(DEFAULT_HEIGHT);
        });
        growBtn?.addEventListener('click', () => {
            applyPanelHeight(panelEl.offsetHeight + 24);
        });

        let dragging = false;
        let startY = 0;
        let startHeight = 0;

        function startDrag(clientY) {
            dragging = true;
            startY = clientY;
            startHeight = panelEl.offsetHeight;
            document.body.classList.add('terminal-resizing');
        }

        function moveDrag(clientY) {
            if (!dragging) return;
            const delta = startY - clientY;
            applyPanelHeight(startHeight + delta);
        }

        function stopDrag() {
            dragging = false;
            document.body.classList.remove('terminal-resizing');
        }

        resizeHandleEl?.addEventListener('mousedown', (e) => {
            e.preventDefault();
            startDrag(e.clientY);
        });

        window.addEventListener('mousemove', (e) => {
            moveDrag(e.clientY);
        });

        window.addEventListener('mouseup', () => {
            stopDrag();
        });

        resizeHandleEl?.addEventListener('touchstart', (e) => {
            if (!e.touches.length) return;
            startDrag(e.touches[0].clientY);
        }, { passive: true });

        window.addEventListener('touchmove', (e) => {
            if (!e.touches.length) return;
            moveDrag(e.touches[0].clientY);
        }, { passive: true });

        window.addEventListener('touchend', () => {
            stopDrag();
        });
    }

    function init() {
        outputEl = document.getElementById('terminal-output');
        inputEl = document.getElementById('terminal-input');
        panelEl = document.getElementById('terminal-panel');
        resizeHandleEl = document.getElementById('terminal-resize-handle');
        if (!outputEl || !inputEl || !panelEl) return;

        setupResizeControls();

        inputEl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const line = inputEl.value.trim();
                if (!line) return;

                if (line.toLowerCase() === 'clear') {
                    outputEl.innerHTML = '';
                    inputEl.value = '';
                    return;
                }

                appendLine(`root@blackout:~# ${line}`);
                inputEl.value = '';
                WS.send('command', { line });
            } else if (e.key === 'c' && (e.ctrlKey || e.metaKey)) {
                // Petit clin d'œil Ctrl+C
                appendSystem('^C');
            }
        });

        // Garder le focus sur l'entrée quand on clique dans le panneau
        document.getElementById('terminal-panel').addEventListener('click', () => {
            inputEl.focus();
        });

        // Résultats des commandes côté serveur
        WS.on('command_result', (data) => {
            if (data.output) {
                appendSystem(data.output);
            }
            if (data.error) {
                appendSystem(`Erreur: ${data.error}`);
            }
        });

        // Premier message d'accueil
        appendSystem('┌─────────────────────────────────────────────────┐');
        appendSystem('│  ██████╗ ██╗      █████╗  ██████╗██╗  ██╗ ██████╗ ██╗   ██╗████████╗');
        appendSystem('│  ██╔══██╗██║     ██╔══██╗██╔════╝██║ ██╔╝██╔═══██╗██║   ██║╚══██╔══╝');
        appendSystem('│  ██████╔╝██║     ███████║██║     █████╔╝ ██║   ██║██║   ██║   ██║   ');
        appendSystem('│  ██╔══██╗██║     ██╔══██║██║     ██╔═██╗ ██║   ██║██║   ██║   ██║   ');
        appendSystem('│  ██████╔╝███████╗██║  ██║╚██████╗██║  ██╗╚██████╔╝╚██████╔╝   ██║   ');
        appendSystem('│  ╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝    ╚═╝   ');
        appendSystem('└─────────────────────────────────────────────────┘');
        appendSystem('Session initialisée. Tapez "help" pour afficher les commandes disponibles.');
    }

    function appendLine(text) {
        if (!outputEl) return;
        const line = document.createElement('div');
        line.className = 'terminal-line';
        line.textContent = text;
        outputEl.appendChild(line);
        outputEl.scrollTop = outputEl.scrollHeight;
    }

    function appendSystem(text) {
        if (!outputEl) return;
        const lines = String(text ?? '').split('\n');
        for (const part of lines) {
            const line = document.createElement('div');
            line.className = 'terminal-line terminal-system';
            line.textContent = part;
            outputEl.appendChild(line);
        }
        outputEl.scrollTop = outputEl.scrollHeight;
    }

    return { init, appendLine, appendSystem };
})();

document.addEventListener('DOMContentLoaded', () => {
    Terminal.init();
});

