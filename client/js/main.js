/**
 * BLACKOUT — Point d'entrée principal côté client
 * Orchestre les modules et gère la navigation entre les écrans.
 */

const App = (() => {
    let selectedMalware = 'worm';
    let selectedDifficulty = 'normal';
    let playerRole = 'red';
    let pendingBlueAction = null;

    function init() {
        WS.connect();

        try { Auth.init(); } catch(e) { console.error('Auth.init fail', e); }
        try { Particles.init(); Particles.start(); } catch(e) { console.error('Particles.init fail', e); }
        try { Leaderboard.init(); } catch(e) { console.error('Leaderboard.init fail', e); }
        try { Upgrades.init(); } catch(e) { console.error('Upgrades.init fail', e); }
        try { Game.init(); } catch(e) { console.error('Game.init fail', e); }
        try { Terminal.init(); } catch(e) { console.error('Terminal.init fail', e); }

        document.querySelectorAll('.malware-card').forEach(card => {
            card.addEventListener('click', () => {
                document.querySelectorAll('.malware-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                selectedMalware = card.dataset.class;
            });
        });

        document.querySelectorAll('input[name="difficulty"]').forEach(input => {
            input.addEventListener('change', () => { selectedDifficulty = input.value || 'normal'; });
        });

        // ── Mode de jeu ────────────────────────────────────────────
        const btnSoloAI = document.getElementById('btn-solo-ai');
        if (btnSoloAI) {
            btnSoloAI.addEventListener('click', () => {
                // Masquer le panneau Blue Team immédiatement — on joue Red Team en solo
                document.getElementById('blue-panel')?.classList.add('hidden');
                document.querySelector('.side-panel')?.classList.remove('hidden');
                playerRole = 'red';
                WS.send('create_room', {
                    malware_class: selectedMalware,
                    difficulty: selectedDifficulty,
                    mode: 'solo_ai',
                });
                showScreen('game');
            });
        }

        const btnCreateRoom = document.getElementById('btn-create-room');
        if (btnCreateRoom) {
            btnCreateRoom.addEventListener('click', () => {
                WS.send('create_room', {
                    malware_class: selectedMalware,
                    difficulty: selectedDifficulty,
                    mode: 'duo',
                });
            });
        }

        const btnJoinRoom = document.getElementById('btn-join-room');
        if (btnJoinRoom) {
            btnJoinRoom.addEventListener('click', () => {
                document.getElementById('join-overlay').classList.remove('hidden');
                document.getElementById('join-code-input').value = '';
                document.getElementById('join-error').classList.add('hidden');
            });
        }

        // ── Overlays ───────────────────────────────────────────────
        const btnCancelRoom = document.getElementById('btn-cancel-room');
        if (btnCancelRoom) {
            btnCancelRoom.addEventListener('click', () => {
                document.getElementById('room-overlay').classList.add('hidden');
            });
        }

        const btnCancelJoin = document.getElementById('btn-cancel-join');
        if (btnCancelJoin) {
            btnCancelJoin.addEventListener('click', () => {
                document.getElementById('join-overlay').classList.add('hidden');
            });
        }

        const btnConfirmJoin = document.getElementById('btn-confirm-join');
        if (btnConfirmJoin) {
            btnConfirmJoin.addEventListener('click', () => {
                const code = document.getElementById('join-code-input').value.trim().toUpperCase();
                if (code.length < 4) {
                    _showJoinError('Code invalide.');
                    return;
                }
                WS.send('join_room', { room_code: code });
            });
        }

        // ── Blue Team actions ──────────────────────────────────────
        document.querySelectorAll('.blue-action-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const action = btn.dataset.action;
                if (action === 'honeypot' || action === 'quarantine') {
                    // Ces actions nécessitent de choisir un noeud
                    pendingBlueAction = action;
                    document.getElementById('blue-action-hint').classList.remove('hidden');
                    document.querySelectorAll('.blue-action-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                } else {
                    // scan et patch s'appliquent directement
                    WS.send('blue_action', { action });
                    clearPendingBlueAction();
                }
            });
        });

        // ── Déconnexion / navigation ───────────────────────────────
        const btnLogout = document.getElementById('btn-logout');
        if (btnLogout) {
            btnLogout.addEventListener('click', () => { Auth.logout(); });
        }

        const btnBackGO = document.getElementById('btn-back-menu-go');
        if (btnBackGO) {
            btnBackGO.addEventListener('click', () => {
                document.getElementById('game-over-overlay').classList.add('hidden');
                showScreen('menu');
            });
        }

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

        // ── Événements WebSocket ───────────────────────────────────
        WS.on('room_created', (data) => {
            document.getElementById('room-code-display').textContent = data.room_code;
            document.getElementById('room-overlay').classList.remove('hidden');
        });

        WS.on('join_result', (data) => {
            if (!data.ok) {
                _showJoinError(data.error || 'Erreur inconnue.');
            }
        });

        WS.on('game_started', (data) => {
            playerRole = data.role || 'red';
            document.getElementById('join-overlay').classList.add('hidden');
            document.getElementById('room-overlay').classList.add('hidden');
            _applyRole(playerRole);
            showScreen('game');
        });

        WS.on('blue_action_result', (data) => {
            if (data.ok === false) {
                toast(data.error || 'Action impossible.', 'error');
            } else if (data.infected_ids) {
                // Le scan révèle des noeuds infectés — Game.js les highlight
                Game.highlightScanned(data.infected_ids);
                toast(`Scan: ${data.infected_ids.length} noeuds infecte(s) detecte(s).`, 'info');
            } else {
                toast('Action Blue Team appliquee.', 'success');
            }
        });
    }

    function _showJoinError(msg) {
        const el = document.getElementById('join-error');
        el.textContent = msg;
        el.classList.remove('hidden');
    }

    function _applyRole(role) {
        const badge = document.getElementById('hud-role-badge');
        const label = document.getElementById('hud-resource-label');
        const bluePanel = document.getElementById('blue-panel');
        const upgradePanel = document.querySelector('.side-panel');

        if (badge) {
            badge.classList.remove('hidden', 'role-red', 'role-blue');
            badge.classList.add(role === 'blue' ? 'role-blue' : 'role-red');
            badge.textContent = role === 'blue' ? 'BLUE TEAM' : 'RED TEAM';
        }
        if (label) label.textContent = role === 'blue' ? 'IT Budget' : 'CPU Cycles';
        if (bluePanel) bluePanel.classList.toggle('hidden', role !== 'blue');
        if (upgradePanel) upgradePanel.classList.toggle('hidden', role === 'blue');
    }

    function clearPendingBlueAction() {
        pendingBlueAction = null;
        const hint = document.getElementById('blue-action-hint');
        if (hint) hint.classList.add('hidden');
        document.querySelectorAll('.blue-action-btn').forEach(b => b.classList.remove('active'));
    }

    function showScreen(name) {
        document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
        const screen = document.getElementById(`${name}-screen`);
        if (screen) screen.classList.add('active');

        if (name === 'game' || name === 'leaderboard') {
            Particles.stop();
            document.body.classList.add('is-playing');
        } else {
            Particles.start();
            document.body.classList.remove('is-playing');
        }

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

    function getRole() { return playerRole; }
    function getPendingBlueAction() { return pendingBlueAction; }

    return { init, showScreen, toast, getRole, getPendingBlueAction, clearPendingBlueAction };
})();

document.addEventListener('DOMContentLoaded', App.init);
