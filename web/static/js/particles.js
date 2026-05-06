/* ═══════════════════════════════════════════════════
   PARTICLE SYSTEM — Butterfly-themed floating orbs
   Canvas-free, pure CSS + JS hybrid
   ═══════════════════════════════════════════════════ */
(function () {
  const canvas = document.getElementById('particle-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let W, H, particles = [], mouse = { x: -1000, y: -1000 };

  const COLORS = [
    'rgba(124, 58, 237, 0.6)',   // purple
    'rgba(244, 114, 182, 0.5)',  // pink
    'rgba(52, 211, 153, 0.4)',   // mint
    'rgba(167, 139, 250, 0.35)', // purple light
  ];

  function resize() {
    W = canvas.width = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }

  class Particle {
    constructor() { this.reset(); }
    reset() {
      this.x = Math.random() * W;
      this.y = Math.random() * H;
      this.size = 1.5 + Math.random() * 3;
      this.speedX = (Math.random() - 0.5) * 0.4;
      this.speedY = -0.2 - Math.random() * 0.5;
      this.color = COLORS[Math.floor(Math.random() * COLORS.length)];
      this.opacity = 0.2 + Math.random() * 0.5;
      this.life = 0;
      this.maxLife = 300 + Math.random() * 400;
    }
    update() {
      this.life++;
      if (this.life > this.maxLife) this.reset();

      // Mouse repulsion
      const dx = this.x - mouse.x, dy = this.y - mouse.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 120) {
        this.x += (dx / dist) * 1.5;
        this.y += (dy / dist) * 1.5;
      }

      this.x += this.speedX + Math.sin(this.life * 0.01) * 0.3;
      this.y += this.speedY;

      if (this.y < -10) { this.y = H + 10; this.x = Math.random() * W; }
    }
    draw() {
      const fade = this.life < 40 ? this.life / 40
                 : this.life > this.maxLife - 40 ? (this.maxLife - this.life) / 40
                 : 1;
      ctx.globalAlpha = this.opacity * fade;
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
      ctx.fillStyle = this.color;
      ctx.fill();

      // Glow effect
      ctx.globalAlpha = this.opacity * fade * 0.3;
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.size * 3, 0, Math.PI * 2);
      ctx.fillStyle = this.color;
      ctx.fill();
    }
  }

  function init() {
    resize();
    const count = Math.min(80, Math.floor(W * H / 15000));
    particles = [];
    for (let i = 0; i < count; i++) particles.push(new Particle());
  }

  function animate() {
    ctx.clearRect(0, 0, W, H);
    
    // Draw connections first (more efficient blending)
    ctx.lineWidth = 0.5;
    for (let i = 0; i < particles.length; i++) {
      const p1 = particles[i];
      for (let j = i + 1; j < particles.length; j++) {
        const p2 = particles[j];
        const dx = p1.x - p2.x;
        const dy = p1.y - p2.y;
        const distSq = dx * dx + dy * dy;
        
        if (distSq < 10000) { // 100 * 100
            const d = Math.sqrt(distSq);
            ctx.globalAlpha = 0.05 * (1 - d / 100);
            ctx.strokeStyle = 'rgba(167, 139, 250, 0.4)';
            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.stroke();
        }
      }
    }

    ctx.globalAlpha = 1;
    particles.forEach(p => { p.update(); p.draw(); });
    requestAnimationFrame(animate);
  }

  window.addEventListener('resize', () => { resize(); });
  window.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; });
  window.addEventListener('mouseout', () => { mouse.x = -1000; mouse.y = -1000; });

  init();
  animate();
})();
