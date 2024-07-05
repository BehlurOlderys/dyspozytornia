pyinstaller -F --paths=venv\Lib\site-packages package\main.py --icon=4lufy.ico --noconsole --add-data package;.
copy config.json dist\config.json
copy 4lufy.ico dist\4lufy.ico