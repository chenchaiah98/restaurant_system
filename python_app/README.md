Temple Restaurant App (Flask)

This is a minimal local implementation of the flow in your diagram: a static menu UI that submits orders to a backend and a kitchen view that shows incoming orders.

Quick start (Windows PowerShell):

```powershell
cd "c:\Users\CHENC\OneDrive\Desktop\hostel\temple_restaurant_app\python_app"
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
# open http://localhost:5000 for the menu, and http://localhost:5000/kitchen for the kitchen view
```

What it includes:

- `app.py` - Flask backend, SQLite storage, API endpoints
- `templates/` - `index.html` (menu), `kitchen.html` (kitchen tablet)
- `static/` - CSS and JS used by the UI

Notes:

- Orders are stored in `python_app/data.db` (SQLite). To reset, delete that file and restart the app.
- For production deployment you'd replace SQLite with a hosted DB and use WebSockets or push notifications for real-time updates.
