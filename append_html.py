with open("client/index.html", "r") as f:
    html = f.read()

import re
html = re.sub(r'👑', r'<img src="img/icons/leaderboard.png" class="menu-icon" alt="">', html)
html = re.sub(r'🏆', '', html)
html = re.sub(r'📡', r'<img src="img/icons/transmission.png" class="menu-icon" alt="T">', html)
html = re.sub(r'💀', r'<img src="img/icons/symptoms.png" class="menu-icon" alt="S">', html)
html = re.sub(r'🛡️', r'<img src="img/icons/capacities.png" class="menu-icon" alt="C">', html)
html = re.sub(r'🦠', '', html)
html = re.sub(r'😈', '', html)
html = re.sub(r'💻', '', html)
html = re.sub(r'🕸️', '', html)
html = re.sub(r'🌐', '', html)
html = re.sub(r'🚪', '', html)

with open("client/index.html", "w") as f:
    f.write(html)
