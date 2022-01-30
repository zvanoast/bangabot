import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

user = os.getenv('DBPASS')
pw = os.getenv('DBUSER')
engine = create_engine("postgresql://{0}:{1}@localhost:5432/banga".format(pw,user))

Session = sessionmaker(bind=engine)
Base = declarative_base()