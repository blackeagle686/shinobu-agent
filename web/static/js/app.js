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

  const mentionDropdown = document.getElementById('file-mention-dropdown');
  const attachBtn = document.getElementById('attach-btn');
  const fileUpload = document.getElementById('file-upload');
  const previewTemplate = document.getElementById('file-preview-template');
  const previewModal = document.getElementById('file-preview-modal');
  const previewModalBackdrop = document.getElementById('file-preview-modal-backdrop');
  const previewModalBody = document.getElementById('file-preview-modal-body');
  const previewModalTitle = document.getElementById('file-preview-modal-title');
  const previewModalClose = document.getElementById('file-preview-modal-close');

  const modeSelector = document.getElementById('mode-selector');
  let currentMode = modeSelector ? modeSelector.value : 'auto';
  const MAX_LIVE_ITEMS = 80;

  if (modeSelector) {
      modeSelector.addEventListener('change', () => {
          currentMode = modeSelector.value;
      });
  }

  function closePreviewModal() {
      if (!previewModal) return;
      previewModal.classList.remove('is-open');
      previewModal.setAttribute('aria-hidden', 'true');
      if (previewModalBody) previewModalBody.innerHTML = '';
  }

  async function openPreviewModal(path, filename) {
      if (!previewModal || !previewModalBody) return;
      const ext = (filename.split('.').pop() || '').toLowerCase();
      const viewUrl = `/api/view-file?path=${encodeURIComponent(path)}`;
      previewModalTitle.textContent = filename || 'File Preview';
      previewModal.classList.add('is-open');
      previewModal.setAttribute('aria-hidden', 'false');

      if (['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp'].includes(ext)) {
          previewModalBody.innerHTML = `<img src="${viewUrl}" alt="${filename}">`;
      } else if (ext === 'pdf') {
          previewModalBody.innerHTML = `<embed src="${viewUrl}" type="application/pdf">`;
      } else {
          try {
              const text = await fetch(viewUrl).then(r => r.text());
              previewModalBody.innerHTML = `<pre class="file-preview-modal-text"></pre>`;
              previewModalBody.querySelector('.file-preview-modal-text').textContent = text;
          } catch (_) {
              previewModalBody.innerHTML = `<div style="padding:1.2rem;color:var(--text-secondary);">Preview not available.</div>`;
          }
      }
  }

  if (previewModalClose) previewModalClose.addEventListener('click', closePreviewModal);
  if (previewModalBackdrop) previewModalBackdrop.addEventListener('click', closePreviewModal);
  document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closePreviewModal();
  });

  function createLivePanel() {
      const panel = document.createElement('div');
      panel.className = 'agent-live-panel';
      panel.innerHTML = `
        <div class="agent-live-header">
          <div class="agent-live-title-wrap">
            <i class="bi bi-cpu"></i>
            <h4>Agent Thinking & Planning</h4>
            <span class="agent-live-chip">Running</span>
          </div>
          <button class="agent-live-clear" type="button" title="Clear live feed">
            <i class="bi bi-trash3"></i>
          </button>
        </div>
        <div class="agent-live-feed">
          <div class="agent-live-empty">Live LLM updates will appear here.</div>
        </div>
      `;
      const clearBtn = panel.querySelector('.agent-live-clear');
      const feed = panel.querySelector('.agent-live-feed');
      const chip = panel.querySelector('.agent-live-chip');
      clearBtn.addEventListener('click', () => {
          feed.innerHTML = '<div class="agent-live-empty">Live LLM updates will appear here.</div>';
      });
      return { panel, feed, chip };
  }

  function setLiveState(live, state) {
      if (!live?.chip) return;
      live.chip.textContent = state;
  }

  function pushLiveEvent(live, role, text) {
      if (!live?.feed || !text) return;
      const empty = live.feed.querySelector('.agent-live-empty');
      if (empty) empty.remove();

      const line = document.createElement('div');
      line.className = 'agent-live-item';
      const safeRole = (role || 'system').toLowerCase();
      line.innerHTML = `
        <span class="agent-live-role ${safeRole}">${safeRole}</span>
        <span class="agent-live-text"></span>
        <span class="agent-live-time">${timeNow()}</span>
      `;
      line.querySelector('.agent-live-text').textContent = text.trim();
      live.feed.appendChild(line);

      while (live.feed.children.length > MAX_LIVE_ITEMS) {
          live.feed.removeChild(live.feed.firstChild);
      }
      live.feed.scrollTop = live.feed.scrollHeight;
  }

  let replyingTo = null;

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

  // ─── FILE MENTION (@) LOGIC ───
  userInput.addEventListener('input', async (e) => {
      const val = userInput.value;
      const lastAt = val.lastIndexOf('@');
      
      if (lastAt !== -1 && (lastAt === 0 || val[lastAt - 1] === ' ')) {
          const query = val.substring(lastAt + 1);
          console.log(`[@ Mention] Triggered with query: "${query}"`);
          
          try {
              const files = await fetch(`/api/files?q=${encodeURIComponent(query)}`).then(r => r.json());
              console.log(`[@ Mention] Found ${files.length} matches`);
              showMentionDropdown(files, lastAt);
          } catch (err) {
              console.error(`[@ Mention] Fetch failed:`, err);
          }
      } else {
          mentionDropdown.style.display = 'none';
      }
  });

  function showMentionDropdown(files, atIndex) {
      if (!files.length) {
          mentionDropdown.style.display = 'none';
          return;
      }
      
      mentionDropdown.innerHTML = '';
      files.forEach(file => {
          const item = document.createElement('div');
          item.className = 'file-mention-item';
          item.innerHTML = `
              <i class="bi ${file.is_dir ? 'bi-folder' : 'bi-file-earmark-text'}"></i>
              <div style="display:flex; flex-direction:column;">
                  <span style="font-weight:600; font-size:0.85rem;">${file.name}</span>
                  <span class="file-path">${file.rel_path}</span>
              </div>
          `;
          item.onclick = () => {
              const before = userInput.value.substring(0, atIndex);
              const after = userInput.value.substring(userInput.selectionStart);
              userInput.value = before + file.rel_path + ' ' + after;
              mentionDropdown.style.display = 'none';
              userInput.focus();
          };
          mentionDropdown.appendChild(item);
      });
      mentionDropdown.style.display = 'block';
  }

  // ─── FILE UPLOAD LOGIC ───
  attachBtn.addEventListener('click', () => fileUpload.click());

  fileUpload.addEventListener('change', async () => {
      if (!fileUpload.files.length) return;
      
      const file = fileUpload.files[0];
      const formData = new FormData();
      formData.append('file', file);

      addMessage(`Uploading file: <b>${file.name}</b>...`, 'user');

      try {
          const res = await fetch('/api/upload', {
              method: 'POST',
              body: formData
          }).then(r => r.json());

          if (res.success) {
              const msg = addMessage(`Attached: <b>${file.name}</b>`, 'agent');
              addFilePreview(msg, res.path, file.name);
          }
      } catch (err) {
          addMessage('Failed to upload file.', 'agent');
      }
      fileUpload.value = '';
  });

  function addFilePreview(messageDiv, path, filename) {
      const clone = previewTemplate.content.cloneNode(true);
      const card = clone.querySelector('.file-preview-card');
      card.querySelector('.file-name').textContent = filename;
      
      const body = card.querySelector('.file-preview-body');
      const ext = filename.split('.').pop().toLowerCase();
      const viewUrl = `/api/view-file?path=${encodeURIComponent(path)}`;

      if (['jpg', 'jpeg', 'png', 'gif', 'svg'].includes(ext)) {
          body.innerHTML = `<img src="${viewUrl}" alt="${filename}">`;
      } else if (ext === 'pdf') {
          body.innerHTML = `<embed src="${viewUrl}" type="application/pdf">`;
      } else {
          body.innerHTML = `<div style="padding:2rem; color:var(--text-secondary);"><i class="bi bi-file-earmark-text" style="font-size:2rem;"></i><br>Preview not available for .${ext} files</div>`;
      }

      card.querySelector('.close-preview').onclick = () => card.remove();
      card.querySelector('.open-file-btn').onclick = () => openPreviewModal(path, filename);
      card.querySelector('.save-as-btn').onclick = () => {
          const newName = prompt('Enter new filename/path:', filename);
          if (newName) {
              userInput.value = `save ${filename} as ${newName}`;
              chatForm.dispatchEvent(new Event('submit'));
          }
      };

      messageDiv.appendChild(card);
  }

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
    window.hasAddedMoreBtn = false;
    window.hasAddedFilePreview = false;

    const typingDiv = showTyping();
    const live = createLivePanel();
    typingDiv.prepend(live.panel);
    const streamStatus = document.createElement('span');
    streamStatus.className = 'agent-stream-status';
    streamStatus.style.cssText = 'color:var(--mint);font-size:0.82rem;display:block;margin-bottom:0.45rem;';
    typingDiv.appendChild(streamStatus);
    setLiveState(live, 'Running');

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
              streamStatus.textContent = `🦋 ${data.content}`;
              pushLiveEvent(live, data.role || 'system', data.content || '');
            } else if (data.type === 'chunk') {
              if (data.role) {
                pushLiveEvent(live, data.role, data.content || '');
              }
              if (!contentStarted) {
                const contentEl = document.createElement('span');
                contentEl.className = 'content';
                typingDiv.appendChild(contentEl);
                contentStarted = true;
              }
              agentText += data.content;
              
              // Render with Marked if available, else fallback
              const renderedHtml = window.marked ? marked.parse(agentText) : agentText.replace(/\n/g, '<br>');
              typingDiv.querySelector('.content').innerHTML = renderedHtml;

               // Detect search completion and add "More Results" button
              const isSearchResponse = agentText.includes('Search |') || agentText.includes('Search Results for:');
              
              // Detect file creation/update and add preview
              if (agentText.includes('✅ File written:') || agentText.includes('✅ File updated:')) {
                  const match = agentText.match(/(?:File written|File updated): (.*)/);
                  if (match && !window.hasAddedFilePreview) {
                      const filePath = match[1].trim();
                      const fileName = filePath.split('/').pop();
                      addFilePreview(typingDiv, filePath, fileName);
                      window.hasAddedFilePreview = true;
                  }
              }

              if (isSearchResponse && !window.hasAddedMoreBtn) {
                if (agentText.includes('Complete') || agentText.includes('Found')) {
                   window.hasAddedMoreBtn = true;
                   
                   // Broad query extraction
                   const queryMatch = agentText.match(/Search Results for: \*(.*?)\*/i) || 
                                     agentText.match(/query: "(.*?)"/i) || 
                                     agentText.match(/Searching for (.*?)\n/i);
                   
                   const finalQuery = queryMatch ? queryMatch[1] : text;
                   
                   const btnContainer = document.createElement('div');
                   btnContainer.style.marginTop = '1rem';
                   btnContainer.innerHTML = `
                     <a href="/search?q=${encodeURIComponent(finalQuery)}" class="more-results-btn">
                        <span>🔍 View All Results in Search Hub</span>
                     </a>
                   `;
                   typingDiv.querySelector('.content').appendChild(btnContainer);
                }
              }
            }
          } catch (_) {}
        }
        chatMessages.scrollTop = chatMessages.scrollHeight;
      }
      setLiveState(live, 'Completed');

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
      streamStatus.style.color = 'var(--pink-hot)';
      streamStatus.textContent = 'Connection error. Please try again.';
      setLiveState(live, 'Error');
    }
  });
});
