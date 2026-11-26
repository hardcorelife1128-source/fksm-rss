"""Unofficial HKBS RSS. Run only after source access is authorized.
Keeps the previous feed intact if downloading or parsing fails.
Article publication dates are omitted when the index does not supply them.
"""
from datetime import datetime, timezone
from email.utils import format_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, parse_qs
from urllib.request import Request, urlopen
import re
import time
import xml.etree.ElementTree as ET

SOURCE = "https://www.hkbs.co.kr/"
OUTPUT = Path("docs/hkbs.xml")


def article_id(href):
    url = urlsplit(urljoin(SOURCE, href))
    if url.scheme not in ("https", "http") or url.hostname not in ("hkbs.co.kr", "www.hkbs.co.kr"):
        return None
    value = parse_qs(url.query).get("idxno", [""])[0] if url.path == "/news/articleView.html" else ""
    return value if value.isdigit() else None


class Articles(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = {}
        self.current = None
        self.parts = []
        self.title_parts = []
        self.title_tag = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.current = article_id(attrs.get("href", ""))
            self.parts = []
            self.title_parts = []
            self.title_tag = None
        if self.current and "auto-titles" in attrs.get("class", "").split():
            self.title_tag = tag

    def handle_data(self, data):
        if self.current:
            self.parts.append(data)
            if self.title_tag:
                self.title_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current:
            title = " ".join(" ".join(self.title_parts or self.parts).split())
            if len(title) >= 6:
                previous = self.items.get(self.current)
                if previous is None or len(title) < len(previous):
                    self.items[self.current] = title
            self.current = None
        if tag == self.title_tag:
            self.title_tag = None


def download():
    for attempt in range(3):
        try:
            req = Request(SOURCE, headers={"User-Agent": "HKBS-RSS/1.0 (+https://github.com/hardcorelife1128-source/fksm-rss)"})
            with urlopen(req, timeout=30) as response:
                content = response.read(5_000_001)
                if len(content) > 5_000_000:
                    raise ValueError("Source page exceeds size limit")
                charset = response.headers.get_content_charset() or "utf-8"
                return content.decode(charset)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))


def build(html):
    parser = Articles()
    parser.feed(html)
    if len(parser.items) < 5:
        raise ValueError("Too few articles: previous feed retained; inspect source layout")
    items = {}
    if OUTPUT.exists():
        for item in ET.parse(OUTPUT).findall("./channel/item"):
            key = article_id(item.findtext("link", ""))
            if key and item.findtext("title", "") not in ("헤드라인 기사 이미지", "기사 썸네일", "기사이미지", "기사 이미지"):
                items[key] = item.findtext("title", "")
    items.update(parser.items)
    items = dict(sorted(items.items(), key=lambda pair: int(pair[0]), reverse=True)[:200])
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    for tag, value in {"title": "환경일보 (비공식 RSS)", "link": SOURCE, "description": "환경일보 홈페이지 기사 제목과 원문 링크. 공식 피드가 아닙니다.", "language": "ko", "ttl": "60"}.items():
        ET.SubElement(channel, tag).text = value
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(datetime.now(timezone.utc), usegmt=True)
    for key, title in items.items():
        item = ET.SubElement(channel, "item")
        link = SOURCE + "news/articleView.html?idxno=" + key
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = link
        ET.SubElement(item, "guid", isPermaLink="true").text = link
    ET.indent(rss)
    data = ET.tostring(rss, encoding="utf-8", xml_declaration=True)
    if len(ET.fromstring(data).findall("./channel/item")) < 5:
        raise ValueError("Invalid output")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_bytes(data)
    temporary.replace(OUTPUT)
    print(f"Generated {len(items)} articles")


if __name__ == "__main__":
    check = Articles()
    check.feed('<a href="/news/articleView.html?idxno=123"><img alt="기사 이미지"></a><a href="/news/articleView.html?idxno=123"><strong class="auto-titles">실제 기사 제목 확인</strong><p>본문 요약은 제외합니다</p></a>')
    assert check.items == {"123": "실제 기사 제목 확인"}, check.items
    assert article_id("https://example.com/news/articleView.html?idxno=123") is None
    assert article_id("/news/articleView.html?idxno=123") == "123"
    build(download())
