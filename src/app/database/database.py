import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path)

pw = os.getenv('DBUSER')
user = os.getenv('DBPASS')
host_name = os.getenv('DBHOST')
db_port = os.getenv('DBPORT')
db_name = os.getenv('DBNAME')
engine = create_engine("postgresql+psycopg2://{0}:{1}@{2}:{3}/{4}".format(pw,user,host_name,db_port,db_name))

Session = sessionmaker(bind=engine)
Base = declarative_base()