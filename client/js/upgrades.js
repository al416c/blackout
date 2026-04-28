/**
 * BLACKOUT — Module Arbre d'évolution (upgrades)
 * Fournisseur de données textuelles pour le terminal.
 */

const Upgrades = (() => {
    let allUpgrades = [];
    let purchasedIds = [];
    let isShopPending = false;

    const BRANCH_LABELS = { transmission: 'Transmission', symptomes: 'Symptômes', capacites: 'Capacités' };
    const BRANCH_COLORS = { transmission: '\x1b[1;31m', symptomes: '\x1b[1;33m', capacites: '\x1b[1;34m' };
    const RESET = '\x1b[0m', BOLD = '\x1b[1m', DIM = '\x1b[2m';

    function init() {
        WS.on('upgrades_list', (data) => { 
            console.log('[UPGRADES] Received list:', data.data?.length);
            allUpgrades = data.data || []; 
            if (isShopPending) {
                isShopPending = false;
                Terminal.print(getAvailableModulesText(), 'shop');
            }
        });
        WS.on('upgrade_result', (data) => {
            if (data.ok) Terminal.print(`[SUCCESS] Module '${data.upgrade}' actif.`, 'system');
            else Terminal.print(`[ERROR] ${data.error}`, 'system');
        });
    }

    function loadUpgrades() { WS.send('get_upgrades'); }
    function updatePurchased(ids) { purchasedIds = ids || []; }

    function getAvailableModulesText() {
        if (allUpgrades.length === 0) {
            isShopPending = true;
            loadUpgrades();
            return "\n[SYSTEM] Synchronizing modules with central database... Please wait.\n";
        }
        let out = `\n${BOLD}═══ MODULES D'ÉVOLUTION ═══${RESET}\n\n`;
        const branches = {};
        allUpgrades.forEach(u => { if (!branches[u.branch]) branches[u.branch] = []; branches[u.branch].push(u); });

        // Header for the table
        const HEADER = `${BOLD}${"ID".padEnd(4)} ${"NOM DU MODULE".padEnd(25)} ${"PRIX".padEnd(10)} ${"DESCRIPTION"}${RESET}\n`;
        const SEP    = `${DIM}${"".padEnd(80, "─")}${RESET}\n`;

        for (const [branch, upgrades] of Object.entries(branches)) {
            const color = BRANCH_COLORS[branch] || RESET;
            const label = BRANCH_LABELS[branch] || branch;
            out += `${color}--- ${label.toUpperCase()} ---${RESET}\n`;
            out += HEADER;
            out += SEP;
            
            upgrades.sort((a, b) => a.tier - b.tier).forEach(u => {
                const purchased = purchasedIds.includes(u.id);
                const prevTierOwned = u.tier <= 1 || upgrades.find(x => x.tier === u.tier-1 && purchasedIds.includes(x.id));
                const locked = !purchased && !prevTierOwned;
                
                const idStr = u.id.toString().padStart(2, '0');
                const nameStr = u.name.padEnd(25);
                const priceStr = purchased ? "ACQUIS" : (locked ? "VERROUILLÉ" : `${u.cost} CPU`).padEnd(10);
                const desc = u.description || "Aucune description disponible.";

                if (purchased) {
                    out += `${DIM}[${idStr}] ${nameStr} ${priceStr.padEnd(10)} ${desc}${RESET}\n`;
                } else if (locked) {
                    out += `${DIM}[${idStr}] ${nameStr} ${priceStr.padEnd(10)} ${desc}${RESET}\n`;
                } else {
                    out += `${BOLD}[${idStr}]${RESET} ${nameStr} ${BOLD}${priceStr}${RESET} ${desc}\n`;
                    out += `     ${DIM}> install ${u.id}${RESET}\n`;
                }
            });
            out += "\n";
        }
        return out + `${DIM}Tapez 'install [id]' pour injecter un module.${RESET}\n`;
    }

    function matchUpgrade(input) {
        if (!input) return [];
        const term = input.toLowerCase().replace(/_/g, ' ');
        return allUpgrades.filter(u => !purchasedIds.includes(u.id))
            .filter(u => u.name.toLowerCase().includes(term) || u.id.toString() === term)
            .map(u => ({ id: u.id, name: u.name }));
    }

    return { init, loadUpgrades, updatePurchased, getAvailableModulesText, matchUpgrade, getUpgradeById: (id) => allUpgrades.find(u => u.id === parseInt(id)) };
})();
