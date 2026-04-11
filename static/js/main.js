// ── Page-level wiring: scroll header, chat controls, scroll-reveal ────────────

// Sticky header accent line
const siteHeader = document.getElementById('site-header');
window.addEventListener('scroll', () => {
  siteHeader.classList.toggle('scrolled', window.scrollY > 10);
}, { passive: true });

// Chat overlay controls
document.getElementById('btn-chat-close').addEventListener('click', closeChatOverlay);
document.getElementById('btn-chat-send').addEventListener('click', sendChatAnswer);

document.getElementById('chat-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendChatAnswer();
  }
});

// Auto-grow chat textarea
document.getElementById('chat-input').addEventListener('input', function () {
  this.style.height = '';
  this.style.height = Math.min(this.scrollHeight, 140) + 'px';
});

// Scroll-reveal for sections with .reveal class
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.12 });

document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));
