"""
SearchLevelClassifier — Shinobu's search decision brain.

Classifies user intent into one of three search levels:
  🟢 FAST  — open browser, redirect (instant action)
  🟡 MID   — headless browsing, collect results (controlled)
  🔵 DEEP  — scrape, extract, analyze (understanding)

Strategy:
  1. Rule-based heuristics FIRST (zero LLM cost for obvious cases)
  2. LLM fallback for ambiguous queries
"""

import re
import json
import logging
from typing import Optional, Dict, Any
from phoenix.framework.agent.core.profile import AgentProfile
from ..core.prompts import build_search_classifier_prompt

logger = logging.getLogger("shinobu.brains.search_classifier")


class SearchLevel:
    """Search level constants with metadata."""
    FAST = "fast"
    MID  = "mid"
    DEEP = "deep"

    @staticmethod
    def describe(level: str) -> str:
        return {
            "fast": "🟢 Fast Search — open browser instantly",
            "mid":  "🟡 Mid Search — controlled headless browsing",
            "deep": "🔵 Deep Search — scrape + extract + analyze",
        }.get(level, "Unknown level")


# ─────────────────────────────────────────────────────────────────────────────
# Rule-Based Pattern Sets
# ─────────────────────────────────────────────────────────────────────────────

# Fast: simple open/launch actions
_FAST_PATTERNS = [
    r"\bopen\b",
    r"\bgo\s+to\b",
    r"\blaunch\b",
    r"\bplay\b",
    r"\bwatch\b",
    r"\bvisit\b",
    r"\bnavigate\s+to\b",
    r"\bshow\s+me\b.*\b(site|page|website)\b",
]

# Deep: thinking / research / understanding actions
_DEEP_PATTERNS = [
    r"\bexplain\b",
    r"\bresearch\b",
    r"\bsummarize\b",
    r"\bsummary\b",
    r"\bcompare\b",
    r"\banalyze\b",
    r"\banalysis\b",
    r"\bwhat\s+is\b",
    r"\bwhat\s+are\b",
    r"\bhow\s+does\b",
    r"\bhow\s+do\b",
    r"\bhow\s+to\b",
    r"\bwhy\s+(is|does|do|are)\b",
    r"\bin\s+depth\b",
    r"\bdetailed\b",
    r"\bpros\s+and\s+cons\b",
    r"\bdifference\s+between\b",
    r"\btell\s+me\s+about\b",
    r"\blearn\s+about\b",
]

# Direct URL or known site → always FAST
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
_KNOWN_SITES = {
    "youtube", "netflix", "github", "twitter", "x", "reddit",
    "google", "spotify", "wikipedia", "amazon", "facebook",
    "instagram", "linkedin", "twitch", "stackoverflow",
}

# Compile patterns
_FAST_RE = [re.compile(p, re.IGNORECASE) for p in _FAST_PATTERNS]
_DEEP_RE = [re.compile(p, re.IGNORECASE) for p in _DEEP_PATTERNS]


# ─────────────────────────────────────────────────────────────────────────────
# Classifier
# ─────────────────────────────────────────────────────────────────────────────

class SearchLevelClassifier:
    """
    Brain: Classifies search-related user intent into fast/mid/deep.
    Uses rule-based heuristics first, LLM fallback for ambiguous cases.
    LLM: YES (fallback only)
    """

    def __init__(self, llm, profile: Optional[AgentProfile] = None):
        self.llm = llm
        self.profile = profile

    async def classify(
        self,
        user_input: str,
        intent: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Classify a user's search request into a search level.

        Args:
            user_input: raw user text
            intent: optional pre-parsed intent from IntentInterpreter

        Returns:
            {
                "level": "fast" | "mid" | "deep",
                "confidence": "rule" | "llm",
                "reason": str,
                "query": str  (cleaned search query)
            }
        """
        text = user_input.strip().lower()

        # ── Rule 1: Direct URL → FAST ──
        if _URL_PATTERN.search(user_input):
            url_match = _URL_PATTERN.search(user_input)
            return {
                "level": SearchLevel.FAST,
                "confidence": "rule",
                "reason": "Direct URL detected",
                "query": url_match.group(0),
            }

        # ── Rule 2: Known site name → FAST ──
        words = set(text.split())
        site_match = words & _KNOWN_SITES
        if site_match and any(r.search(text) for r in _FAST_RE):
            return {
                "level": SearchLevel.FAST,
                "confidence": "rule",
                "reason": f"Known site '{next(iter(site_match))}' with open action",
                "query": user_input,
            }

        # ── Rule 3: Strong DEEP patterns ──
        deep_hits = sum(1 for r in _DEEP_RE if r.search(text))
        if deep_hits >= 2:
            return {
                "level": SearchLevel.DEEP,
                "confidence": "rule",
                "reason": f"Multiple deep-research patterns detected ({deep_hits} matches)",
                "query": user_input,
            }

        # ── Rule 4: Strong FAST patterns (without deep patterns) ──
        fast_hits = sum(1 for r in _FAST_RE if r.search(text))
        if fast_hits >= 1 and deep_hits == 0:
            # Check if it's truly a simple open action vs a search
            if site_match or _URL_PATTERN.search(user_input):
                return {
                    "level": SearchLevel.FAST,
                    "confidence": "rule",
                    "reason": "Open/launch action with target",
                    "query": user_input,
                }

        # ── Rule 5: Single deep pattern → likely DEEP ──
        if deep_hits == 1:
            return {
                "level": SearchLevel.DEEP,
                "confidence": "rule",
                "reason": "Research/understanding pattern detected",
                "query": user_input,
            }

        # ── Rule 6: Simple short query with "search" or "find" → MID ──
        if re.search(r"\b(search|find|look\s+up|look\s+for)\b", text, re.IGNORECASE):
            return {
                "level": SearchLevel.MID,
                "confidence": "rule",
                "reason": "Search/find action detected",
                "query": user_input,
            }

        # ── Rule 7: Fast patterns present → FAST ──
        if fast_hits >= 1:
            return {
                "level": SearchLevel.FAST,
                "confidence": "rule",
                "reason": "Open/launch action detected",
                "query": user_input,
            }

        # ── Ambiguous → LLM fallback ──
        return await self._classify_with_llm(user_input, intent)

    async def _classify_with_llm(
        self,
        user_input: str,
        intent: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Use LLM to classify ambiguous search intent."""
        try:
            prompt = build_search_classifier_prompt(user_input, intent)
            raw = await self.llm.generate(prompt, session_id=None, max_tokens=150)

            # Parse LLM response
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                level = data.get("level", "mid").lower()
                if level not in (SearchLevel.FAST, SearchLevel.MID, SearchLevel.DEEP):
                    level = SearchLevel.MID
                return {
                    "level": level,
                    "confidence": "llm",
                    "reason": data.get("reason", "LLM classification"),
                    "query": data.get("query", user_input),
                }
        except Exception as e:
            logger.warning(f"LLM classification failed: {e}")

        # Ultimate fallback → MID (safest default)
        return {
            "level": SearchLevel.MID,
            "confidence": "fallback",
            "reason": "LLM classification failed, defaulting to Mid Search",
            "query": user_input,
        }
