import os
import time
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Try multiple possible dotenv paths to increase reliability
possible_paths = [
    os.path.join(os.path.dirname(__file__), '..', '.env'),
    os.path.join(os.getcwd(), '.env'),
    '.env'
]

for dotenv_path in possible_paths:
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        break

user = os.getenv('DBUSER')
pw = os.getenv('DBPASS')
host_name = os.getenv('DBHOST')
db_port = os.getenv('DBPORT')
db_name = os.getenv('DBNAME')

# Wait for PostgreSQL to be ready
def wait_for_postgres(retries=30, delay=2):
    print(f"Waiting for PostgreSQL at {host_name}:{db_port}...")
    
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(
                user=user, 
                password=pw, 
                host=host_name, 
                port=db_port
            )
            conn.close()
            print(f"PostgreSQL connection successful!")
            return True
        except psycopg2.OperationalError as e:
            if attempt < retries:
                time.sleep(delay)
            else:
                print(f"Failed to connect after {retries} attempts: {e}")
                return False

# Wait for PostgreSQL to be available
if not wait_for_postgres():
    print("Could not connect to PostgreSQL. Continuing anyway...")

# Create database if it doesn't exist
try:
    conn = psycopg2.connect(
        user=user, 
        password=pw, 
        host=host_name, 
        port=db_port
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    with conn.cursor() as cursor:
        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'")
        exists = cursor.fetchone()
        if not exists:
            print(f"Creating database '{db_name}'...")
            cursor.execute(f"CREATE DATABASE {db_name} WITH ENCODING='utf8' TEMPLATE=template0")
        else:
            print(f"Database '{db_name}' already exists.")
    conn.close()
except Exception as e:
    print(f"Error when trying to create database: {e}")

# Connect with SQLAlchemy
connection_string = "postgresql://{0}:{1}@{2}:{3}/{4}".format(user,pw,host_name,db_port,db_name)
print("Connection string: " + connection_string.replace(pw, '*****'))

try:
    # Create engine with connection retry
    engine = create_engine(
        connection_string,
        pool_pre_ping=True,
        pool_recycle=3600,
        connect_args={"connect_timeout": 10}
    )
    
    Session = sessionmaker(bind=engine)
    Base = declarative_base()
    
except Exception as e:
    print(f"Failed to create SQLAlchemy engine: {e}")
    # Still create these so the application can at least start
    engine = None
    Session = sessionmaker()
    Base = declarative_base()