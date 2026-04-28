/**
 * BLACKOUT — Effet de réseau de particules (Constellation)
 * Gère l'arrière-plan animé et interactif.
 */

const Particles = (() => {
    let canvas, ctx;
    let particles = [];
    const mouse = { x: null, y: null, radius: 150 };
    const config = {
        count: 150,
        connectionDist: 200,
        particleColor: 'rgba(0, 0, 0, 0.7)',
        lineColor: 'rgba(0, 0, 0, 0.4)',
        speed: 0.8
    };

    class Particle {
        constructor() {
            this.init();
        }
        init() {
            this.x = Math.random() * canvas.width;
            this.y = Math.random() * canvas.height;
            this.vx = (Math.random() - 0.5) * config.speed;
            this.vy = (Math.random() - 0.5) * config.speed;
            this.size = 2;
        }
        update() {
            this.x += this.vx;
            this.y += this.vy;

            if (this.x < 0 || this.x > canvas.width) this.vx *= -1;
            if (this.y < 0 || this.y > canvas.height) this.vy *= -1;

            // Interaction souris
            if (mouse.x && mouse.y) {
                let dx = mouse.x - this.x;
                let dy = mouse.y - this.y;
                let dist = Math.sqrt(dx*dx + dy*dy);
                if (dist < mouse.radius) {
                    // Attraction légère
                    this.x += dx * 0.01;
                    this.y += dy * 0.01;
                }
            }
        }
        draw() {
            ctx.fillStyle = config.particleColor;
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    let isRunning = false;

    function init() {
        canvas = document.getElementById('bg-particles');
        if (!canvas) return;
        ctx = canvas.getContext('2d');
        resize();

        particles = [];
        for (let i = 0; i < config.count; i++) {
            particles.push(new Particle());
        }

        window.addEventListener('resize', resize);
        window.addEventListener('mousemove', e => {
            mouse.x = e.x;
            mouse.y = e.y;
        });
        window.addEventListener('mouseout', () => {
            mouse.x = null;
            mouse.y = null;
        });
    }

    function start() {
        if (isRunning) return;
        isRunning = true;
        canvas.style.display = 'block';
        animate();
    }

    function stop() {
        isRunning = false;
        canvas.style.display = 'none';
    }

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    function animate() {
        if (!isRunning) return;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        for (let i = 0; i < particles.length; i++) {
            particles[i].update();
            particles[i].draw();

            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx*dx + dy*dy);

                if (dist < config.connectionDist) {
                    let opacity = 1 - (dist / config.connectionDist);
                    ctx.strokeStyle = `rgba(0, 0, 0, ${opacity * 0.4})`;
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.stroke();
                }
            }

            // Connection à la souris
            if (mouse.x && mouse.y) {
                const dx = particles[i].x - mouse.x;
                const dy = particles[i].y - mouse.y;
                const dist = Math.sqrt(dx*dx + dy*dy);
                if (dist < mouse.radius) {
                    let opacity = 1 - (dist / mouse.radius);
                    ctx.strokeStyle = `rgba(0, 0, 0, ${opacity * 0.6})`;
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(mouse.x, mouse.y);
                    ctx.stroke();
                }
            }
        }
        requestAnimationFrame(animate);
    }

    return { init, start, stop };
})();
