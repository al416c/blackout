/**
 * BLACKOUT — Module Arbre d'évolution (upgrades)
 */

const Upgrades = (() => {
    let allUpgrades = [];
    let purchasedIds = [];

    const BRANCH_NAMES = {
        transmission: '📡 Transmission',
        symptomes: '💀 Symptômes',
        capacites: '🛡️ Capacités',
    };

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
            title.textContent = BRANCH_NAMES[branch] || branch;
            div.appendChild(title);

            upgrades.sort((a, b) => a.tier - b.tier);

            upgrades.forEach(u => {
                const item = document.createElement('div');
                item.className = 'upgrade-item';

                const purchased = purchasedIds.includes(u.id);
                const prevTierOwned = u.tier <= 1 || upgrades.find(
                    x => x.tier === u.tier - 1 && purchasedIds.includes(x.id)
                );
                const locked = !purchased && !prevTierOwned;

                if (purchased) item.classList.add('purchased');
                if (locked) item.classList.add('locked');

                item.innerHTML = `
                    <span class="upgrade-name">${u.name}</span>
                    <span class="upgrade-cost">${purchased ? '✓' : u.cost + ' ⚡'}</span>
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

    return { init, loadUpgrades, updatePurchased };
})();
