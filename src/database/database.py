import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

user = os.getenv('DBPASS')
pw = os.getenv('DBUSER')
host_name = os.getenv('DBHOST')
db_name = os.getenv('DBNAME')
engine = create_engine("postgresql://{0}:{1}@{2}:5432/{3}".format(pw,user,host_name,db_name))

Session = sessionmaker(bind=engine)
Base = declarative_base()