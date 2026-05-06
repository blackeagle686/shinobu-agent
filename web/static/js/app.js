document.addEventListener('DOMContentLoaded', () => {
    const chatMessages = document.getElementById('chat-messages');
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const sessionIdDisplay = document.getElementById('session-id');
    
    // Generate a random session ID
    const sessionId = 'session_' + Math.random().toString(36).substr(2, 9);
    sessionIdDisplay.textContent = sessionId;

    // Create background butterflies
    const container = document.getElementById('butterfly-container');
    for (let i = 0; i < 15; i++) {
        const b = document.createElement('div');
        b.className = 'butterfly';
        b.style.left = Math.random() * 100 + 'vw';
        b.style.top = Math.random() * 100 + 'vh';
        b.style.animationDelay = Math.random() * 5 + 's';
        b.style.animationDuration = (5 + Math.random() * 10) + 's';
        container.appendChild(b);
    }

    function addMessage(content, role) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;
        
        const textSpan = document.createElement('span');
        textSpan.innerHTML = content.replace(/\n/g, '<br>');
        msgDiv.appendChild(textSpan);
        
        const tsSpan = document.createElement('span');
        tsSpan.className = 'ts';
        tsSpan.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        msgDiv.appendChild(tsSpan);
        
        chatMessages.appendChild(msgDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = userInput.value.trim();
        if (!text) return;

        addMessage(text, 'user');
        userInput.value = '';
        
        // Show typing indicator placeholder
        const typingId = 'typing-' + Date.now();
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message agent';
        typingDiv.id = typingId;
        typingDiv.innerHTML = '<span class="pulse">Processing intent...</span>';
        chatMessages.appendChild(typingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: text, session_id: sessionId })
            });
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let agentText = '';
            
            typingDiv.innerHTML = ''; // Clear indicator

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                
                const chunk = decoder.decode(value);
                // Handle SSE format "data: {...}"
                const lines = chunk.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.substring(6));
                            if (data.type === 'status') {
                                typingDiv.innerHTML = `<span style="color: var(--mint); font-size: 0.8rem;">🦋 ${data.content}</span>`;
                            } else if (data.type === 'chunk') {
                                agentText += data.content;
                                // For chunks, we'll replace the status with the actual text once it starts coming
                                if (!typingDiv.querySelector('.content')) {
                                    typingDiv.innerHTML = '<span class="content"></span>';
                                }
                                typingDiv.querySelector('.content').innerHTML = agentText.replace(/\n/g, '<br>');
                            }
                        } catch (e) {}
                    }
                }
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
            
            // Finalize message
            typingDiv.removeAttribute('id');
            const ts = document.createElement('span');
            ts.className = 'ts';
            ts.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            typingDiv.appendChild(ts);

        } catch (error) {
            console.error('Chat error:', error);
            typingDiv.innerHTML = '<span style="color: #ff5555;">Sorry, I encountered an error.</span>';
        }
    });
});
