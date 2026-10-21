"""Troubleshooting content used by the API for real, auditable retrieval."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeArticle:
    title: str
    category: str
    intro: str
    steps: tuple[str, ...]


ARTICLES = (
    KnowledgeArticle(
        title="Troubleshoot a dropped VPN connection",
        category="Network",
        intro="Restore a stable remote connection with a few quick checks.",
        steps=(
            "Confirm your internet connection is stable without the VPN.",
            "Disconnect and reconnect to the nearest approved gateway.",
            "Restart the VPN client and check for pending updates.",
            "If disconnects continue, note the time and your network type before contacting IT.",
        ),
    ),
    KnowledgeArticle(
        title="Connect to campus Wi-Fi",
        category="Network",
        intro="Set up your device on the secure campus network.",
        steps=(
            "Select the college's verified secure Wi-Fi network; confirm its exact name with official campus IT if you are unsure.",
            "Sign in with your college account. Verify any certificate details against official campus IT instructions, and do not accept an unexpected or unverified certificate warning.",
            "Forget older saved campus networks if authentication fails.",
            "If a certificate warning remains unclear, stop and contact campus IT using independently verified contact information before connecting.",
            "Restart Wi-Fi and try again near an access point after the network and certificate are verified.",
        ),
    ),
    KnowledgeArticle(
        title="Request access to a shared drive",
        category="Access",
        intro="Get the right permissions for shared team files.",
        steps=(
            "Connect to the campus network or approved VPN.",
            "Confirm you are signed in with your college account.",
            "Ask the folder owner to confirm your group membership.",
            "Create a ticket with the drive path if access is still denied.",
        ),
    ),
    KnowledgeArticle(
        title="Improve a slow computer",
        category="Hardware",
        intro="Try these safe steps before requesting device support.",
        steps=(
            "Restart your computer to finish pending updates.",
            "Close apps and browser tabs you are not using.",
            "Check available storage and remove unneeded downloads.",
            "Record the apps affected if slowness continues.",
        ),
    ),
    KnowledgeArticle(
        title="Set up your authenticator on a new phone",
        category="Account",
        intro="Regain secure access after changing devices.",
        steps=(
            "Keep your previous device available if you still have it.",
            "Open the account security page on a trusted browser.",
            "Choose Add sign-in method and follow the authenticator prompts.",
            "Contact IT for identity verification if you are locked out.",
        ),
    ),
    KnowledgeArticle(
        title="Refresh desktop email sync",
        category="Software",
        intro="Check common causes of delayed email updates.",
        steps=(
            "Confirm the desktop client is online.",
            "Use Sync or Refresh to request new messages.",
            "Restart the mail client and check for updates.",
            "Use webmail temporarily if the delay continues.",
        ),
    ),
)

_STOP_WORDS = {
    "a", "about", "after", "an", "and", "are", "as", "at", "be", "but", "by", "can", "could",
    "do", "for", "from", "have", "help", "how", "i", "if", "in", "is", "it", "my", "of", "on",
    "or", "please", "problem", "since", "that", "the", "this", "to", "up", "was", "what", "when",
    "with", "would", "campus",
}

_CATEGORY_SIGNALS = {
    "Network": {"wifi", "internet", "network", "vpn", "dns", "connection", "connect", "disconnect", "wireless", "signal", "router"},
    "Account": {"account", "password", "signin", "login", "authenticator", "mfa", "locked"},
    "Hardware": {"computer", "laptop", "desktop", "device", "hardware", "fan", "storage", "keyboard", "screen"},
    "Software": {"software", "email", "mail", "sync", "application", "app", "update"},
    "Access": {"access", "drive", "shared", "permission", "folder", "file"},
}


def _terms(text: str) -> set[str]:
    normalized = re.sub(r"wi[\s-]?fi", "wifi", text.casefold())
    return {term for term in re.findall(r"[a-z0-9]+", normalized) if len(term) > 1 and term not in _STOP_WORDS}


def retrieve_articles(issue: str, limit: int = 3) -> list[KnowledgeArticle]:
    """Rank lexical matches by title and issue-category relevance; omit weak incidental matches."""
    issue_terms = _terms(issue)
    if not issue_terms or limit <= 0:
        return []

    likely_categories = {
        category for category, signals in _CATEGORY_SIGNALS.items()
        if issue_terms & signals
    }
    ranked: list[tuple[float, int, KnowledgeArticle]] = []
    for index, article in enumerate(ARTICLES):
        title_terms = _terms(article.title)
        category_terms = _terms(article.category)
        body_terms = _terms(" ".join((article.intro, *article.steps)))
        title_matches = issue_terms & title_terms
        category_matches = issue_terms & category_terms
        body_matches = issue_terms & body_terms
        if not (title_matches or category_matches or body_matches):
            continue

        # Article titles carry stronger topical intent than incidental mentions in steps.
        score = len(title_matches) * 3.0 + len(category_matches) * 1.5 + len(body_matches) * 0.7
        if article.category in likely_categories:
            score += 2.5
        ranked.append((score, -index, article))

    ranked.sort(reverse=True, key=lambda row: (row[0], row[1]))
    if not ranked:
        return []

    # Drop weak one-word matches when a much stronger topical article exists.
    relevance_floor = ranked[0][0] * 0.55
    return [article for score, _, article in ranked if score >= relevance_floor][:limit]
