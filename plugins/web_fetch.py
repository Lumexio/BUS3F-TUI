"""Web fetch tool plugin for agent_team."""
import urllib.request
import re

def fetch_web(url: str = "") -> dict:
    """Fetch text documentation or reference content from a web URL."""
    if not url:
        return {"ok": False, "error": "url is required"}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text).strip()
            return {"ok": True, "url": url, "content": text[:4000]}
    except Exception as e:
        return {"ok": False, "error": str(e)}

TOOLS = {
    "fetch_web": fetch_web
}
