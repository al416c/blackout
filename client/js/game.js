/**
 * BLACKOUT — Module de rendu du jeu (Canvas)
 * Affiche le réseau, les nœuds, les connexions et les bulles.
 */

const Game = (() => {
    let canvas, ctx;
    let state = null;
    let animFrame = null;
    let hoveredNode = null;
    let hoveredBubble = null;

    // Couleurs
    const COLORS = {
        infected:    '#ff2244',
        healthy:     '#00cc88',
        quarantined: '#aa44ff',
        honeypot:    '#ffcc00',
        connection:  'rgba(255,255,255,0.08)',
        connectionInfected: 'rgba(255,34,68,0.2)',
    };

    const BUBBLE_COLORS = {
        breach:       { fill: 'rgba(255,34,68,0.7)',  stroke: '#ff2244' },
        exfiltration: { fill: 'rgba(255,153,51,0.7)', stroke: '#ff9933' },
        log_analysis: { fill: 'rgba(51,136,255,0.7)', stroke: '#3388ff' },
        patch_deploy: { fill: 'rgba(0,204,136,0.7)',  stroke: '#00cc88' },
    };

    const BUBBLE_LABELS = {
        breach:       '🔓 Brèche',
        exfiltration: '📤 Exfiltration',
        log_analysis: '📋 Analyse Logs',
        patch_deploy: '🔧 Patch',
    };

    function init() {
        canvas = document.getElementById('network-canvas');
        ctx = canvas.getContext('2d');

        window.addEventListener('resize', resizeCanvas);
        canvas.addEventListener('mousemove', onMouseMove);
        canvas.addEventListener('click', onClick);

        WS.on('game_started', (data) => {
            state = data.state;
            Upgrades.loadUpgrades();
            resizeCanvas();
            startRenderLoop();
            updateHUD();
        });

        WS.on('tick', (data) => {
            state = data.state;
            updateHUD();
            Upgrades.updatePurchased(state.purchased_upgrades);
        });

        WS.on('game_over', (data) => {
            showGameOver(data.result, data.score);
        });

        WS.on('bubble_feedback', (data) => {
            if (data.error) {
                App.toast(data.error, 'error');
            } else if (data.type === 'attacker') {
                App.toast(`+${data.gained} CPU Cycles (${BUBBLE_LABELS[data.kind] || data.kind})`, 'success');
            } else {
                App.toast(`Méfiance +${data.suspicion_added}%`, 'info');
            }
        });
    }

    function resizeCanvas() {
        if (!canvas) return;
        const rect = canvas.parentElement.getBoundingClientRect();
        canvas.width = rect.width;
        canvas.height = rect.height;
    }

    // ── Render Loop ─────────────────────────────────────────────
    function startRenderLoop() {
        cancelAnimationFrame(animFrame);
        (function loop() {
            render();
            animFrame = requestAnimationFrame(loop);
        })();
    }

    function render() {
        if (!state || !ctx) return;
        const w = canvas.width;
        const h = canvas.height;
        ctx.clearRect(0, 0, w, h);

        // Calculer les facteurs d'échelle (la topologie est dans ~900x700)
        const scaleX = w / 900;
        const scaleY = h / 700;

        // ── Dessiner les connexions ─────────────────────────────
        ctx.lineWidth = 1.2;
        state.nodes.forEach(node => {
            node.connections.forEach(nid => {
                if (nid > node.id) {
                    const target = state.nodes[nid];
                    const bothInfected = node.infected && target.infected;
                    ctx.strokeStyle = bothInfected ? COLORS.connectionInfected : COLORS.connection;
                    ctx.beginPath();
                    ctx.moveTo(node.x * scaleX, node.y * scaleY);
                    ctx.lineTo(target.x * scaleX, target.y * scaleY);
                    ctx.stroke();
                }
            });
        });

        // ── Dessiner les nœuds ──────────────────────────────────
        state.nodes.forEach(node => {
            const x = node.x * scaleX;
            const y = node.y * scaleY;
            const radius = node === hoveredNode ? 10 : 7;

            let color;
            if (node.quarantined) color = COLORS.quarantined;
            else if (node.honeypot && !node.infected) color = COLORS.honeypot;
            else if (node.infected) color = COLORS.infected;
            else color = COLORS.healthy;

            // Glow effect pour les nœuds infectés
            if (node.infected && !node.quarantined) {
                ctx.save();
                ctx.shadowColor = COLORS.infected;
                ctx.shadowBlur = 15;
                ctx.fillStyle = COLORS.infected;
                ctx.beginPath();
                ctx.arc(x, y, radius, 0, Math.PI * 2);
                ctx.fill();
                ctx.restore();
            }

            ctx.fillStyle = color;
            ctx.strokeStyle = 'rgba(255,255,255,0.3)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.arc(x, y, radius, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();

            // Label du nœud au survol
            if (node === hoveredNode) {
                ctx.fillStyle = '#fff';
                ctx.font = '11px monospace';
                ctx.textAlign = 'center';
                const status = node.quarantined ? 'Quarantaine' :
                               node.honeypot ? 'Honeypot' :
                               node.infected ? 'Infecté' : 'Sain';
                ctx.fillText(`#${node.id} ${status}`, x, y - 16);
            }
        });

        // ── Dessiner les bulles ─────────────────────────────────
        (state.bubbles || []).forEach(bubble => {
            const x = bubble.x * scaleX;
            const y = bubble.y * scaleY;
            const colors = BUBBLE_COLORS[bubble.kind] || BUBBLE_COLORS.breach;
            const radius = bubble === hoveredBubble ? 22 : 18;

            // Pulse animation
            const pulse = 1 + 0.1 * Math.sin(Date.now() / 300 + bubble.id);

            ctx.save();
            ctx.shadowColor = colors.stroke;
            ctx.shadowBlur = 12;
            ctx.fillStyle = colors.fill;
            ctx.strokeStyle = colors.stroke;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(x, y, radius * pulse, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
            ctx.restore();

            // Texte
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 11px sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(`+${bubble.value}`, x, y);
        });
    }

    // ── Interactivité ───────────────────────────────────────────
    function getScaledPos(e) {
        const rect = canvas.getBoundingClientRect();
        return {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top,
            scaleX: canvas.width / 900,
            scaleY: canvas.height / 700,
        };
    }

    function onMouseMove(e) {
        if (!state) return;
        const { x, y, scaleX, scaleY } = getScaledPos(e);

        hoveredNode = null;
        hoveredBubble = null;

        // Check bubbles first (they're on top)
        for (const b of (state.bubbles || [])) {
            const bx = b.x * scaleX;
            const by = b.y * scaleY;
            if (Math.hypot(x - bx, y - by) < 22) {
                hoveredBubble = b;
                canvas.style.cursor = 'pointer';
                return;
            }
        }

        // Check nodes
        for (const n of state.nodes) {
            const nx = n.x * scaleX;
            const ny = n.y * scaleY;
            if (Math.hypot(x - nx, y - ny) < 12) {
                hoveredNode = n;
                canvas.style.cursor = 'pointer';
                return;
            }
        }

        canvas.style.cursor = 'default';
    }

    function onClick(e) {
        if (!state) return;
        const { x, y, scaleX, scaleY } = getScaledPos(e);

        // Click on bubble?
        for (const b of (state.bubbles || [])) {
            const bx = b.x * scaleX;
            const by = b.y * scaleY;
            if (Math.hypot(x - bx, y - by) < 22) {
                WS.send('click_bubble', { bubble_id: b.id });
                return;
            }
        }
    }

    // ── HUD update ──────────────────────────────────────────────
    function updateHUD() {
        if (!state) return;

        document.getElementById('hud-tick').textContent = state.tick;
        document.getElementById('hud-malware').textContent =
            state.malware_class.charAt(0).toUpperCase() + state.malware_class.slice(1);
        document.getElementById('hud-cpu').textContent = Math.floor(state.cpu_cycles);
        document.getElementById('hud-score').textContent = state.score;

        // Suspicion bar
        const pct = Math.min(100, Math.max(0, state.suspicion));
        document.getElementById('suspicion-fill').style.width = pct + '%';
        document.getElementById('suspicion-text').textContent = Math.floor(pct) + '%';

        // Node info
        document.getElementById('info-infected').textContent = state.infected_count;
        document.getElementById('info-healthy').textContent = state.healthy_count;
        document.getElementById('info-quarantined').textContent = state.quarantined_count;
    }

    // ── Game Over ───────────────────────────────────────────────
    function showGameOver(result, score) {
        const overlay = document.getElementById('game-over-overlay');
        const title = document.getElementById('game-over-title');
        const msg = document.getElementById('game-over-msg');
        const scoreEl = document.getElementById('game-over-score');

        if (result === 'victory') {
            title.textContent = '🏆 VICTOIRE';
            title.style.color = 'var(--green)';
            msg.textContent = 'Le réseau est entièrement compromis !';
        } else {
            title.textContent = '💀 DÉFAITE';
            title.style.color = 'var(--red)';
            msg.textContent = 'Votre malware a été éradiqué par la Blue Team.';
        }

        scoreEl.textContent = score;
        overlay.classList.remove('hidden');
    }

    function getState() { return state; }

    return { init, getState };
})();
