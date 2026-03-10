/**
 * BLACKOUT — Module d'authentification côté client
 */

const Auth = (() => {
    let currentUser = null;

    function init() {
        // Tabs
        document.querySelectorAll('#auth-tabs .tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('#auth-tabs .tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');

                const target = tab.dataset.tab;
                document.getElementById('login-form').classList.toggle('hidden', target !== 'login');
                document.getElementById('register-form').classList.toggle('hidden', target !== 'register');
                hideError();
            });
        });

        // Login form
        document.getElementById('login-form').addEventListener('submit', (e) => {
            e.preventDefault();
            const username = document.getElementById('login-username').value.trim();
            const password = document.getElementById('login-password').value;
            WS.send('login', { username, password });
        });

        // Register form
        document.getElementById('register-form').addEventListener('submit', (e) => {
            e.preventDefault();
            const username = document.getElementById('reg-username').value.trim();
            const password = document.getElementById('reg-password').value;
            const password2 = document.getElementById('reg-password2').value;

            if (password !== password2) {
                showError('Les mots de passe ne correspondent pas.');
                return;
            }
            WS.send('register', { username, password });
        });

        // Listen for auth result
        WS.on('auth_result', (data) => {
            if (data.ok) {
                currentUser = {
                    id: data.user_id,
                    username: data.username,
                    games_played: data.games_played || 0,
                    games_won: data.games_won || 0,
                    best_score: data.best_score || 0,
                };
                hideError();
                App.showScreen('menu');
                document.getElementById('welcome-msg').textContent =
                    `Bienvenue, ${currentUser.username}`;
            } else {
                showError(data.error);
            }
        });
    }

    function showError(msg) {
        const el = document.getElementById('auth-error');
        el.textContent = msg;
        el.classList.remove('hidden');
    }

    function hideError() {
        document.getElementById('auth-error').classList.add('hidden');
    }

    function getUser() { return currentUser; }

    function logout() {
        currentUser = null;
        document.getElementById('login-username').value = '';
        document.getElementById('login-password').value = '';
        App.showScreen('auth');
    }

    return { init, getUser, logout };
})();
