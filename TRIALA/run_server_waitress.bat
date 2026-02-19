@echo off
cd /d C:\Users\MEDDY\Desktop\TRIALA
"C:\Users\MEDDY\AppData\Local\Programs\Python\Python313\python.exe" -c "from waitress import serve; from web_app import app; serve(app, host='0.0.0.0', port=5000)" >> server_waitress.log 2>&1
