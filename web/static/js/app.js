document.addEventListener('DOMContentLoaded', () => {
  const chatMessages = document.getElementById('chat-messages');
  const chatForm = document.getElementById('chat-form');
  const userInput = document.getElementById('user-input');
  const sessionEl = document.getElementById('session-id');
  const replyPreview = document.getElementById('reply-preview');
  const replyPreviewText = document.getElementById('reply-preview-text');
  const cancelReplyBtn = document.getElementById('cancel-reply');

  if (!chatForm) return;

  const sessionId = 'shinobu_' + Math.random().toString(36).substr(2, 8);
  if (sessionEl) sessionEl.textContent = sessionId;

  let currentMode = 'agent_loop';
  let replyingTo = null;

  const modeBtns = document.querySelectorAll('.mode-btn');
  modeBtns.forEach(btn => {
      btn.addEventListener('click', () => {
          modeBtns.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          currentMode = btn.dataset.mode;
      });
  });

  function timeNow() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function setReply(text) {
      replyingTo = text;
      replyPreviewText.textContent = `Replying to: "${text.substring(0, 50)}${text.length > 50 ? '...' : ''}"`;
      replyPreview.style.display = 'flex';
      userInput.focus();
  }

  function clearReply() {
      replyingTo = null;
      replyPreview.style.display = 'none';
  }

  cancelReplyBtn.addEventListener('click', clearReply);

  function addMessage(html, role) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    
    const content = document.createElement('span');
    content.innerHTML = html;
    div.appendChild(content);

    const ts = document.createElement('span');
    ts.className = 'ts';
    ts.textContent = timeNow();
    div.appendChild(ts);

    // Add Reply Button
    const actions = document.createElement('div');
    actions.className = 'message-actions';
    const replyBtn = document.createElement('button');
    replyBtn.className = 'action-btn';
    replyBtn.innerHTML = '↩';
    replyBtn.title = 'Reply';
    replyBtn.onclick = () => setReply(content.innerText);
    actions.appendChild(replyBtn);
    div.appendChild(actions);

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

  // Initial message needs a reply button too
  const firstMsg = chatMessages.querySelector('.message');
  if (firstMsg) {
      const actions = document.createElement('div');
      actions.className = 'message-actions';
      const replyBtn = document.createElement('button');
      replyBtn.className = 'action-btn';
      replyBtn.innerHTML = '↩';
      replyBtn.onclick = () => setReply(firstMsg.querySelector('span').innerText);
      actions.appendChild(replyBtn);
      firstMsg.appendChild(actions);
  }

  chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    let text = userInput.value.trim();
    if (!text) return;

    let displayPrompt = text;
    let fullPrompt = text;

    if (replyingTo) {
        fullPrompt = `[CONTEXT REPLY TO: "${replyingTo}"]\n\n${text}`;
        clearReply();
    }

    addMessage(displayPrompt.replace(/</g, '&lt;'), 'user');
    userInput.value = '';
    window.hasRedirected = false;

    const typingDiv = showTyping();

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: fullPrompt, session_id: sessionId, mode: currentMode })
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

              // Detect search completion and redirect
              if (agentText.includes('Search |') && !window.hasRedirected) {
                const searchMatch = agentText.match(/(?:Search \|).*?\n(.*)/i);
                const queryMatch = agentText.match(/query: "(.*?)"/i) || agentText.match(/Searching for (.*?)\n/i);
                
                if (agentText.includes('Complete') || agentText.includes('Found')) {
                   window.hasRedirected = true;
                   setTimeout(() => {
                      const finalQuery = queryMatch ? queryMatch[1] : text;
                      window.location.href = `/search?q=${encodeURIComponent(finalQuery)}`;
                   }, 2500);
                }
              }
            }
          } catch (_) {}
        }
        chatMessages.scrollTop = chatMessages.scrollHeight;
      }

      // Finalize message with reply button
      const actions = document.createElement('div');
      actions.className = 'message-actions';
      const replyBtn = document.createElement('button');
      replyBtn.className = 'action-btn';
      replyBtn.innerHTML = '↩';
      replyBtn.onclick = () => setReply(agentText);
      actions.appendChild(replyBtn);
      typingDiv.appendChild(actions);

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
