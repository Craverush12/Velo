from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage.blog_store import get_default_blog_store


def main() -> int:
    load_dotenv()
    slug = sys.argv[1] if len(sys.argv) > 1 else "thinkvelocity-ai-seo-geo-audit-agent"
    store = get_default_blog_store()
    posts = store.list_posts(search=slug, page_size=1)["items"]
    if not posts:
        print(json.dumps({"status": "missing", "slug": slug}, indent=2))
        return 1
    post = posts[0]
    payload = {
        "status": "found",
        "route": f"/admin/api/blog-posts/{post['id']}/seo-audit",
        "post_id": post["id"],
        "slug": post["slug"],
        "post_status": post["status"],
        "quality_score": post.get("quality_score", 0),
        "seo_score": post.get("seo_score", 0),
        "geo_score": post.get("geo_score", 0),
        "eeat_score": post.get("eeat_score", 0),
        "schema_types": [node.get("@type") for node in post.get("schema_jsonld", {}).get("@graph", [])],
        "missing_items": post.get("seo_audit", {}).get("missing_items", []),
        "recommendations": post.get("seo_audit", {}).get("recommendations", []),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
