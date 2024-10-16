from fastapi import FastAPI, Form, Depends, APIRouter
from sqlalchemy.orm import Session
from models.models import joinRequests, crew, user, tripPlans
from database import sqldb
import base64
import uuid

router = APIRouter()

@router.get('/getJoinRequests', description="mySQL joinRequests Table 접근해서 정보 가져오기, userId는 필수")
async def getJoinRequestsTable(userId: str = None, session: Session = Depends(sqldb.sessionmaker)):
    try:
        if userId:
            query = session.query(joinRequests).filter(
                (joinRequests.userId == userId) | 
                (joinRequests.crewId.in_(
                    session.query(crew.crewId).filter(crew.crewLeader == userId)
                ))
            )
        else:
            return {"result code": 404, "response": "User not found"}

        joinRequest_data = query.all()
        results = []
        for joinRequest in joinRequest_data:
            joinRequest_dict = {
                "requestId": joinRequest.requestId,
                "crewId": joinRequest.crewId,
                "status": joinRequest.status,
                "alert": joinRequest.alert,
                "userId": joinRequest.userId
            }

            if joinRequest.crewId:
                crew_data = session.query(crew).filter(crew.crewId == joinRequest.crewId).first()
                if crew_data:
                    joinRequest_dict["crewTitle"] = crew_data.title
                    joinRequest_dict["crewLeader"] = crew_data.crewLeader
            
            results.append(joinRequest_dict)
        return {"result code": 200, "response": results}
        
    finally:
        session.close()

@router.post('/insertJoinRequests', description="mySQL joinRequests Table에 추가, requestId는 auto increment로 생성")
async def insertJoinRequestsTable(
    userId: str = Form(...),
    tripId: str = Form(...),
    crewId: str = Form(...),
    session: Session = Depends(sqldb.sessionmaker)
):
    try:
        existing_request = session.query(joinRequests).filter(
            joinRequests.userId == userId,
            joinRequests.crewId == crewId
        ).first()
        if existing_request:
            return {"result code": 409, "response": "Request already exists"}

        new_joinRequest = joinRequests(
            userId=userId,
            tripId=tripId,
            crewId=crewId,
            status=0,
            alert=0  # 새로운 요청의 알림 상태는 미확인
        )
        session.add(new_joinRequest)

        crew_data = session.query(crew).filter(crew.crewId == crewId).first()
        if not crew_data:
            return {"result code": 404, "response": "Crew not found"}

        sincheongIn = crew_data.sincheongIn
        if sincheongIn is None:
            crew_data.sincheongIn = userId
        elif userId in sincheongIn:
            return {"result code": 404, "response": "Already joined"}
        else:
            crew_data.sincheongIn = str(sincheongIn) + "," + userId
        session.commit()
        session.refresh(new_joinRequest)

        return {"result code": 200, "response": crewId}
    finally:
        session.close()

