/**
 * BLACKOUT — Module Leaderboard
 */

const Leaderboard = (() => {
    function init() {
        document.getElementById('btn-leaderboard').addEventListener('click', () => {
            WS.send('leaderboard');
            App.showScreen('leaderboard');
        });

        document.getElementById('btn-back-menu').addEventListener('click', () => {
            App.showScreen('menu');
        });

        WS.on('leaderboard', (data) => {
            render(data.data);
        });
    }

    function render(entries) {
        const tbody = document.getElementById('leaderboard-body');
        tbody.innerHTML = '';

        if (!entries || entries.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-dim)">Aucun joueur pour le moment.</td></tr>';
            return;
        }

        entries.forEach((entry, idx) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${idx + 1}</td>
                <td><strong>${escapeHtml(entry.username)}</strong></td>
                <td>${entry.games_played}</td>
                <td>${entry.games_won}</td>
                <td>${entry.best_score}</td>
                <td>${entry.total_nodes}</td>
            `;
            tbody.appendChild(tr);
        });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    return { init };
})();
