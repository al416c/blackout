sed -i.bak -s 's/document.getElementById('\''auth-screen'\'').classList.toggle('\''inverted-theme'\'');/document.body.classList.toggle('\''dark-theme'\'');/g' client/js/main.js
sed -i.bak -s 's/document.getElementById('\''menu-screen'\'').classList.toggle('\''inverted-theme'\'');//g' client/js/main.js
