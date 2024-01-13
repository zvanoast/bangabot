from sqlalchemy import Column, String, Integer, DateTime

from database.database import Base

class Link(Base):
    __tablename__ = 'links'
    id = Column(Integer, primary_key=True)
    url = Column(String)
    user = Column(String)
    channel = Column(String)
    date = Column(DateTime)
    jump_url = Column(String)

    def __init__(self, url, user, channel, date, jump_url):
        self.url = url
        self.user = user
        self.channel = channel
        self.date = date
        self.jump_url = jump_url

class LinkExclusion(Base):
    __tablename__ = 'link_exclusions'
    id = Column(Integer, primary_key=True)
    url = Column(String)

    def __init__(self, url):
        self.url = url

class StartupHistory(Base):
    __tablename__ = 'startup_history'
    id = Column(Integer, primary_key=True)
    date = Column(DateTime)

    def __init__(self, date):
        self.date = date


