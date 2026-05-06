document.addEventListener('DOMContentLoaded', () => {
  const chatMessages = document.getElementById('chat-messages');
  const chatForm = document.getElementById('chat-form');
  const userInput = document.getElementById('user-input');
  const sessionEl = document.getElementById('session-id');

  if (!chatForm) return;

  const sessionId = 'shinobu_' + Math.random().toString(36).substr(2, 8);
  if (sessionEl) sessionEl.textContent = sessionId;

  function timeNow() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function addMessage(html, role) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.innerHTML = `<span>${html}</span><span class="ts">${timeNow()}</span>`;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return div;
  }

  function showTyping() {
    const div = document.createElement('div');
    div.className = 'message agent';
    div.id = 'typing';
    div.innerHTML = `
      <div class="typing-indicator">
        <span></span><span></span><span></span>
      </div>`;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return div;
  }

  chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = userInput.value.trim();
    if (!text) return;

    addMessage(text.replace(/</g, '&lt;'), 'user');
    userInput.value = '';

    const typingDiv = showTyping();

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: text, session_id: sessionId })
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let agentText = '';
      let contentStarted = false;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        for (const line of decoder.decode(value).split('\n')) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.substring(6));
            if (data.type === 'status') {
              typingDiv.innerHTML = `<span style="color:var(--mint);font-size:0.82rem;">🦋 ${data.content}</span>`;
            } else if (data.type === 'chunk') {
              if (!contentStarted) {
                typingDiv.innerHTML = '<span class="content"></span>';
                contentStarted = true;
              }
              agentText += data.content;
              typingDiv.querySelector('.content').innerHTML = agentText.replace(/\n/g, '<br>');
            }
          } catch (_) {}
        }
        chatMessages.scrollTop = chatMessages.scrollHeight;
      }

      typingDiv.removeAttribute('id');
      const ts = document.createElement('span');
      ts.className = 'ts';
      ts.textContent = timeNow();
      typingDiv.appendChild(ts);

    } catch (err) {
      typingDiv.innerHTML = `<span style="color:var(--pink-hot);">Connection error. Please try again.</span>`;
    }
  });
});
