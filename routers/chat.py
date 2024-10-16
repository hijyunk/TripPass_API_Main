from fastapi import FastAPI, APIRouter, Query, HTTPException, Depends, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel, ValidationError
from typing import Optional
from datetime import datetime
from models.models import *
import json
from database import sqldb, db
from utils.function import *

router = APIRouter()

# mongodb collection
ChatData_collection = db['ChatData']
SavePlace_collection = db['SavePlace']

class QuestionRequest(BaseModel):
    userId: str
    tripId: str
    sender: str
    message: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    personality: Optional[str] = None
    isSerp: Optional[bool] = None

# ObjectId를 문자열로 변환하는 헬퍼 함수
def convert_objectid_to_str(doc):
    if '_id' in doc:
        doc['_id'] = str(doc['_id'])
    return doc

def formatDate(dateObj):
    return dateObj.strftime("%Y년 %m월 %d일")

@router.get(path='/getWelcomeMessage', description="환영 메시지 가져오기")
async def getWelcomeMessage(
    userId: str = Query(...), 
    tripId: str = Query(...),
    session: Session = Depends(sqldb.sessionmaker)):
    try:
        # 여행 정보와 사용자 정보 가져오기
        trip_info = session.query(myTrips).filter(myTrips.tripId == tripId).first()
        user_info = session.query(user).filter(user.userId == userId).first()

        if trip_info and user_info:
            startDate = formatDate(trip_info.startDate)
            endDate = formatDate(trip_info.endDate)
            welcome_message = f"안녕하세요,\n {startDate}부터 {endDate}까지 \n{trip_info.city}(으)로 여행을 가시는 {user_info.nickname}님!\n{user_info.nickname}님만의 여행 플랜을 함께 만들어 볼까요?🤓"

            # 환영 메시지를 메모리에 저장
            from utils.function import memory
            memory.save_context({"input": ""}, {"output": welcome_message})

            # 환영 메시지를 ChatData_collection에 저장
            chat_log = {
                "userId": userId,
                "tripId": tripId,
                "conversation": [
                    {
                        "timestamp": datetime.datetime.now(),
                        "sender": "bot",
                        "message": welcome_message,
                        "isSerp": False
                    }
                ]
            }

            ChatData_collection.update_one(
                {"userId": userId, "tripId": tripId},
                {"$set": chat_log},
                upsert=True
            )

            return {"result_code": 200, "welcome_message": welcome_message}
        else:
            return {"result_code": 404, "message": "Trip info or user info not found"}
    except Exception as e:
        return {"result_code": 400, "message": f"Error: {str(e)}"}


@router.get(path='/getChatMessages', description="채팅 로그 가져오기")
async def getChatMessages(userId: str = Query(...), tripId: str = Query(...)):
    try:
        chat_log = ChatData_collection.find_one({"userId": userId, "tripId": tripId})
        if chat_log:
            response_data = convert_objectid_to_str(chat_log)
            conversation = response_data.get("conversation", [])
            return {"result_code": 200, "messages": conversation}
        else:
            return {"result_code": 404, "messages": []}
    except Exception as e:
        return {"result_code": 400, "messages": f"Error: {str(e)}"}

@router.post(path='/saveChatMessage', description="채팅 로그 저장")
async def saveChatMessage(request: QuestionRequest):
    try:
        # 채팅 로그 생성
        chat_log = {
            "timestamp": datetime.datetime.now(),
            "sender": request.sender,
            "message": request.message,
            "isSerp": request.isSerp or False
        }
        # userId와 tripId가 있는지 확인하고 업데이트 또는 삽입
        result = ChatData_collection.update_one(
            {"userId": request.userId, "tripId": request.tripId},
            {
                "$push": {"conversation": chat_log},
                "$setOnInsert": {
                    "userId": request.userId,
                    "tripId": request.tripId
                }
            },
            upsert=True
        )

        if result.upserted_id is not None:
            response_message = "New chat log created successfully"
        else:
            response_message = "Chat log updated successfully"

        return {"result_code": 200, "response": response_message}

    except ValidationError as e:
        return {"result_code": 422, "response": f"Validation error: {str(e)}"}
    except Exception as e:
        return {"result_code": 400, "response": f"Error: {str(e)}"}

