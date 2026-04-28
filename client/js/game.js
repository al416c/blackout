/**
 * BLACKOUT — Module de rendu du jeu (Canvas)
 * Système de zones réseau avec routeurs à infecter pour déverrouiller les zones.
 */

const Game = (() => {
    let canvas, ctx;
    let state = null;
    let animFrame = null;
    let hoveredNode = null;
    let hoveredBubble = null;
    let buildings = [];

    const BUBBLE_STYLES = {
        breach:       { color: '#8a4fff', shape: 'diamond', label: 'BRCH' },
        exfiltration: { color: '#8a4fff', shape: 'circle',  label: 'EXFL' },
        log_analysis: { color: '#00f2ff', shape: 'circle',  label: 'LOGS' },
        patch_deploy: { color: '#00f2ff', shape: 'diamond', label: 'PTCH' }
    };

    // Chance de craquage d'un routeur selon le niveau de sécurité (miroir du serveur)
    const ROUTER_CRACK_CHANCE = { 1: 25, 2: 16, 3: 10, 4: 6, 5: 3 };

    let zoom = 1.0;
    let offsetX = 0;
    let offsetY = 0;
    let isPanning = false;
    let lastPanX = 0, lastPanY = 0;

    function generateCity() {
        buildings = [];
        for (let i = 0; i < 300; i++) {
            buildings.push({
                x: Math.random() * 1200 - 100, y: Math.random() * 900 - 100,
                w: 12 + Math.random() * 22, h: 12 + Math.random() * 22,
                type: 'small'
            });
        }
        for (let i = 0; i < 35; i++) {
            buildings.push({
                x: Math.random() * 1000 - 50, y: Math.random() * 750 - 50,
                w: 70 + Math.random() * 100, h: 70 + Math.random() * 100,
                type: 'large', details: Math.random() > 0.5 ? 'helipad' : 'none'
            });
        }
    }

    function drawCity(s) {
        if (!ctx) return;

        ctx.strokeStyle = 'rgba(0, 242, 255, 0.03)';
        ctx.lineWidth = 0.5;
        const gridSize = 30 * s;
        ctx.beginPath();
        for (let x = offsetX % gridSize; x < canvas.width; x += gridSize) { ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); }
        for (let y = offsetY % gridSize; y < canvas.height; y += gridSize) { ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); }
        ctx.stroke();

        buildings.forEach(b => {
            const bx = b.x * s + offsetX, by = b.y * s + offsetY;
            const bw = b.w * s, bh = b.h * s;
            if (bx + bw < 0 || bx > canvas.width || by + bh < 0 || by > canvas.height) return;

            ctx.fillStyle = b.type === 'large' ? '#121520' : '#0c0e16';
            ctx.fillRect(bx, by, bw, bh);

            if (b.type === 'large' && s > 0.6 && b.details === 'helipad') {
                ctx.strokeStyle = 'rgba(255,255,255,0.04)';
                ctx.beginPath(); ctx.arc(bx + bw/2, by + bh/2, bw/4, 0, Math.PI*2); ctx.stroke();
            }
        });
    }

    function init() {
        canvas = document.getElementById('network-canvas');
        if (!canvas) return;
        ctx = canvas.getContext('2d');

        generateCity();
        resizeCanvas();
        startRenderLoop();

        window.addEventListener('resize', () => { resizeCanvas(); });
        new ResizeObserver(() => { if (canvas.clientWidth > 0) resizeCanvas(); }).observe(canvas.parentElement);

        canvas.addEventListener('mousemove', onMouseMove);
        canvas.addEventListener('wheel', onWheel, { passive: false });
        canvas.addEventListener('mousedown', onMouseDown);
        window.addEventListener('mouseup', onMouseUp);

        WS.on('game_started', (data) => {
            state = data.state;
            Upgrades.loadUpgrades();
            generateCity();
            resizeCanvas();
            // Centrer la vue sur le milieu du layout des zones
            offsetX = canvas.width / 2 - 430 * zoom;
            offsetY = canvas.height / 2 - 340 * zoom;
            updateHUD();
        });

        WS.on('tick', (data) => {
            state = data.state;
            Upgrades.updatePurchased(state.purchased_upgrades);
            updateHUD();
            _updateBlueBudget();
        });

        WS.on('game_over', data => showGameOver(data.result, data.score));
    }

    function resizeCanvas() {
        if (!canvas || !canvas.parentElement) return;
        const oldW = canvas.width, oldH = canvas.height;
        const w = canvas.parentElement.clientWidth, h = canvas.parentElement.clientHeight;
        if (w > 0 && h > 0 && (w !== canvas.width || h !== canvas.height)) {
            canvas.width = w; canvas.height = h;
            if (oldW > 0) { offsetX += (w - oldW) / 2; offsetY += (h - oldH) / 2; }
        }
    }

    function startRenderLoop() {
        if (animFrame) cancelAnimationFrame(animFrame);
        const loop = () => { render(); animFrame = requestAnimationFrame(loop); };
        animFrame = requestAnimationFrame(loop);
    }

    function render() {
        if (!ctx) return;
        ctx.fillStyle = '#050608';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        const s = zoom;
        drawCity(s);

        if (!state || !state.nodes) {
            ctx.fillStyle = 'rgba(0, 242, 255, 0.2)';
            ctx.font = '10px monospace'; ctx.textAlign = 'center';
            ctx.fillText('UPLINK_SEARCHING...', canvas.width/2, canvas.height/2);
            return;
        }

        // Construire le map zone_id → zone
        const zoneMap = {};
        (state.zones || []).forEach(z => { zoneMap[z.id] = z; });

        // 1. Dessiner les zones (halos + bordures)
        (state.zones || []).forEach(zone => {
            const cx = zone.cx * s + offsetX;
            const cy = zone.cy * s + offsetY;
            const r  = zone.radius * s;

            ctx.save();
            if (zone.unlocked) {
                const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
                grad.addColorStop(0, zone.color + '20');
                grad.addColorStop(1, 'transparent');
                ctx.fillStyle = grad;
                ctx.beginPath();
                ctx.arc(cx, cy, r, 0, Math.PI * 2);
                ctx.fill();

                ctx.strokeStyle = zone.color + '55';
                ctx.lineWidth = 1.2 * s;
                ctx.setLineDash([8 * s, 4 * s]);
                ctx.beginPath();
                ctx.arc(cx, cy, r, 0, Math.PI * 2);
                ctx.stroke();
                ctx.setLineDash([]);
            } else {
                ctx.strokeStyle = 'rgba(255,255,255,0.08)';
                ctx.lineWidth = 1 * s;
                ctx.setLineDash([5 * s, 8 * s]);
                ctx.beginPath();
                ctx.arc(cx, cy, r, 0, Math.PI * 2);
                ctx.stroke();
                ctx.setLineDash([]);
            }
            ctx.restore();

            // Label de zone
            ctx.save();
            ctx.textAlign = 'center';
            ctx.font = `bold ${11 * s}px monospace`;
            ctx.fillStyle = zone.unlocked ? zone.color + 'cc' : 'rgba(255,255,255,0.18)';
            ctx.fillText(zone.name, cx, cy - r - 6 * s);
            if (!zone.unlocked) {
                ctx.font = `${9 * s}px monospace`;
                ctx.fillStyle = 'rgba(255,80,80,0.6)';
                ctx.fillText(`SEC.LVL ${zone.security_level} — VERROUILLE`, cx, cy - r + 6 * s);
            }
            ctx.restore();
        });

        // 2. Dessiner les connexions
        state.nodes.forEach(node => {
            // Noeuds intérieurs des zones verrouillées : masqués
            if (!node.zone_unlocked && !node.is_router) return;

            node.connections.forEach(nid => {
                if (nid <= node.id) return;
                const target = state.nodes[nid];
                if (!target) return;
                if (!target.zone_unlocked && !target.is_router) return;

                const both = node.infected && target.infected;
                ctx.save();
                ctx.beginPath();
                if (both) {
                    ctx.strokeStyle = node.zone_color;
                    ctx.lineWidth = 2.5 * s;
                    ctx.shadowColor = node.zone_color;
                    ctx.shadowBlur = 10 * s;
                } else {
                    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
                    ctx.lineWidth = 1.0 * s;
                    ctx.setLineDash([5, 5]);
                    ctx.shadowBlur = 0;
                }
                ctx.moveTo(node.x * s + offsetX, node.y * s + offsetY);
                ctx.lineTo(target.x * s + offsetX, target.y * s + offsetY);
                ctx.stroke();
                ctx.setLineDash([]);
                ctx.shadowBlur = 0;
                ctx.restore();
            });
        });

        // 3. Dessiner les noeuds
        state.nodes.forEach(node => {
            if (!node.zone_unlocked && !node.is_router) return;

            const x = node.x * s + offsetX;
            const y = node.y * s + offsetY;
            const isHovered = node === hoveredNode;
            const baseR = node.is_router ? 11 : 8;
            const r = (isHovered ? baseR + 4 : baseR) * s;
            const color = node.zone_color;

            ctx.save();

            if (node.infected) {
                // Noeud infecté : plein, brillant
                ctx.shadowColor = color;
                ctx.shadowBlur = 22 * s;
                ctx.fillStyle = color;
                ctx.beginPath();
                if (node.is_router) {
                    ctx.rect(x - r, y - r, r * 2, r * 2);
                } else {
                    ctx.moveTo(x, y - r); ctx.lineTo(x + r, y); ctx.lineTo(x, y + r); ctx.lineTo(x - r, y); ctx.closePath();
                }
                ctx.fill();
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 2 * s;
                ctx.stroke();
            } else if (node.is_router && !node.zone_unlocked) {
                // Routeur d'une zone verrouillée — cible d'attaque, affiché en rouge
                ctx.shadowColor = '#ff4444';
                ctx.shadowBlur = 10 * s;
                ctx.fillStyle = 'rgba(255,68,68,0.12)';
                ctx.strokeStyle = '#ff4444bb';
                ctx.lineWidth = 2 * s;
                ctx.beginPath();
                ctx.rect(x - r * 0.9, y - r * 0.9, r * 1.8, r * 1.8);
                ctx.fill();
                ctx.stroke();
                // Croix "verrou"
                ctx.strokeStyle = '#ff4444cc';
                ctx.lineWidth = 1.5 * s;
                ctx.beginPath();
                ctx.moveTo(x - 4*s, y - 4*s); ctx.lineTo(x + 4*s, y + 4*s);
                ctx.moveTo(x + 4*s, y - 4*s); ctx.lineTo(x - 4*s, y + 4*s);
                ctx.stroke();
            } else {
                // Noeud sain d'une zone déverrouillée
                ctx.fillStyle = 'rgba(15, 15, 25, 0.85)';
                ctx.strokeStyle = color + '88';
                ctx.lineWidth = 1.5 * s;
                ctx.beginPath();
                if (node.is_router) {
                    ctx.rect(x - 7 * s, y - 7 * s, 14 * s, 14 * s);
                } else {
                    ctx.arc(x, y, 6 * s, 0, Math.PI * 2);
                }
                ctx.fill();
                ctx.stroke();
            }

            // Tooltip au survol
            if (isHovered) {
                ctx.fillStyle = '#ffffff';
                ctx.font = `bold ${11 * s}px monospace`;
                ctx.textAlign = 'center';
                const label = node.zone_name + (node.is_router ? ' — ROUTEUR' : ` — NODE_0x${node.id.toString(16)}`);
                ctx.fillText(label, x, y - 22 * s);
                if (node.is_router && !node.zone_unlocked) {
                    const zone = zoneMap[node.zone_id];
                    const chance = zone ? (ROUTER_CRACK_CHANCE[zone.security_level] || 5) : '?';
                    ctx.font = `${9 * s}px monospace`;
                    ctx.fillStyle = '#ff6666';
                    ctx.fillText(`Craquage ~${chance}%/tick`, x, y - 11 * s);
                } else if (node.is_router && node.zone_unlocked) {
                    ctx.font = `${9 * s}px monospace`;
                    ctx.fillStyle = node.zone_color;
                    ctx.fillText('ZONE DEBLOQUEE', x, y - 11 * s);
                }
            }

            ctx.restore();
        });

        // 4. Scan highlights — anneau cyan autour des noeuds détectés
        if (scannedHighlight.length > 0) {
            scannedHighlight.forEach(nid => {
                const node = state.nodes[nid];
                if (!node) return;
                const x = node.x * s + offsetX, y = node.y * s + offsetY;
                ctx.save();
                ctx.strokeStyle = '#00f2ff';
                ctx.lineWidth = 2 * s;
                ctx.shadowColor = '#00f2ff';
                ctx.shadowBlur = 12;
                ctx.beginPath();
                ctx.arc(x, y, 20 * s, 0, Math.PI * 2);
                ctx.stroke();
                ctx.restore();
            });
        }

        // 5. Bulles cliquables
        (state.bubbles || []).forEach(b => {
            const x = b.x * s + offsetX, y = b.y * s + offsetY;
            const r = (b === hoveredBubble ? 22 : 18) * s;
            const style = BUBBLE_STYLES[b.kind] || BUBBLE_STYLES.breach;

            ctx.save();
            ctx.shadowColor = style.color;
            ctx.shadowBlur = 15 * s;
            ctx.fillStyle = style.color + '33';
            ctx.strokeStyle = style.color;
            ctx.lineWidth = 2 * s;

            ctx.beginPath();
            if (style.shape === 'diamond') {
                ctx.moveTo(x, y - r); ctx.lineTo(x + r, y); ctx.lineTo(x, y + r); ctx.lineTo(x - r, y); ctx.closePath();
            } else {
                ctx.arc(x, y, r, 0, Math.PI * 2);
            }
            ctx.fill();
            ctx.stroke();

            ctx.fillStyle = '#ffffff';
            ctx.font = `bold ${9 * s}px monospace`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.shadowBlur = 0;
            ctx.fillText(style.label, x, y - 2 * s);
            ctx.font = `${8 * s}px monospace`;
            ctx.fillText(`+${b.value}`, x, y + 8 * s);
            ctx.restore();
        });
    }

    function getScaledPos(e) {
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;
        return {
            x: (e.clientX - rect.left) * scaleX,
            y: (e.clientY - rect.top) * scaleY,
            s: zoom
        };
    }

    function onMouseMove(e) {
        if (!state) return;
        const { x, y, s } = getScaledPos(e);
        hoveredNode = null;
        hoveredBubble = null;

        for (const b of (state.bubbles || [])) {
            if (Math.hypot(x - (b.x * s + offsetX), y - (b.y * s + offsetY)) < 30 * s) {
                hoveredBubble = b; canvas.style.cursor = 'pointer'; return;
            }
        }

        for (const n of state.nodes) {
            // Noeuds invisibles des zones verrouillées non-routeurs
            if (!n.zone_unlocked && !n.is_router) continue;
            if (Math.hypot(x - (n.x * s + offsetX), y - (n.y * s + offsetY)) < 20 * s) {
                hoveredNode = n; canvas.style.cursor = 'pointer'; return;
            }
        }
        canvas.style.cursor = 'default';
    }

    function onWheel(e) {
        if (!state) return;
        e.preventDefault();
        const prevZoom = zoom;
        zoom = e.deltaY < 0 ? Math.min(4.0, zoom * 1.1) : Math.max(0.3, zoom / 1.1);
        const rect = canvas.getBoundingClientRect();
        offsetX = e.clientX - rect.left - (e.clientX - rect.left - offsetX) * (zoom / prevZoom);
        offsetY = e.clientY - rect.top - (e.clientY - rect.top - offsetY) * (zoom / prevZoom);
    }

    function onMouseDown(e) {
        if (!state) return;

        if (hoveredBubble) {
            WS.send('click_bubble', { bubble_id: hoveredBubble.id });
            return;
        }

        if (hoveredNode && App.getPendingBlueAction()) {
            WS.send('blue_action', { action: App.getPendingBlueAction(), node_id: hoveredNode.id });
            App.clearPendingBlueAction();
            return;
        }

        isPanning = true;
        lastPanX = e.clientX;
        lastPanY = e.clientY;
    }

    function onMouseUp() { isPanning = false; }

    window.addEventListener('mousemove', e => {
        if (!isPanning) return;
        offsetX += e.clientX - lastPanX;
        offsetY += e.clientY - lastPanY;
        lastPanX = e.clientX; lastPanY = e.clientY;
    });

    function updateHUD() {
        if (!state) return;

        const role = (typeof App !== 'undefined') ? App.getRole() : 'red';
        const cpuEl = document.getElementById('hud-cpu');
        if (cpuEl) {
            const val = role === 'blue' ? state.it_budget : state.cpu_cycles;
            cpuEl.textContent = Math.floor(val).toLocaleString();
        }

        const pct = Math.min(100, Math.max(0, state.suspicion));
        const text = document.getElementById('suspicion-text');
        if (text) text.textContent = Math.floor(pct) + '%';

        const segments = document.querySelectorAll('#detection-segments .segment');
        if (segments.length > 0) {
            const activeCount = Math.floor((pct / 100) * segments.length);
            segments.forEach((seg, idx) => {
                seg.classList.toggle('active', idx < activeCount);
            });
        }
    }

    let scannedHighlight = [];
    let scannedTimer = null;

    function highlightScanned(nodeIds) {
        scannedHighlight = nodeIds;
        if (scannedTimer) clearTimeout(scannedTimer);
        scannedTimer = setTimeout(() => { scannedHighlight = []; }, 3000);
    }

    function _updateBlueBudget() {
        if (!state) return;
        const el = document.getElementById('blue-budget-display');
        if (el) el.textContent = Math.floor(state.it_budget) + ' IT';
    }

    function showGameOver(result, score) {
        const overlay = document.getElementById('game-over-overlay');
        const title = document.getElementById('game-over-title');
        title.textContent = result === 'victory' ? 'VICTOIRE' : 'DEFAITE';
        title.style.color = result === 'victory' ? '#00ff99' : '#ff0055';
        document.getElementById('game-over-score').textContent = score;
        overlay.classList.remove('hidden');
    }

    return { init, getState: () => state, highlightScanned };
})();
