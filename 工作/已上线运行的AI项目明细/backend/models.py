"""
数据库模型
"""
from sqlalchemy import Column, Integer, String, Text, DECIMAL, Date, TIMESTAMP
from sqlalchemy.sql import func
from database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_name = Column(String(255), nullable=False)
    project_goal = Column(Text)
    benefit_desc = Column(Text)
    money_benefit = Column(DECIMAL(10, 2), default=0)
    time_saved = Column(DECIMAL(10, 2), default=0)
    factory_name = Column(String(100))
    applicant = Column(String(100))
    create_time = Column(Date)
    submit_time = Column(Date)
    developer = Column(String(100))
    audit_time = Column(Date)
    online_time = Column(Date)
    cancel_time = Column(Date)
    status = Column(String(50))
    alarm_image = Column(String(500))
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
