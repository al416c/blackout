/**
 * BLACKOUT — Point d'entrée principal côté client
 * Orchestre les modules et gère la navigation entre les écrans.
 */

const App = (() => {
    let selectedMalware = 'worm';
    let selectedDifficulty = 'normal';

    function init() {
        console.log('[APP] Initialisation...');
        // Connexion WebSocket
        WS.connect();

        // Initialiser les modules avec sécurité
        try { Auth.init(); } catch(e) { console.error('Auth.init fail', e); }
        try { Particles.init(); Particles.start(); } catch(e) { console.error('Particles.init fail', e); }
        try { Leaderboard.init(); } catch(e) { console.error('Leaderboard.init fail', e); }
        try { Upgrades.init(); } catch(e) { console.error('Upgrades.init fail', e); }
        try { Game.init(); } catch(e) { console.error('Game.init fail', e); }
        try { Terminal.init(); } catch(e) { console.error('Terminal.init fail', e); }

        // Sélection de malware
        document.querySelectorAll('.malware-card').forEach(card => {
            card.addEventListener('click', () => {
                console.log('[APP] Sélection malware:', card.dataset.class);
                document.querySelectorAll('.malware-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                selectedMalware = card.dataset.class;
            });
        });

        // Sélection de difficulté
        document.querySelectorAll('input[name="difficulty"]').forEach(input => {
            input.addEventListener('change', () => {
                selectedDifficulty = input.value || 'normal';
            });
        });

        // Bouton lancer la partie
        const btnStart = document.getElementById('btn-start-game');
        if (btnStart) {
            btnStart.addEventListener('click', () => {
                WS.send('new_game', {
                    malware_class: selectedMalware,
                    difficulty: selectedDifficulty,
                });
                showScreen('game');
            });
        }

        // Bouton déconnexion
        const btnLogout = document.getElementById('btn-logout');
        if (btnLogout) {
            btnLogout.addEventListener('click', () => {
                Auth.logout();
            });
        }

        // Bouton retour au menu depuis game over
        const btnBackGO = document.getElementById('btn-back-menu-go');
        if (btnBackGO) {
            btnBackGO.addEventListener('click', () => {
                document.getElementById('game-over-overlay').classList.add('hidden');
                showScreen('menu');
            });
        }

        // Modal Règles
        const btnRules = document.getElementById('btn-rules');
        if (btnRules) {
            btnRules.addEventListener('click', () => {
                document.getElementById('rules-modal').classList.remove('hidden');
                document.body.classList.add('modal-open');
            });
        }
        const btnCloseRules = document.getElementById('btn-close-rules');
        if (btnCloseRules) {
            btnCloseRules.addEventListener('click', () => {
                document.getElementById('rules-modal').classList.add('hidden');
                document.body.classList.remove('modal-open');
            });
        }
    }

    function showScreen(name) {
        document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
        const screen = document.getElementById(`${name}-screen`);
        if (screen) screen.classList.add('active');

        // Gérer les particules et le glitch
        if (name === 'game' || name === 'leaderboard') {
            Particles.stop();
            document.body.classList.add('is-playing'); // Réutilisation de la classe pour stopper le glitch
        } else {
            Particles.start();
            document.body.classList.remove('is-playing');
        }

        // Gérer la visibilité du terminal
        const terminal = document.getElementById('terminal-panel');
        if (terminal) {
            terminal.style.display = (name === 'game') ? 'flex' : 'none';
        }
    }

    function toast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const el = document.createElement('div');
        el.className = `toast toast-${type}`;
        el.textContent = message;
        container.appendChild(el);
        setTimeout(() => el.remove(), 3000);
    }

    return { init, showScreen, toast };
})();

// Lancer l'app au chargement
document.addEventListener('DOMContentLoaded', App.init);
