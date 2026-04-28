sed -i.bak 's/ctx.fillStyle = '\'#16161f\''/ctx.fillStyle = isDarkTheme() ? '\''#16161f'\'' : '\''#e0e0e0'\''/g' client/js/game.js
sed -i.bak 's/ctx.fillStyle = '\'#fff\''/ctx.fillStyle = getTextColor()/g' client/js/game.js
