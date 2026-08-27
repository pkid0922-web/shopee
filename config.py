import os


def _normalize_db_url(url: str) -> str:
    """Railway / Heroku 給的 DATABASE_URL 常是 postgres://，
    SQLAlchemy 1.4+ 需要 postgresql://，這裡自動轉換。"""
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    _database_url = os.environ.get("DATABASE_URL")
    if _database_url:
        SQLALCHEMY_DATABASE_URI = _normalize_db_url(_database_url)
    else:
        # 本機開發沒設 DATABASE_URL 時，退回本機 SQLite，方便先跑起來
        _basedir = os.path.abspath(os.path.dirname(__file__))
        _instance_dir = os.path.join(_basedir, "instance")
        os.makedirs(_instance_dir, exist_ok=True)
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(_instance_dir, "dev.db")

    SQLALCHEMY_TRACK_MODIFICATIONS = False
