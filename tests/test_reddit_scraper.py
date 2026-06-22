"""Tests for the Reddit intelligence scraper in core/blog_trends.py.

All external HTTP calls are mocked — no real Reddit requests are made.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from core.blog_trends import collect_reddit_sources, _score_reddit_post

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REDDIT_HOT_FIXTURE = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "GPT-5 outperforms all benchmarks in multi-modal reasoning tasks",
                    "selftext": "Detailed discussion about the benchmark results and what they mean for the field.",
                    "url": "https://www.reddit.com/r/MachineLearning/comments/abc123/gpt5_outperforms/",
                    "score": 1234,
                    "num_comments": 87,
                    "created_utc": 1718000000.0,
                    "subreddit": "MachineLearning",
                }
            },
            {
                "data": {
                    "title": "Weekly Discussion Thread",
                    "selftext": "",
                    "url": "https://www.reddit.com/r/MachineLearning/comments/def456/weekly/",
                    "score": 2,          # below threshold — should be filtered
                    "num_comments": 1,   # below threshold — should be filtered
                    "created_utc": 1718000100.0,
                    "subreddit": "MachineLearning",
                }
            },
            {
                "data": {
                    "title": "New open-source LLM beats Llama 3 on coding tasks with 7B parameters",
                    "selftext": "Released weights, code and paper today.",
                    "url": "https://github.com/example/model",
                    "score": 450,
                    "num_comments": 33,
                    "created_utc": 1718000200.0,
                    "subreddit": "MachineLearning",
                }
            },
        ]
    }
}

_GOOD_POST = {
    "title": "New open-source framework makes async Python 10x faster",
    "selftext": "Detailed explanation here with benchmarks and methodology.",
    "score": 500,
    "num_comments": 42,
}

_LOW_SCORE_POST = {
    "title": "Check this out if you have time",
    "selftext": "Some content",
    "score": 3,
    "num_comments": 5,
}

_LOW_COMMENTS_POST = {
    "title": "Interesting paper on transformer architectures for code generation",
    "selftext": "Really fascinating read from MIT labs",
    "score": 100,
    "num_comments": 1,
}

_EMPTY_SELFTEXT_SHORT_TITLE_POST = {
    "title": "Cool link",
    "selftext": "",
    "score": 50,
    "num_comments": 10,
}

_VALID_SHORT_TITLE_WITH_SELFTEXT = {
    "title": "Short",
    "selftext": "But has selftext so it passes the title-length check",
    "score": 50,
    "num_comments": 10,
}


def _make_ok_response(payload: dict) -> MagicMock:
    """Return a mock requests.Response for a successful JSON payload."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def _make_error_response(status_code: int) -> MagicMock:
    import requests

    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.raise_for_status.side_effect = requests.HTTPError(
        f"{status_code} Error", response=mock_resp
    )
    return mock_resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCollectRedditSources(unittest.TestCase):
    # ------------------------------------------------------------------
    # 1. Happy path — structure check
    # ------------------------------------------------------------------
    @patch("core.blog_trends.time.sleep")
    @patch("core.blog_trends.requests.get")
    def test_collect_reddit_sources_returns_list_on_success(self, mock_get, mock_sleep):
        mock_get.return_value = _make_ok_response(_REDDIT_HOT_FIXTURE)

        results = collect_reddit_sources(["MachineLearning"])

        self.assertIsInstance(results, list)
        # Only 2 posts pass the quality filter (score>=5, num_comments>=2,
        # and title-length / selftext rules).
        self.assertGreater(len(results), 0)

        first = results[0]
        # Required keys must be present
        for key in ("title", "url", "snippet", "source", "source_score",
                    "query", "rank", "checked_at", "domain"):
            self.assertIn(key, first, f"Missing key: {key}")

        self.assertEqual(first["source_score"], 45)
        self.assertIn("MachineLearning", first["source"])

    # ------------------------------------------------------------------
    # 2. Degrades gracefully on ConnectionError
    # ------------------------------------------------------------------
    @patch("core.blog_trends.time.sleep")
    @patch("core.blog_trends.requests.get", side_effect=ConnectionError("network down"))
    def test_collect_reddit_sources_degrades_on_http_error(self, mock_get, mock_sleep):
        results = collect_reddit_sources(["MachineLearning"])
        self.assertEqual(results, [])

    # ------------------------------------------------------------------
    # 3. Degrades gracefully on bad JSON
    # ------------------------------------------------------------------
    @patch("core.blog_trends.time.sleep")
    @patch("core.blog_trends.requests.get")
    def test_collect_reddit_sources_degrades_on_bad_json(self, mock_get, mock_sleep):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = json.JSONDecodeError("bad json", "", 0)

        mock_get.return_value = mock_resp
        results = collect_reddit_sources(["MachineLearning"])
        self.assertEqual(results, [])

    # ------------------------------------------------------------------
    # 4. Degrades gracefully on 404
    # ------------------------------------------------------------------
    @patch("core.blog_trends.time.sleep")
    @patch("core.blog_trends.requests.get")
    def test_collect_reddit_sources_degrades_on_404(self, mock_get, mock_sleep):
        mock_get.return_value = _make_error_response(404)
        results = collect_reddit_sources(["MachineLearning"])
        self.assertEqual(results, [])

    # ------------------------------------------------------------------
    # 5. Low-score posts are filtered out
    # ------------------------------------------------------------------
    @patch("core.blog_trends.time.sleep")
    @patch("core.blog_trends.requests.get")
    def test_low_score_posts_filtered(self, mock_get, mock_sleep):
        payload = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "High quality post about machine learning trends in 2024",
                            "selftext": "Very detailed body text.",
                            "url": "https://reddit.com/r/ML/comments/good/",
                            "score": 100,
                            "num_comments": 20,
                            "created_utc": 1718000000.0,
                            "subreddit": "MachineLearning",
                        }
                    },
                    {
                        "data": {
                            "title": "Throwaway low quality post with tiny score value",
                            "selftext": "Nothing notable.",
                            "url": "https://reddit.com/r/ML/comments/low/",
                            "score": 4,   # below threshold
                            "num_comments": 10,
                            "created_utc": 1718000000.0,
                            "subreddit": "MachineLearning",
                        }
                    },
                ]
            }
        }
        mock_get.return_value = _make_ok_response(payload)

        results = collect_reddit_sources(["MachineLearning"])
        urls = [r["url"] for r in results]
        self.assertIn("https://reddit.com/r/ML/comments/good/", urls)
        self.assertNotIn("https://reddit.com/r/ML/comments/low/", urls)

    # ------------------------------------------------------------------
    # 6. Rate-limit sleep is called between subreddits
    # ------------------------------------------------------------------
    @patch("core.blog_trends.time.sleep")
    @patch("core.blog_trends.requests.get")
    def test_rate_limit_sleep_called(self, mock_get, mock_sleep):
        mock_get.return_value = _make_ok_response(_REDDIT_HOT_FIXTURE)

        collect_reddit_sources(["MachineLearning", "programming"])

        # sleep(1) should be called once between the two subreddit requests
        mock_sleep.assert_any_call(1)

    # ------------------------------------------------------------------
    # 7. User-Agent header is sent
    # ------------------------------------------------------------------
    @patch("core.blog_trends.time.sleep")
    @patch("core.blog_trends.requests.get")
    def test_user_agent_header_sent(self, mock_get, mock_sleep):
        mock_get.return_value = _make_ok_response(_REDDIT_HOT_FIXTURE)

        collect_reddit_sources(["MachineLearning"])

        self.assertTrue(mock_get.called)
        _, kwargs = mock_get.call_args
        headers = kwargs.get("headers", {})
        self.assertEqual(headers.get("User-Agent"), "ThinkVelocity-Intel/1.0")

    # ------------------------------------------------------------------
    # 8. Empty subreddit list returns empty list immediately
    # ------------------------------------------------------------------
    @patch("core.blog_trends.time.sleep")
    @patch("core.blog_trends.requests.get")
    def test_empty_subreddit_list_returns_empty(self, mock_get, mock_sleep):
        results = collect_reddit_sources([])
        self.assertEqual(results, [])
        mock_get.assert_not_called()
        mock_sleep.assert_not_called()

    # ------------------------------------------------------------------
    # 9. One failing subreddit does not stop the others
    # ------------------------------------------------------------------
    @patch("core.blog_trends.time.sleep")
    @patch("core.blog_trends.requests.get")
    def test_one_failing_subreddit_does_not_stop_others(self, mock_get, mock_sleep):
        subreddits = [
            "MachineLearning",
            "programming",
            "SideProject",
            "AIAssistants",
            "artificial",
            "productivity",
            "learnprogramming",
        ]

        ok_response = _make_ok_response(_REDDIT_HOT_FIXTURE)

        # First call raises ConnectionError; remaining 6 succeed.
        mock_get.side_effect = [ConnectionError("fail")] + [ok_response] * 6

        results = collect_reddit_sources(subreddits)

        # 7 total requests attempted
        self.assertEqual(mock_get.call_count, 7)
        # Results come from the 6 successful subreddits
        self.assertGreater(len(results), 0)


