/**
 * BLACKOUT — Terminal de commandes (façon hacking)
 * Permet de saisir des commandes texte qui pilotent des actions côté serveur.
 */

const Terminal = (() => {
    let outputEl;
    let inputEl;

    function init() {
        outputEl = document.getElementById('terminal-output');
        inputEl = document.getElementById('terminal-input');
        if (!outputEl || !inputEl) return;

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
        const line = document.createElement('div');
        line.className = 'terminal-line terminal-system';
        line.textContent = text;
        outputEl.appendChild(line);
        outputEl.scrollTop = outputEl.scrollHeight;
    }

    return { init, appendLine, appendSystem };
})();

document.addEventListener('DOMContentLoaded', () => {
    Terminal.init();
});

