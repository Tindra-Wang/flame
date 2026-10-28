"""Small persistent application repository, PostgreSQL in Compose, SQLite locally."""
import os
import time
from pathlib import Path
from sqlalchemy import create_engine, String, Text, Float, JSON, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

ROOT=Path(os.getenv('AI07_ROOT',Path(__file__).resolve().parents[1])).resolve()
STATE=ROOT/'.cache/platform'; STATE.mkdir(parents=True,exist_ok=True)
URL=os.getenv('AI07_DATABASE_URL','sqlite:///'+(STATE/'platform.db').as_posix())
engine=create_engine(URL,connect_args={'check_same_thread':False,'timeout':30} if URL.startswith('sqlite:') else {},pool_pre_ping=True)
Session=sessionmaker(engine,expire_on_commit=False)

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__='web_user'
    id:Mapped[str]=mapped_column(String,primary_key=True)
    username:Mapped[str]=mapped_column(String,unique=True)
    password_hash:Mapped[str]=mapped_column(String)
    role:Mapped[str]=mapped_column(String)

class Login(Base):
    __tablename__='web_session'
    token_hash:Mapped[str]=mapped_column(String,primary_key=True)
    user_id:Mapped[str]=mapped_column(String)
    expires:Mapped[float]=mapped_column(Float)

class Project(Base):
    __tablename__='web_project'
    id:Mapped[str]=mapped_column(String,primary_key=True)
    name:Mapped[str]=mapped_column(String)
    owner_id:Mapped[str]=mapped_column(String)

class Member(Base):
    __tablename__='web_member'
    project_id:Mapped[str]=mapped_column(String,primary_key=True)
    user_id:Mapped[str]=mapped_column(String,primary_key=True)

class Scene(Base):
    __tablename__='web_scene'
    id:Mapped[str]=mapped_column(String,primary_key=True)
    project_id:Mapped[str]=mapped_column(String,index=True)
    name:Mapped[str]=mapped_column(String)
    config:Mapped[dict]=mapped_column(JSON)

class Job(Base):
    __tablename__='web_job'
    __table_args__=(UniqueConstraint('project_id','idempotency_key'),)
    id:Mapped[str]=mapped_column(String,primary_key=True)
    project_id:Mapped[str]=mapped_column(String,index=True)
    idempotency_key:Mapped[str]=mapped_column(String)
    kind:Mapped[str]=mapped_column(String,default='generate')
    status:Mapped[str]=mapped_column(String,default='queued')
    stage:Mapped[str]=mapped_column(String,default='queued')
    payload:Mapped[dict]=mapped_column(JSON)
    result:Mapped[dict]=mapped_column(JSON,default=dict)
    log:Mapped[str]=mapped_column(Text,default='')
    cancel_requested:Mapped[bool]=mapped_column(default=False)
    lease:Mapped[str]=mapped_column(String,default='')
    updated:Mapped[float]=mapped_column(Float,default=time.time)
    created:Mapped[float]=mapped_column(Float,default=time.time)

class Run(Base):
    __tablename__='web_run'
    id:Mapped[str]=mapped_column(String,primary_key=True)
    project_id:Mapped[str]=mapped_column(String,index=True)
    name:Mapped[str]=mapped_column(String)
    relative_path:Mapped[str]=mapped_column(String,unique=True)
    route:Mapped[str]=mapped_column(String)
    created:Mapped[float]=mapped_column(Float,default=time.time)

class Version(Base):
    __tablename__='web_version'
    __table_args__=(UniqueConstraint('project_id','name'),)
    id:Mapped[str]=mapped_column(String,primary_key=True)
    project_id:Mapped[str]=mapped_column(String,index=True)
    name:Mapped[str]=mapped_column(String)
    run_id:Mapped[str]=mapped_column(String)
    status:Mapped[str]=mapped_column(String,default='staging')
    result:Mapped[dict]=mapped_column(JSON,default=dict)
    created:Mapped[float]=mapped_column(Float,default=time.time)

class Experiment(Base):
    __tablename__='web_experiment'
    id:Mapped[str]=mapped_column(String,primary_key=True)
    project_id:Mapped[str]=mapped_column(String,index=True)
    kind:Mapped[str]=mapped_column(String)
    result:Mapped[dict]=mapped_column(JSON)
    created:Mapped[float]=mapped_column(Float,default=time.time)

class Event(Base):
    __tablename__='web_event'
    id:Mapped[str]=mapped_column(String,primary_key=True)
    project_id:Mapped[str]=mapped_column(String,index=True)
    actor:Mapped[str]=mapped_column(String)
    action:Mapped[str]=mapped_column(String)
    detail:Mapped[dict]=mapped_column(JSON,default=dict)
    created:Mapped[float]=mapped_column(Float,default=time.time)

class Setting(Base):
    __tablename__='web_setting'
    key:Mapped[str]=mapped_column(String,primary_key=True)
    value:Mapped[dict]=mapped_column(JSON)

class Link(Base):
    __tablename__='web_label_link'
    run_id:Mapped[str]=mapped_column(String,primary_key=True)
    value:Mapped[dict]=mapped_column(JSON)
