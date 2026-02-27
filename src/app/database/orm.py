from sqlalchemy import Column, String, Integer, Float, DateTime, func

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    # Fallback: Vector columns will be raw — managed by migration SQL
    Vector = None

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
    importance = Column(Integer, default=2)
    embedding = Column(
        Vector(384) if Vector else String, nullable=True
    )
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(),
                        onupdate=func.now())

    def __init__(self, user_id, user_name, fact, importance=2):
        self.user_id = user_id
        self.user_name = user_name
        self.fact = fact
        self.importance = importance


class BotMemory(Base):
    __tablename__ = 'bot_memories'
    id = Column(Integer, primary_key=True)
    category = Column(String, index=True)
    fact = Column(String)
    importance = Column(Integer, default=2)
    embedding = Column(
        Vector(384) if Vector else String, nullable=True
    )
    related_user_ids = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(),
                        onupdate=func.now())

    def __init__(self, category, fact, related_user_ids=None,
                 importance=2):
        self.category = category
        self.fact = fact
        self.related_user_ids = related_user_ids
        self.importance = importance


class UserSentiment(Base):
    __tablename__ = 'user_sentiments'
    id = Column(Integer, primary_key=True)
    user_id = Column(String, unique=True, index=True)
    user_name = Column(String)
    score = Column(Float, default=0.0)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(),
                        onupdate=func.now())

    def __init__(self, user_id, user_name, score=0.0, reason=None):
        self.user_id = user_id
        self.user_name = user_name
        self.score = score
        self.reason = reason


class EpisodicSummary(Base):
    __tablename__ = 'episodic_summaries'
    id = Column(Integer, primary_key=True)
    channel_id = Column(String, index=True)
    summary = Column(String)
    participant_ids = Column(String, nullable=True)
    message_count = Column(Integer)
    started_at = Column(DateTime)
    ended_at = Column(DateTime)
    embedding = Column(
        Vector(384) if Vector else String, nullable=True
    )
    created_at = Column(DateTime, server_default=func.now())

    def __init__(self, channel_id, summary, participant_ids=None,
                 message_count=0, started_at=None,
                 ended_at=None):
        self.channel_id = channel_id
        self.summary = summary
        self.participant_ids = participant_ids
        self.message_count = message_count
        self.started_at = started_at
        self.ended_at = ended_at
