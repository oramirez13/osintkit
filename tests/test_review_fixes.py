import httpx

from osintkit.browser import BrowserFetcher
from osintkit.cli import cmd_report
from osintkit.config import Settings
from osintkit.http import Fetcher
from osintkit.modules.crawl import CrawlConfig, crawl
from osintkit.modules.detect import detect_type
from osintkit.storage import Recorder


def _fetcher_with_transport(handler, settings=None):
    fetcher = Fetcher(settings or Settings(delay=0, retries=0, respect_robots=False))
    fetcher._client.close()
    fetcher._client = httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )
    return fetcher


def test_fetcher_blocks_redirect_outside_allowed_hosts():
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://outside.example/path"})

    fetcher = _fetcher_with_transport(handler)
    try:
        response = fetcher.get(
            "https://start.example/", allowed_hosts={"start.example"}
        )
    finally:
        fetcher.close()

    assert response.status == 0
    assert response.headers["error"] == "redirect outside allowed hosts"
    assert requested == ["https://start.example/"]


def test_fetcher_limits_body_while_reading_response():
    fetcher = _fetcher_with_transport(
        lambda request: httpx.Response(200, content=b"abcdefghij"),
        Settings(delay=0, retries=0, respect_robots=False, max_bytes=4),
    )
    try:
        response = fetcher.get("https://example.test/")
    finally:
        fetcher.close()

    assert response.text == "abcd"


def test_csv_export_sanitizes_formula_cells(tmp_path):
    recorder = Recorder(str(tmp_path))
    recorder.add(**{"=formula": "  =1+1"})

    csv_path = recorder.save_csv()

    assert csv_path is not None
    csv_content = open(csv_path, encoding="utf-8").read()
    assert "'=formula" in csv_content
    assert "'  =1+1" in csv_content


def test_report_title_cannot_escape_output_directory(tmp_path, monkeypatch):
    input_path = tmp_path / "records.jsonl"
    input_path.write_text('{"title":"test"}\n', encoding="utf-8")
    output_dir = tmp_path / "reports"
    captured = {}

    def capture_report(records, path, **kwargs):
        captured["path"] = path
        return path

    monkeypatch.setattr("osintkit.cli.write_report", capture_report)
    args = type(
        "Args",
        (),
        {
            "input": str(input_path),
            "title": "../../outside",
            "out": None,
            "output": str(output_dir),
            "subtitle": None,
        },
    )()

    cmd_report(args)

    assert captured["path"] == str(output_dir / "outside.html")


def test_crawler_uses_same_agent_for_robots_and_page_requests():
    class FakeFetcher:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return type(
                "Response",
                (),
                {
                    "ok": True,
                    "status": 200,
                    "url": url,
                    "text": "<html></html>",
                    "headers": {"content-type": "text/html"},
                },
            )()

    fetcher = FakeFetcher()
    config = CrawlConfig(
        start_url="https://start.example/",
        max_depth=0,
        user_agent="crawler-test/1.0",
    )

    crawl(fetcher, config)

    assert fetcher.calls[0][1]["user_agent"] == "crawler-test/1.0"
    assert fetcher.calls[1][1]["user_agent"] == "crawler-test/1.0"
    assert fetcher.calls[1][1]["allowed_hosts"] == {"start.example"}
    assert fetcher.calls[0][1]["allowed_hosts"] == {"start.example"}


def test_browser_fetcher_blocks_disallowed_url_before_navigation():
    fetcher = object.__new__(BrowserFetcher)
    fetcher.settings = Settings(respect_robots=True)
    fetcher._deadline = None
    fetcher._robots_fetcher = type(
        "RobotsFetcher", (), {"robots_allowed": lambda *args, **kwargs: False}
    )()

    result = fetcher.get("https://blocked.example/")

    assert result.status == 0
    assert "blocked by robots.txt" in result.text


def test_eight_digit_numeric_value_is_detected_as_phone():
    assert detect_type("12345678") == "phone"


def test_nine_digit_numeric_value_remains_an_id():
    assert detect_type("123456789") == "id"


def test_formatted_short_phone_is_detected_as_phone():
    assert detect_type("123-4567") == "phone"
