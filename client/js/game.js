/**
 * BLACKOUT — Module de rendu du jeu (Canvas)
 * Thème : Galactique / Dense City
 */

const Game = (() => {
    let canvas, ctx;
    let state = null;
    let animFrame = null;
    let hoveredNode = null;
    let buildings = []; 

    let zoom = 1.0;
    let offsetX = 0;
    let offsetY = 0;
    let isPanning = false;
    let lastPanX = 0, lastPanY = 0;

    const COLORS = {
        bg:          '#050608', 
        infected:    '#8a4fff', 
        healthy:     'rgba(255, 255, 255, 0.05)', 
        quarantined: '#aa44ff',
        connection:  'rgba(255, 255, 255, 0.1)', 
        connectionInfected: 'rgba(138, 79, 255, 0.9)', // Violet opaque
    };

    function generateCity() {
        buildings = [];
        for (let i = 0; i < 400; i++) { // Plus de bâtiments
            buildings.push({
                x: Math.random() * 2400 - 700, y: Math.random() * 2000 - 650,
                w: 12 + Math.random() * 25, h: 12 + Math.random() * 25,
                type: 'small'
            });
        }
        for (let i = 0; i < 50; i++) {
            buildings.push({
                x: Math.random() * 1600 - 300, y: Math.random() * 1400 - 300,
                w: 80 + Math.random() * 120, h: 80 + Math.random() * 120,
                type: 'large', details: Math.random() > 0.5 ? 'helipad' : 'none'
            });
        }
    }

    function drawCity(s) {
        if (!ctx) return;
        
        ctx.strokeStyle = 'rgba(0, 242, 255, 0.03)';
        ctx.lineWidth = 0.5;
        const gridSize = 30 * s; // Grille plus serrée comme dans le mockup
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
                ctx.strokeStyle = 'rgba(255,255,255,0.05)';
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
            if (state.nodes && state.nodes.length > 0) {
                offsetX = canvas.width / 2 - (state.nodes[0].x * zoom);
                offsetY = canvas.height / 2 - (state.nodes[0].y * zoom);
            }
            updateHUD();
        });

        WS.on('tick', (data) => {
            state = data.state;
            Upgrades.updatePurchased(state.purchased_upgrades);
            updateHUD();
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
        ctx.fillStyle = COLORS.bg;
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        const s = zoom;
        drawCity(s);

        if (!state || !state.nodes) {
            ctx.fillStyle = 'rgba(0, 242, 255, 0.2)';
            ctx.font = '10px monospace'; ctx.textAlign = 'center';
            ctx.fillText('UPLINK_SEARCHING...', canvas.width/2, canvas.height/2);
            return;
        }

        // Connections
        state.nodes.forEach(node => {
            node.connections.forEach(nid => {
                if (nid > node.id) {
                    const target = state.nodes[nid];
                    if (!target) return;
                    const both = node.infected && target.infected;

                    
                    ctx.beginPath();
                    if (both) {
                        ctx.strokeStyle = '#8a4fff'; // Violet éclatant
                        ctx.lineWidth = 2.5;
                        ctx.setLineDash([]);
                        ctx.shadowColor = '#8a4fff';
                        ctx.shadowBlur = 10;
                    } else {
                        ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
                        ctx.lineWidth = 1.0;
                        ctx.setLineDash([5, 5]); // Pointillés
                        ctx.shadowBlur = 0;
                    }
                    
                    ctx.moveTo(node.x * s + offsetX, node.y * s + offsetY);
                    ctx.lineTo(target.x * s + offsetX, target.y * s + offsetY);
                    ctx.stroke();
                    ctx.setLineDash([]);
                    ctx.shadowBlur = 0;
                }
            });
        });

        // Nodes
        state.nodes.forEach(node => {
            const x = node.x * s + offsetX, y = node.y * s + offsetY;
            const r = (node === hoveredNode ? 12 : 9) * s;

            if (node.infected) {
                ctx.save();
                ctx.shadowColor = '#8a4fff'; ctx.shadowBlur = 25 * s;
                ctx.fillStyle = '#8a4fff';
                // Diamant
                ctx.beginPath(); 
                ctx.moveTo(x, y - r); 
                ctx.lineTo(x + r, y); 
                ctx.lineTo(x, y + r); 
                ctx.lineTo(x - r, y); 
                ctx.closePath();
                ctx.fill();
                
                // Bordure blanche épaisse
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 2 * s;
                ctx.stroke();
                ctx.restore();
            } else {
                ctx.fillStyle = 'rgba(255, 255, 255, 0.05)';
                ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
                ctx.lineWidth = 1 * s;
                ctx.beginPath();
                ctx.rect(x - 5*s, y - 5*s, 10*s, 10*s);
                ctx.closePath();
                ctx.fill();
                ctx.stroke();
            }

            if (node === hoveredNode) {
                ctx.fillStyle = '#fff'; ctx.font = `${10*s}px monospace`; ctx.textAlign = 'center';
                ctx.fillText(`ID_0x${node.id.toString(16).toUpperCase()}`, x, y - 18*s);
            }
        });
    }

    function getScaledPos(e) {
        const rect = canvas.getBoundingClientRect();
        return { x: (e.clientX - rect.left) * (canvas.width / rect.width), y: (e.clientY - rect.top) * (canvas.height / rect.height), s: zoom };
    }

    function onMouseMove(e) {
        if (!state) return;
        const { x, y, s } = getScaledPos(e);
        hoveredNode = null;
        for (const n of state.nodes) {
            if (Math.hypot(x - (n.x * s + offsetX), y - (n.y * s + offsetY)) < 15 * s) {
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

    function onMouseDown(e) { if (!state) return; isPanning = true; lastPanX = e.clientX; lastPanY = e.clientY; }
    function onMouseUp() { isPanning = false; }

    window.addEventListener('mousemove', e => {
        if (!isPanning) return;
        offsetX += e.clientX - lastPanX;
        offsetY += e.clientY - lastPanY;
        lastPanX = e.clientX; lastPanY = e.clientY;
    });

    function updateHUD() {
        if (!state) return;

        // CPU
        const cpuEl = document.getElementById('hud-cpu');
        if (cpuEl) cpuEl.textContent = Math.floor(state.cpu_cycles).toLocaleString();

        // Suspicion
        const pct = Math.min(100, Math.max(0, state.suspicion));
        const text = document.getElementById('suspicion-text');
        if (text) text.textContent = Math.floor(pct) + '%';

        // Segments de détection (Barre massive)
        const segments = document.querySelectorAll('#detection-segments .segment');
        if (segments.length > 0) {
            const activeCount = Math.floor((pct / 100) * segments.length);
            segments.forEach((seg, idx) => {
                if (idx < activeCount) {
                    seg.classList.add('active');
                } else {
                    seg.classList.remove('active');
                }
            });
        }
    }

    function showGameOver(result, score) {
        const overlay = document.getElementById('game-over-overlay');
        const title = document.getElementById('game-over-title');
        title.textContent = result === 'victory' ? '🏆 VICTOIRE' : '💀 DÉFAITE';
        title.style.color = result === 'victory' ? '#00ff99' : '#ff0055';
        document.getElementById('game-over-score').textContent = score;
        overlay.classList.remove('hidden');
    }

    return { init, getState: () => state };
})();
