import os
import json
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker
from pymongo import MongoClient

# BASE_DIR = os.path.dirname(os.path.relpath("./"))
# secret_file = os.path.join(BASE_DIR, 'secret.json')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
secret_file = os.path.join(BASE_DIR, 'secret.json')

with open(secret_file) as f:
    secrets = json.loads(f.read())

def get_secret(setting, secrets=secrets):
    try:
        return secrets[setting]
    except KeyError:
        error_msg = "Set the {} environment variable".format(setting)
        raise ImproperlyConfigured(error_msg)

PORT = get_secret("MYSQL_PORT")
SQLUSERNAME = get_secret("MYSQL_USER_NAME")
SQLPASSWORD = get_secret("MYSQL_PASSWORD")
SQLDBNAME = get_secret("MYSQL_DB_NAME")
HOSTNAME = get_secret("MYSQL_HOST")
KAKAO_CLIENT_ID = get_secret("KAKAO_CLIENT_ID")
KAKAO_REDIRECT_URI = get_secret("KAKAO_REDIRECT_URI")
OPENAI_API_KEY = get_secret("OPENAI_API_KEY")
WEATHER_API_KEY = get_secret("WEATHER_API_KEY")
SERP_API_KEY = get_secret("SERP_API_KEY")
MongoDB_Hostname = get_secret("MongoDB_Hostname")
MongoDB_Username = get_secret("MongoDB_Username")
MongoDB_Password = get_secret("MongoDB_Password")
GEMINI_API_KEY = get_secret("GEMINI_API_KEY")

DB_URL = f'mysql+pymysql://{SQLUSERNAME}:{SQLPASSWORD}@{HOSTNAME}:{PORT}/{SQLDBNAME}'

class db_conn:
    def __init__(self):
        self.engine = create_engine(DB_URL, pool_recycle=500)

    def sessionmaker(self):
        Session = sessionmaker(bind=self.engine)
        session = Session()
        return session
    
    def connection(self):
        conn = self.engine.connection()
        return conn

sqldb = db_conn()

# Mongo 연결 설정
mongodb_url = f'mongodb://{MongoDB_Username}:{MongoDB_Password}@{MongoDB_Hostname}:27017/'
client = MongoClient(mongodb_url)
db = client['TripPass']