# ---------------------------------------------------------------------------
# Tests for _score_reddit_post helper
# ---------------------------------------------------------------------------


class TestScoreRedditPost(unittest.TestCase):
    def test_good_post_returns_nonzero_score(self):
        score = _score_reddit_post(_GOOD_POST)
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_low_score_post_returns_zero(self):
        result = _score_reddit_post(_LOW_SCORE_POST)
        self.assertEqual(result, 0.0)

    def test_low_comments_post_returns_zero(self):
        result = _score_reddit_post(_LOW_COMMENTS_POST)
        self.assertEqual(result, 0.0)

    def test_empty_selftext_short_title_returns_zero(self):
        result = _score_reddit_post(_EMPTY_SELFTEXT_SHORT_TITLE_POST)
        self.assertEqual(result, 0.0)

    def test_short_title_with_selftext_is_not_filtered(self):
        """A short title is acceptable when selftext provides content."""
        result = _score_reddit_post(_VALID_SHORT_TITLE_WITH_SELFTEXT)
        self.assertGreater(result, 0.0)

    def test_score_is_normalised_between_0_and_1(self):
        """Regardless of how high the reddit score/num_comments are, output is [0, 1]."""
        big_post = {**_GOOD_POST, "score": 999_999, "num_comments": 50_000}
        result = _score_reddit_post(big_post)
        self.assertGreaterEqual(result, 0.0)
        self.assertLessEqual(result, 1.0)


if __name__ == "__main__":
    unittest.main()
