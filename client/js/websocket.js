/**
 * BLACKOUT — Client WebSocket
 * Gère la connexion bidirectionnelle avec le serveur.
 */

const WS = (() => {
    let socket = null;
    let reconnectTimer = null;
    const listeners = {};
    const pendingMessages = [];

    function connect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${location.host}/ws`;

        socket = new WebSocket(url);

        socket.addEventListener('open', () => {
            console.log('[WS] Connecté au serveur');
            // Envoyer les actions tapées avant la connexion (ex: login rapide au chargement).
            while (pendingMessages.length > 0 && socket.readyState === WebSocket.OPEN) {
                socket.send(pendingMessages.shift());
            }
            emit('connected');
        });

        socket.addEventListener('message', (event) => {
            try {
                const data = JSON.parse(event.data);
                emit(data.type, data);
            } catch (e) {
                console.error('[WS] Message invalide:', e);
            }
        });

        socket.addEventListener('close', () => {
            console.log('[WS] Déconnecté — tentative de reconnexion...');
            emit('disconnected');
            if (reconnectTimer) clearTimeout(reconnectTimer);
            reconnectTimer = setTimeout(connect, 3000);
        });

        socket.addEventListener('error', (err) => {
            console.error('[WS] Erreur:', err);
        });
    }

    function send(action, data = {}) {
        const payload = JSON.stringify({ action, ...data });
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(payload);
        } else {
            console.warn('[WS] Socket non connecté, action mise en attente:', action);
            pendingMessages.push(payload);
        }
    }

    function on(type, callback) {
        if (!listeners[type]) listeners[type] = [];
        listeners[type].push(callback);
    }

    function off(type, callback) {
        if (!listeners[type]) return;
        listeners[type] = listeners[type].filter(cb => cb !== callback);
    }

    function emit(type, data) {
        (listeners[type] || []).forEach(cb => {
            try { cb(data); } catch(e) { console.error(`[WS] Erreur listener ${type}:`, e); }
        });
    }

    return { connect, send, on, off };
})();
