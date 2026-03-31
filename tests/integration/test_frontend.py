"""Integration tests for the frontend.

Checks that the built React app is served correctly and its static assets load.
Does not require a browser — uses HTTP-level checks only.
"""

import re


EXPECTED_TITLE = "Six Degrees"
EXPECTED_ROOT_ID = "root"


class TestFrontendPage:
    def test_root_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_content_type_is_html(self, client):
        assert "text/html" in client.get("/").headers.get("content-type", "")

    def test_page_has_expected_title(self, client):
        assert EXPECTED_TITLE in client.get("/").text

    def test_page_has_react_root_element(self, client):
        assert f'id="{EXPECTED_ROOT_ID}"' in client.get("/").text


class TestStaticAssets:
    def test_linked_js_and_css_assets_return_200(self, client):
        html = client.get("/").text
        urls = re.findall(r'<script[^>]+src="(/[^"]+)"', html)
        urls += re.findall(r'<link[^>]+href="(/assets/[^"]+)"', html)
        assert len(urls) > 0, "No JS/CSS assets found in page — is this the built app?"
        for url in urls:
            assert client.get(url).status_code == 200, f"Asset {url} returned non-200"

    def test_js_bundle_is_nonempty(self, client):
        html = client.get("/").text
        js_urls = re.findall(r'<script[^>]+src="(/assets/[^"]+\.js)"', html)
        assert len(js_urls) > 0, "No JS bundle found in page"
        for url in js_urls:
            content = client.get(url).content
            assert len(content) > 1000, f"JS bundle at {url} looks too small ({len(content)} bytes)"