@router.post('/updateCrewTripMate', description="mySQL crew Table의 tripMate를 업데이트. main page에서 수락 또는 거절 누르면 처리")
async def updateCrewTripMate(
    crewId: str = Form(...),
    userId: str = Form(...),
    status: int = Form(...),
    session: Session = Depends(sqldb.sessionmaker)
):
    try:
        join_request = session.query(joinRequests).filter(
            joinRequests.crewId == crewId,
            joinRequests.userId == userId
        ).first()

        if not join_request:
            return {"result code": 404, "response": "Join request not found"}

        join_request.status = status
        join_request.alert = 0  # 알림 미확인 상태로 설정
        session.commit()

        crew_data = session.query(crew).filter(crew.crewId == crewId).first()
        if not crew_data:
            return {"result code": 404, "response": "Crew not found"}

        sincheongIn = crew_data.sincheongIn.split(",") if crew_data.sincheongIn else []
        if userId in sincheongIn:
            sincheongIn.remove(userId)
            if not sincheongIn or sincheongIn == [""]:
                crew_data.sincheongIn = None
            else:
                crew_data.sincheongIn = ",".join(sincheongIn)
        session.commit()
        # print(status)
    
        if status == 1:
            tripmates = crew_data.tripmate.split(",") if crew_data.tripmate else []
            if (userId not in tripmates) and (len(tripmates) < 4):
                tripmates.append(userId)
                crew_data.tripmate = ",".join(tripmates)
            session.commit()

            # joinRequests 테이블에서 tripId 가져오기
            tripId = join_request.tripId

            # tripPlans 테이블에서 tripId로 계획 찾기
            trip_plans = session.query(tripPlans).filter(tripPlans.planId == crew_data.planId).first()
            # print(trip_plans)
            new_trip_plan = tripPlans(
                planId=str(uuid.uuid4()),
                userId=userId,
                tripId=tripId,
                title=trip_plans.title,
                date=trip_plans.date,
                time=trip_plans.time,
                place=trip_plans.place,
                address=trip_plans.address,
                latitude=trip_plans.latitude,
                longitude=trip_plans.longitude,
                description=trip_plans.description,
                crewId=trip_plans.crewId
            )
            session.add(new_trip_plan)
            session.commit()

        return {"result code": 200, "response": "Operation successful"}
    except Exception as e:
        session.rollback()
        return {"result code": 500, "response": str(e)}
    finally:
        session.close()

@router.delete('/deleteJoinRequest', description="mySQL joinRequests Table에서 특정 요청 삭제")
async def deleteJoinRequest(requestId: int, session: Session = Depends(sqldb.sessionmaker)):
    try:
        join_request = session.query(joinRequests).filter(joinRequests.requestId == requestId).first()
        
        if not join_request:
            return {"result code": 404, "response": "Join request not found"}
        
        session.delete(join_request)
        session.commit()
        
        return {"result code": 200, "response": "Join request deleted successfully"}
    except Exception as e:
        session.rollback()
        return {"result code": 500, "response": str(e)}
    finally:
        session.close()

@router.get("/getCrewSincheongIn", description="mySQL crew Table에서 crew sincheongIn 가져오기")
async def getCrewSincheongIn(crewId: str, userId: str, session: Session = Depends(sqldb.sessionmaker)):
    try:
        query = session.query(crew)
        query = query.filter(crew.crewId == crewId, crew.sincheongIn.isnot(None), crew.crewLeader == userId)
        crew_data = query.first()
        
        if not crew_data:
            return {"result code": 404, "response": "no sincheongIn data"}

        sincheongIn_ids = crew_data.sincheongIn.split(",")
        
        sincheongIn_data = []
        for user_id in sincheongIn_ids:
            user_query = session.query(user).filter(user.userId == user_id)
            user_data = user_query.first()
            if user_data:
                user_dict = {
                    "userId": user_data.userId,
                    "id": user_data.id,
                    "nickname": user_data.nickname,
                    "birthDate": user_data.birthDate,
                    "sex": user_data.sex,
                    "profileImage": base64.b64encode(user_data.profileImage).decode('utf-8') if user_data.profileImage else None,
                    "socialProfileImage": user_data.socialProfileImage,
                    "personality": user_data.personality
                }
                sincheongIn_data.append(user_dict)
        
        return {"result code": 200, "response": sincheongIn_data}
    finally:
        session.close()

@router.post('/updateNotificationStatus', description="mySQL joinRequests Table에서 특정 요청 상태 업데이트")
async def updateNotificationStatus(
    requestId: int = Form(...),
    alert: int = Form(...),
    session: Session = Depends(sqldb.sessionmaker)
):
    try:
        join_request = session.query(joinRequests).filter(joinRequests.requestId == requestId).first()
        
        if not join_request:
            return {"result code": 404, "response": "Join request not found"}
        
        join_request.alert = alert
        session.commit()

        # 만약 알림이 거절된 요청이라면, joinRequests 테이블에서 해당 요청 삭제
        if alert == 1 and join_request.status == 2:
            session.delete(join_request)
            session.commit()
        
        return {"result code": 200, "response": "Join request alert status updated successfully"}
    except Exception as e:
        session.rollback()
        return {"result code": 500, "response": str(e)}
    finally:
        session.close()
