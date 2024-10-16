from sqlalchemy import Column, String, INT, FLOAT, LargeBinary, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.mysql import LONGBLOB

Base = declarative_base()

class user(Base):
    __tablename__ = 'user'
    userId = Column(String(36), primary_key=True)
    id = Column(String(36), nullable=False)
    passwd = Column(String(255), nullable=False)
    nickname = Column(String(50), nullable=False)
    profileImage = Column(LONGBLOB,  nullable=True)
    socialProfileImage = Column(String(255), nullable=True)
    birthDate = Column(String(36), nullable=False)
    sex = Column(String(36), nullable=False)
    personality = Column(JSON, nullable=True)
    mainTrip = Column(String(36), nullable=True)

class myTrips(Base):
    __tablename__ = 'myTrips'
    tripId = Column(String(36), primary_key=True)
    userId = Column(String(36), nullable=False)
    title = Column(String(60), nullable=False)
    contry = Column(String(36), nullable=False)
    city = Column(String(36), nullable=False)
    latitude = Column(FLOAT, nullable=False)
    longitude = Column(FLOAT, nullable=False)
    startDate = Column(String(36), nullable=False)
    endDate = Column(String(36), nullable=False)
    banner = Column(LargeBinary, nullable=True)
    memo = Column(Text, nullable=True)

class tripPlans(Base):
    __tablename__ = 'tripPlans'
    planId = Column(String(36), primary_key=True)
    userId = Column(String(36), nullable=False)
    tripId = Column(String(36), nullable=False)
    title = Column(String(255), nullable=False)
    date = Column(String(36), nullable=False)
    time = Column(String(36), nullable=False)
    place = Column(String(255), nullable=False)
    address = Column(String(255), nullable=False)
    latitude = Column(FLOAT, nullable=False)
    longitude = Column(FLOAT, nullable=False)
    description = Column(String(255), nullable=False)
    crewId = Column(String(36), nullable=True)

class crew(Base):
    __tablename__ = 'crew'
    crewId = Column(String(36), primary_key=True)
    planId = Column(String(36), nullable=False)
    tripId = Column(String(36), nullable=False)
    title = Column(String(60), nullable=False)
    contact = Column(String(36), nullable=False)
    note = Column(String(255), nullable=False)
    numOfMate = Column(INT, nullable=False)
    banner = Column(LargeBinary, nullable=True)
    tripmate = Column(String(255), nullable=True)
    sincheongIn = Column(String(255), nullable=True)
    crewLeader = Column(String(36), nullable=False)


class joinRequests(Base):
    __tablename__ = 'joinRequests'
    requestId = Column(INT, primary_key=True, autoincrement=True)
    crewId = Column(String(36), nullable=False)
    tripId = Column(String(50), nullable=False)
    userId = Column(String(36), nullable=False)
    status = Column(INT, nullable=False)     
    alert = Column(INT, nullable=False)