"""Unofficial FKSM RSS. Run only after source access is authorized.
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

SOURCE = "https://fksm.co.kr/"
OUTPUT = Path("docs/feed.xml")


def article_id(href):
    url = urlsplit(urljoin(SOURCE, href))
    if url.scheme not in ("https", "http") or url.hostname not in ("fksm.co.kr", "www.fksm.co.kr"):
        return None
    match = re.fullmatch(r"/news/(\d+)/?", url.path)
    value = match.group(1) if match else parse_qs(url.query).get("idx", [""])[0] if url.path == "/news/view.php" else ""
    return value if value.isdigit() else None


class Articles(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = {}
        self.current = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.current = article_id(attrs.get("href", ""))
            self.parts = [attrs.get("title", "")]
        elif tag == "img" and self.current:
            self.parts.append(attrs.get("alt", ""))

    def handle_data(self, data):
        if self.current:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current:
            title = " ".join(" ".join(self.parts).split())
            if len(title) >= 6 and self.current not in self.items:
                self.items[self.current] = title
            self.current = None
            self.parts = []


def download():
    for attempt in range(3):
        try:
            req = Request(SOURCE, headers={"User-Agent": "FKSM-RSS/1.0 (+https://github.com/hardcorelife1128-source/fksm-rss)"})
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
            if key:
                items[key] = item.findtext("title", "")
    items.update(parser.items)
    items = dict(sorted(items.items(), key=lambda pair: int(pair[0]), reverse=True)[:200])
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    for tag, value in {"title": "환경신문 (비공식 RSS)", "link": SOURCE, "description": "환경신문 홈페이지 기사 제목과 원문 링크. 공식 피드가 아닙니다.", "language": "ko", "ttl": "60"}.items():
        ET.SubElement(channel, tag).text = value
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(datetime.now(timezone.utc), usegmt=True)
    for key, title in items.items():
        item = ET.SubElement(channel, "item")
        link = SOURCE + "news/" + key
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
    build(download())