@router.get(path='/getSavePlace', description="선택한 장소 가져오기")
async def getSavedPlaces(userId: str = Query(...), tripId: str = Query(...)):
    try:
        document = SavePlace_collection.find_one({"userId": userId, "tripId": tripId})
        if document:
            response_data = document.get('placeData', [])
            return {"result_code": 200, "response": response_data}
        else:
            return {"result_code": 404, "response": "Document not found"}
    except Exception as e:
        return {"result_code": 400, "response": f"Error: {str(e)}"}

@router.post(path='/updateTripPlan', description="여행 계획 수정")
async def updateTripPlan(
    userId: str = Form(...),
    tripId: str = Form(...),
    date: str = Form(...),
    title: str = Form(...),
    new_time: str = Form(...),
    session: Session = Depends(sqldb.sessionmaker)
):
    try:
        # 사용자와 여행 ID에 따른 모든 여행 정보 가져오기
        plans = session.query(tripPlans).filter_by(userId=userId, tripId=tripId).all()
        
        if not plans:
            raise HTTPException(status_code=404, detail="No data found for this user and trip.")
        
        # 날짜와 제목이 일치하는 계획 찾기
        updated = False
        for plan in plans:
            if plan.date == date and plan.title == title:
                # 변경할 시간이 이미 존재하면 불가능
                if any(p.time == new_time for p in plans):
                    raise HTTPException(status_code=400, detail="The new time already exists in the schedule.")
                
                # crewId가 있을 경우 변경 불가
                if plan.crewId:
                    raise HTTPException(status_code=403, detail="Cannot modify plan with crewId.")
                
                # 시간 업데이트
                plan.time = new_time
                session.commit()
                updated = True
                break
        
        if not updated:
            raise HTTPException(status_code=404, detail="No matching plan found to update.")

        return {"result_code": 200, "response": "Plan updated successfully"}
    
    except Exception as e:
        session.rollback()
        return {"result_code": 400, "response": f"Error: {str(e)}"}
    
    finally:
        session.close()

@router.post(path='/callOpenAIFunction', description="OpenAI 함수 호출")
async def call_openai_function_endpoint(request: QuestionRequest):
    try:
        response = call_openai_function(request.message, request.userId, request.tripId, request.latitude, request.longitude, request.personality)
        return {"result_code": 200, 
                "response": response["result"], 
                "geo": response.get("geo_coordinates"), 
                "isSerp": response.get("isSerp"),
                "function_name": response.get("function_name")}
    except ValidationError as e:
        return {"result_code": 422, "response": f"Validation error: {str(e)}"}
    except Exception as e:
        return {"result_code": 400, "response": f"Error: {str(e)}"}

@router.post(path='/clearMemory', description="메모리 초기화")
async def clear_memory_endpoint():
    try:
        memory.clear()
        return {"result_code": 200, "response": "Memory has been cleared."}
    except Exception as e:
        return {"result_code": 400, "response": f"Error: {str(e)}"}


#savePlace mongoDB data delete 
@router.delete(path ="/deletePlaceData/{tripId}/{title}", description="특정 placeData 삭제")

async def delete_place_data(tripId: str, title: str):
    try:
        # tripId와 일치하는 문서에서 특정 title의 placeData 항목 삭제
        result = SavePlace_collection.update_one(
            {"tripId": tripId},
            {"$pull": {"placeData": {"title": title}}}
        )

        if result.modified_count > 0:
            response_message = "Place data deleted successfully"
        else:
            response_message = "No matching place data found"

        return {"result_code": 200, "response": response_message}

    except Exception as e:
        return {"result_code": 400, "response": f"Error: {str(e)}"}
