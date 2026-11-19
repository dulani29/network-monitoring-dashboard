"""Entry point:  python run.py"""
from app import create_app
from config import Config

app = create_app(Config)

if __name__ == "__main__":
    # use_reloader=False so the background monitor thread is only started once.
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG, use_reloader=False)
