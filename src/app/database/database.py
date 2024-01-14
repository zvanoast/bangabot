import os
import time
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path)

user = os.getenv('DBUSER')
pw = os.getenv('DBPASS')
host_name = os.getenv('DBHOST')
db_port = os.getenv('DBPORT')
db_name = os.getenv('DBNAME')

#use psycopg2 to connect to postgresql, check if the DB exists, and create it if it doesn't
#make sure the postgres container has had time to initialize
time_limit = 30
start_time = time.time()
pg_init = False

while time.time() < start_time + time_limit:
    try:
        conn = psycopg2.connect(user=user, password=pw, host=host_name, port=db_port)
        conn.close()
        print("Postgresql container initialized.")
        pg_init = True
        break
    except psycopg2.OperationalError:
        time.sleep(1)
    print("Waiting for postgresql container to initialize...")

if not pg_init:
    print("Postgresql container failed to initialize.")
    exit(1)

conn = psycopg2.connect(user=user, password=pw, host=host_name, port=db_port)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

with conn.cursor() as cursor:
    cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'")
    exists = cursor.fetchone()
    if not exists:
        cursor.execute(f"CREATE DATABASE {db_name} WITH ENCODING='utf8' TEMPLATE=template0")
conn.close()

#now connect with SQLAlchemy and create tables
connection_string = "postgresql://{0}:{1}@{2}:{3}/{4}".format(user,pw,host_name,db_port,db_name)
print("Connection string: " + connection_string)
engine = create_engine(connection_string)

Session = sessionmaker(bind=engine)
Base = declarative_base()