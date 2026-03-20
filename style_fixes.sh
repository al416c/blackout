cat << 'CSS_EOF' >> client/css/style.css
/* Toggles & Resets */
.dark-theme #theme-toggle { color: #aaa; }
.dark-theme #theme-toggle:hover { color: #fff; border-color:#fff;}
#theme-toggle { color: #444; border: 1px solid transparent; }
#theme-toggle:hover { color: #000; border-color:#000; }
body { transition: background 0.3s, color 0.3s; }
.screen { background: inherit; }
CSS_EOF
