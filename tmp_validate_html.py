from html.parser import HTMLParser
from pathlib import Path
html = Path('client/index.html').read_text(encoding='utf-8')
parser = HTMLParser()
parser.feed(html)
print('parsed OK')
