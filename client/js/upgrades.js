/**
 * BLACKOUT — Module Arbre d'évolution (upgrades)
 */

const Upgrades = (() => {
    let allUpgrades = [];
    let purchasedIds = [];

    const BRANCH_LABELS = {
        transmission: 'Transmission',
        symptomes: 'Symptomes',
        capacites: 'Capacites',
    };

    // Couleurs des branches
    const BRANCH_COLORS = {
        transmission: 'var(--red)',
        symptomes:    'var(--orange)',
        capacites:    'var(--blue)',
    };

    let currentStats = null;

    function init() {
        WS.on('upgrades_list', (data) => {
            allUpgrades = data.data || [];
            render();
        });

        WS.on('upgrade_result', (data) => {
            if (data.ok) {
                App.toast(`${data.upgrade} acquis !`, 'success');
            } else {
                App.toast(data.error, 'error');
            }
        });

        document.getElementById('toggle-upgrades').addEventListener('click', () => {
            const panel = document.getElementById('upgrade-panel');
            panel.classList.toggle('collapsed');
            const btn = document.getElementById('toggle-upgrades');
            btn.textContent = panel.classList.contains('collapsed') ? '▶' : '◀';
        });
    }

    function loadUpgrades() {
        WS.send('get_upgrades');
    }

    function updatePurchased(ids) {
        purchasedIds = ids || [];
        render();
    }

    function updateStats(state) {
        currentStats = state;
        renderStatsPanel(state);
    }

    function renderStatsPanel(state) {
        let panel = document.getElementById('upgrade-stats-panel');
        if (!panel) return;
        if (!state) { panel.innerHTML = ''; return; }
        const cd = state.special_cooldown || 0;
        const hackStatus = cd > 0
            ? `<span class="stat-val stat-cd">hack : recharge (${cd})</span>`
            : `<span class="stat-val stat-ready">hack : PRET</span>`;
        panel.innerHTML = `
            <div class="stat-row"><span class="stat-key">Propagation</span><span class="stat-val">x${(1 + (state.propagation_mod||0)).toFixed(2)}</span></div>
            <div class="stat-row"><span class="stat-key">Furtivite</span><span class="stat-val">${Math.round((state.stealth_mod||0)*100)}%</span></div>
            <div class="stat-row"><span class="stat-key">Revenu</span><span class="stat-val">x${(1 + (state.income_mod||0)).toFixed(2)}</span></div>
            <div class="stat-row">${hackStatus}</div>
        `;
    }

    function render() {
        const container = document.getElementById('upgrade-tree');
        container.innerHTML = '';

        const branches = {};
        allUpgrades.forEach(u => {
            if (!branches[u.branch]) branches[u.branch] = [];
            branches[u.branch].push(u);
        });

        for (const [branch, upgrades] of Object.entries(branches)) {
            const div = document.createElement('div');
            div.className = 'upgrade-branch';

            const title = document.createElement('div');
            title.className = 'upgrade-branch-title';
            title.style.color = BRANCH_COLORS[branch] || 'var(--accent)';
            title.textContent = BRANCH_LABELS[branch] || branch;
            div.appendChild(title);

            upgrades.sort((a, b) => a.tier - b.tier);

            upgrades.forEach((u, idx) => {
                // Connecteur entre tiers (sauf avant le premier)
                if (idx > 0) {
                    const connector = document.createElement('div');
                    const prevPurchased = purchasedIds.includes(upgrades[idx - 1].id);
                    connector.className = 'upgrade-connector' + (prevPurchased ? ' active' : '');
                    div.appendChild(connector);
                }

                const item = document.createElement('div');
                item.className = 'upgrade-item';

                const purchased = purchasedIds.includes(u.id);
                const prevTierOwned = u.tier <= 1 || upgrades.find(
                    x => x.tier === u.tier - 1 && purchasedIds.includes(x.id)
                );
                const locked = !purchased && !prevTierOwned;

                if (purchased) item.classList.add('purchased');
                if (locked) item.classList.add('locked');

                const tierLabel = `<span class="upgrade-tier">N${u.tier}</span>`;
                item.innerHTML = `
                    ${tierLabel}
                    <span class="upgrade-name">${u.name}</span>
                    <span class="upgrade-cost">${purchased ? 'OK' : u.cost + ' CPU'}</span>
                `;
                item.title = u.description || '';

                if (!purchased && !locked) {
                    item.addEventListener('click', () => {
                        WS.send('buy_upgrade', { upgrade_id: u.id });
                    });
                }

                div.appendChild(item);
            });

            container.appendChild(div);
        }
    }

    return { init, loadUpgrades, updatePurchased, updateStats };
})();
