/**
 * Shinobu Search — Frontend controller for the 3-Level Search System.
 * Handles: level selection, search API calls, result rendering (fast/mid/deep).
 */
document.addEventListener('DOMContentLoaded', () => {
    // ── Elements ──
    const searchInput    = document.getElementById('search-input');
    const searchSubmit   = document.getElementById('search-submit');
    const levelSelector  = document.getElementById('level-selector');
    const classBar       = document.getElementById('classification-bar');
    const classBadge     = document.getElementById('classification-badge');
    const clLevel        = document.getElementById('cl-level');
    const clReason       = document.getElementById('cl-reason');
    const clTime         = document.getElementById('cl-time');
    const loadingEl      = document.getElementById('search-loading');
    const loadingText    = document.getElementById('loading-text');
    const resultsEl      = document.getElementById('search-results');
    const resultsGrid    = document.getElementById('results-grid');
    const resultsStats   = document.getElementById('results-stats');
    const statCount      = document.getElementById('stat-count');
    const statEngine     = document.getElementById('stat-engine');
    const statTime       = document.getElementById('stat-time');
    const fastResult     = document.getElementById('fast-result');
    const fastTitle      = document.getElementById('fast-title');
    const fastUrl        = document.getElementById('fast-url');
    const deepContent    = document.getElementById('deep-content');
    const deepPages      = document.getElementById('deep-pages');
    const deepBody       = document.getElementById('deep-body');
    const deepSources    = document.getElementById('deep-sources');
    const emptyState     = document.getElementById('search-empty');
    const exampleBtns    = document.querySelectorAll('.example-btn');

    const intelCard      = document.getElementById('intelligence-card');
    const intelBody      = document.getElementById('intel-body');
    const copyIntelBtn   = document.getElementById('copy-intel');

    if (!searchInput) return;

    let currentLevel = 'auto';

    // ── Copy Intelligence ──
    if (copyIntelBtn) {
        copyIntelBtn.addEventListener('click', () => {
            const text = intelBody.innerText;
            navigator.clipboard.writeText(text);
            copyIntelBtn.textContent = '✅';
            setTimeout(() => copyIntelBtn.textContent = '📋', 2000);
        });
    }

    // ── Check for URL query parameter ──
    const urlParams = new URLSearchParams(window.location.search);
    const queryParam = urlParams.get('q');
    const levelParam = urlParams.get('level');

    if (queryParam) {
        searchInput.value = queryParam;
        if (levelParam && ['auto', 'fast', 'mid', 'deep'].includes(levelParam)) {
            levelSelector.value = levelParam;
            currentLevel = levelParam;
        }
        executeSearch();
    }

    // ── Level Selector ──
    levelSelector.addEventListener('change', () => {
        currentLevel = levelSelector.value;
    });

    // ── Example Queries ──
    exampleBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            searchInput.value = btn.dataset.query;
            searchInput.focus();
            executeSearch();
        });
    });

    // ── Submit Handlers ──
    searchSubmit.addEventListener('click', executeSearch);
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') executeSearch();
    });

    // ── Loading Messages ──
    const LOADING_MESSAGES = {
        auto: ['🤖 Shinobu is analyzing your intent...', '🧠 Classifying search level...', '⚡ Choosing optimal strategy...'],
        fast: ['⚡ Opening browser...', '🌐 Redirecting...'],
        mid:  ['🎯 Searching DuckDuckGo...', '📋 Collecting results...', '🔍 Processing...'],
        deep: ['🧠 Deep searching...', '📚 Scraping pages...', '🔬 Extracting content...', '✨ Analyzing data...']
    };

    function animateLoading(level) {
        const msgs = LOADING_MESSAGES[level] || LOADING_MESSAGES.auto;
        let idx = 0;
        loadingText.textContent = msgs[0];
        return setInterval(() => {
            idx = (idx + 1) % msgs.length;
            loadingText.textContent = msgs[idx];
        }, 1500);
    }

    // ── Reset UI ──
    function resetUI() {
        resultsEl.style.display = 'none';
        fastResult.style.display = 'none';
        resultsStats.style.display = 'none';
        resultsGrid.innerHTML = '';
        deepContent.style.display = 'none';
        deepBody.innerHTML = '';
        deepSources.innerHTML = '';
        classBar.style.display = 'none';
        intelCard.style.display = 'none';
        intelBody.innerHTML = '';
    }

    // ── Main Search ──
    async function executeSearch() {
        const query = searchInput.value.trim();
        if (!query) return;

        // Hide empty, show loading
        emptyState.style.display = 'none';
        resetUI();
        loadingEl.style.display = 'flex';
        const loadInterval = animateLoading(currentLevel);

        try {
            const res = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: query,
                    level: currentLevel,
                    extended: false,
                }),
            });

            const data = await res.json();
            clearInterval(loadInterval);
            loadingEl.style.display = 'none';

            // Show classification badge
            showClassification(data);

            // Render based on level
            resultsEl.style.display = 'block';

            // Handle LLM Answer (Shinobu Intelligence Card)
            if (data.llm_answer) {
                if (window.marked) {
                    intelBody.innerHTML = marked.parse(data.llm_answer);
                } else {
                    intelBody.innerHTML = simpleMarkdownToHtml(data.llm_answer);
                }
                intelCard.style.display = 'block';
            }

            if (data.level === 'fast') {
                renderFastResult(data);
            } else if (data.level === 'mid') {
                renderMidResults(data);
            } else if (data.level === 'deep') {
                renderDeepResults(data);
            }

        } catch (err) {
            clearInterval(loadInterval);
            loadingEl.style.display = 'none';
            emptyState.style.display = 'block';
            console.error('Search failed:', err);
        }
    }

    // ── Helpers ──
    function simpleMarkdownToHtml(text) {
        if (!text) return '';
        // Fallback if marked is not loaded
        return text.replace(/\n/g, '<br>');
    }

    // ── Classification Badge ──
    function showClassification(data) {
        const levelLabels = {
            fast: '🟢 Fast Search',
            mid:  '🟡 Mid Search',
            deep: '🔵 Deep Search',
        };

        clLevel.textContent = levelLabels[data.level] || data.level;
        clLevel.className = `classification-level level-${data.level}`;
        clReason.textContent = data.reason || '';
        clTime.textContent = `${data.elapsed_seconds || 0}s`;
        classBar.style.display = 'block';
    }

    // ── Fast Result ──
    function renderFastResult(data) {
        const url = data.url || data.search_url || '';
        fastTitle.textContent = data.resolved ? 'Opened directly' : 'Opened search in browser';
        fastUrl.textContent = url;
        fastResult.style.display = 'block';
    }

    // ── Mid Results ──
    function renderMidResults(data) {
        const results = data.results || [];
        statCount.textContent = results.length;
        statEngine.textContent = data.engine || 'httpx';
        statTime.textContent = `${data.elapsed_seconds || 0}s`;
        resultsStats.style.display = 'flex';

        results.forEach((r, i) => {
            const card = createResultCard(r, i);
            resultsGrid.appendChild(card);
        });
    }

    // ── Deep Results ──
    function renderDeepResults(data) {
        const pages = data.pages || [];
        const scraped = data.pages_scraped || 0;

        // Stats
        statCount.textContent = pages.length;
        statEngine.textContent = data.from_cache ? 'cached' : 'httpx+bs4';
        statTime.textContent = `${data.elapsed_seconds || 0}s`;
        resultsStats.style.display = 'flex';

        // Result cards (collapsed view)
        pages.forEach((p, i) => {
            const card = createDeepCard(p, i);
            resultsGrid.appendChild(card);
        });

        // Deep content section
        deepPages.textContent = `${scraped}/${pages.length} pages scraped`;
        
        // Build combined content view
        let bodyHTML = '';
        pages.forEach((p, i) => {
            if (!p.scrape_success) return;
            bodyHTML += `<div class="deep-page-section">`;
            bodyHTML += `<h3>${escapeHtml(p.title || 'Untitled')}</h3>`;
            if (p.meta_description) {
                bodyHTML += `<p style="color:var(--text-muted);font-style:italic;font-size:0.82rem;">${escapeHtml(p.meta_description)}</p>`;
            }
            if (p.content) {
                // Show first 600 chars of content
                const preview = p.content.substring(0, 600);
                bodyHTML += `<p>${escapeHtml(preview)}${p.content.length > 600 ? '...' : ''}</p>`;
            }
            bodyHTML += `</div>`;
        });

        if (bodyHTML) {
            deepBody.innerHTML = bodyHTML;
        } else {
            deepBody.innerHTML = '<p style="color:var(--text-muted)">No content could be extracted from the scraped pages.</p>';
        }

        // Sources
        let sourcesHTML = '';
        pages.forEach((p, i) => {
            sourcesHTML += `
                <div class="deep-source-item">
                    <span class="deep-source-num">${i + 1}</span>
                    <span class="deep-source-title">${escapeHtml(p.title || 'Untitled')}</span>
                    <a href="${escapeHtml(p.url || '#')}" target="_blank" rel="noopener" class="deep-source-link">↗ open</a>
                </div>`;
        });
        deepSources.innerHTML = sourcesHTML;
        deepContent.style.display = 'block';
    }

    // ── Card Builders ──
    function createResultCard(r, index) {
        const div = document.createElement('div');
        div.className = 'search-result-card fade-in';
        div.style.animationDelay = `${index * 0.08}s`;
        
        let imgHtml = '';
        if (r.image) {
            imgHtml = `<div class="result-image"><img src="${r.image}" alt="preview" onerror="this.parentElement.style.display='none'"></div>`;
        } else if (r.favicon) {
            imgHtml = `<div class="result-favicon-box"><img src="${r.favicon}" class="result-favicon"></div>`;
        }

        div.innerHTML = `
            ${imgHtml}
            <div class="result-index">${r.index || index + 1}</div>
            <div class="result-title">${escapeHtml(r.title || 'Untitled')}</div>
            <div class="result-url">${escapeHtml(r.display_url || extractDomain(r.url || ''))}</div>
            <div class="result-snippet">${escapeHtml(r.snippet || '')}</div>
            <div class="result-actions">
                <button class="result-action-btn open-btn" onclick="window.open('${escapeAttr(r.url || '#')}', '_blank')">↗ Open</button>
                <button class="result-action-btn" onclick="deepSearchUrl('${escapeAttr(r.url || '')}')">🧠 Deep Scan</button>
            </div>`;

        return div;
    }

    function createDeepCard(page, index) {
        const div = document.createElement('div');
        div.className = 'deep-card fade-in';
        div.style.animationDelay = `${index * 0.15}s`;

        let imgHtml = '';
        if (page.main_image) {
            imgHtml = `<div class="deep-card-image"><img src="${page.main_image}" alt="Page Image" onerror="this.parentElement.style.display='none'"></div>`;
        }

        const score = Math.round((page.word_count || 0) / 10) + (page.headings?.length || 0) * 2;
        const relevance = Math.min(score, 98);

        div.innerHTML = `
            ${imgHtml}
            <div class="deep-card-header">
                <div class="deep-card-badge">Source ${index + 1}</div>
                <div class="deep-card-relevance">Relevance: ${relevance}%</div>
            </div>
            <h4 class="deep-card-title">${escapeHtml(page.title || 'Untitled Source')}</h4>
            <div class="deep-card-url">${escapeHtml(extractDomain(page.url || ''))}</div>
            <div class="deep-card-meta">
                <span>📝 ${page.word_count || 0} words</span>
                <span>📑 ${page.headings?.length || 0} sections</span>
            </div>
            <div class="deep-card-summary">
                ${escapeHtml(page.paragraphs?.[0] || page.meta_description || 'Analysis complete.')}
            </div>
        `;
        return div;
    }

    // ── Helpers ──
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function escapeAttr(text) {
        return text.replace(/'/g, "\\'").replace(/"/g, '&quot;');
    }

    function extractDomain(url) {
        try {
            return new URL(url).hostname;
        } catch {
            return url.substring(0, 50);
        }
    }

    // ── Global: Deep scan a specific URL ──
    window.deepSearchUrl = async function(url) {
        if (!url) return;
        searchInput.value = url;
        // Force deep level
        levelSelector.value = 'deep';
        currentLevel = 'deep';
        executeSearch();
    };
});
