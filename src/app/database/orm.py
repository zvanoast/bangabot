from sqlalchemy import Column, String, Integer, DateTime, func

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


class UserMemory(Base):
    __tablename__ = 'user_memories'
    id = Column(Integer, primary_key=True)
    user_id = Column(String, index=True)
    user_name = Column(String)
    fact = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(),
                        onupdate=func.now())

    def __init__(self, user_id, user_name, fact):
        self.user_id = user_id
        self.user_name = user_name
        self.fact = fact


class BotMemory(Base):
    __tablename__ = 'bot_memories'
    id = Column(Integer, primary_key=True)
    category = Column(String, index=True)
    fact = Column(String)
    related_user_ids = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(),
                        onupdate=func.now())

    def __init__(self, category, fact, related_user_ids=None):
        self.category = category
        self.fact = fact
        self.related_user_ids = related_user_ids
