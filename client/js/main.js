/**
 * BLACKOUT — Point d'entrée principal côté client
 * Orchestre les modules et gère la navigation entre les écrans.
 */

const App = (() => {
    let selectedMalware = 'worm';

    function init() {
        // Connexion WebSocket
        WS.connect();

        // Initialiser les modules
        Auth.init();
        Leaderboard.init();
        Upgrades.init();
        Game.init();

        // Sélection de malware
        document.querySelectorAll('.malware-card').forEach(card => {
            card.addEventListener('click', () => {
                document.querySelectorAll('.malware-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                selectedMalware = card.dataset.class;
            });
        });

        // Bouton lancer la partie
        document.getElementById('btn-start-game').addEventListener('click', () => {
            WS.send('new_game', { malware_class: selectedMalware });
            showScreen('game');
        });

        // Bouton déconnexion
        document.getElementById('btn-logout').addEventListener('click', () => {
            Auth.logout();
        });

        // Bouton retour au menu depuis game over
        document.getElementById('btn-back-menu-go').addEventListener('click', () => {
            document.getElementById('game-over-overlay').classList.add('hidden');
            showScreen('menu');
        });
    }

    function showScreen(name) {
        document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
        const screen = document.getElementById(`${name}-screen`);
        if (screen) screen.classList.add('active');
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
