/**
 * BLACKOUT — Client WebSocket
 * Gère la connexion bidirectionnelle avec le serveur.
 */

const WS = (() => {
    let socket = null;
    const listeners = {};

    function connect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${location.host}/ws`;

        socket = new WebSocket(url);

        socket.addEventListener('open', () => {
            console.log('[WS] Connecté au serveur');
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
            setTimeout(connect, 3000);
        });

        socket.addEventListener('error', (err) => {
            console.error('[WS] Erreur:', err);
        });
    }

    function send(action, data = {}) {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ action, ...data }));
        } else {
            console.warn('[WS] Socket non connecté, action ignorée:', action);
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
