from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException, Request, APIRouter
from sqlalchemy.orm import Session
from models.models import myTrips, user, crew, tripPlans
from database import sqldb, db, OPENAI_API_KEY, WEATHER_API_KEY, GEMINI_API_KEY
from utils.ImageGeneration import imageGeneration
from utils.GetWeather import getWeather
from utils.openaiMemo import openaiMemo
import base64
import uuid

router = APIRouter()

# mongodb collection
ChatData_collection = db['ChatData']
SavePlace_collection = db['SavePlace']
SerpData_collection = db['SerpData']

def convert_objectid_to_str(doc):
    if '_id' in doc:
        doc['_id'] = str(doc['_id'])
    return doc

@router.get('/getMyTrips', description = "mySQL myTrips Table 접근해서 정보 가져오기, tripId는 선택사항")
async def getMyTripsTable(
    userId: str = None,
    tripId: str = None,
    session: Session = Depends(sqldb.sessionmaker)):
    try:
        query = session.query(myTrips)
        if userId is not None:
            query = query.filter(myTrips.userId == userId)
        if tripId is not None:
            query = query.filter(myTrips.tripId == tripId)
        mytrips_data = query.all()
        results = []
        for mytrip in mytrips_data:
            mytrip_dict = {
                "tripId": mytrip.tripId,
                "userId": mytrip.userId,
                "title": mytrip.title,
                "contry": mytrip.contry,
                "city": mytrip.city,
                "latitude": mytrip.latitude,
                "longitude": mytrip.longitude,
                "startDate": mytrip.startDate,
                "endDate": mytrip.endDate,
                "memo": mytrip.memo,
                "banner": base64.b64encode(mytrip.banner).decode('utf-8') if mytrip.banner else None,
                
            }
            results.append(mytrip_dict)
        return {"result code": 200, "response": results}
    finally:
        session.close()

@router.get('/getWeather', description="main trip 지역의 날씨 정보 가져오기")
async def getWeatherInfo(city: str):
    # getWeather 함수를 호출하여 날씨 정보를 가져옴
    try:
        weather, icon, temp = getWeather(city, WEATHER_API_KEY)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"city": city, "weather": weather, "icon": icon, "temperature": temp}

@router.post('/insertmyTrips', description="mySQL myTrips Table에 추가, tripId는 uuid로 생성")
async def insertMyTripsTable(
    userId: str = Form(...),
    title: str = Form(...),
    contry: str = Form(...),
    city: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    startDate: str = Form(...),
    endDate: str = Form(...),
    session: Session = Depends(sqldb.sessionmaker)
):
    image_data = imageGeneration(contry, city, title, OPENAI_API_KEY)
    image_data = base64.b64decode(image_data)

    ai_memo = openaiMemo(contry, city, GEMINI_API_KEY)

    
    try:
        tripId = str(uuid.uuid4())
        new_trip = myTrips(
            tripId=tripId, 
            userId=userId, 
            title=title, 
            contry=contry, 
            city=city,
            latitude=latitude,
            longitude=longitude,
            startDate=startDate, 
            endDate=endDate, 
            memo=ai_memo, 
            banner=image_data
        )
        
        user_record = session.query(user).filter(user.userId == userId).first()
        if user_record and user_record.mainTrip is None:
            user_record.mainTrip = tripId
            session.commit()
        
        session.add(new_trip)
        session.commit()
        session.refresh(new_trip)
        return {"result code": 200, "response": tripId}
    finally:
        session.close()

@router.post("/updateUserMainTrip", description="mySQL user Table의 mainTrip 업데이트, myTripPage에서 사용")
async def update_user_main_trip(
    request: Request,
    session: Session = Depends(sqldb.sessionmaker)):

    data = await request.json()
    user_id = data.get("userId")
    main_trip = data.get("mainTrip")
    
    if not user_id or not main_trip:
        raise HTTPException(status_code=422, detail="userId and mainTrip are required")
    
    try:
        query = session.query(user).filter(user.userId == user_id)
        user_data = query.first()

        if user_data:
            user_data.mainTrip = main_trip
            session.commit()
            return {"result code": 200, "response": main_trip}
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()

@router.post('/updateMyTripsMemo', description="mySQL trip Table의 memo를 업데이트")
async def updateMytripsMemo(
    tripId: str = Form(...), 
    memo : str = Form(...),
    session: Session = Depends(sqldb.sessionmaker)
):
    try:
        query = session.query(myTrips).filter(myTrips.tripId == tripId)
        trip_data = query.first()

        if trip_data:
            trip_data.memo = memo
            session.commit()
            return {"result code": 200, "response": memo}
        else:
            return {"result code": 404, "response": "User not found"}
    except Exception as e:
        session.rollback()
        return {"result code": 500, "response": str(e)}
    finally:
        session.close()


@router.delete("/deleteTrip", description="mySQL myTrip Table에서 트립 삭제, crew가 있는 trip은 제외")
async def delete_trip(
    request: Request,
    session: Session = Depends(sqldb.sessionmaker)
    ):
    try:
        data = await request.json()
        user_id = data.get('userId')
        trip_id = data.get('tripId')

        if not user_id or not trip_id:
            raise HTTPException(status_code=400, detail="userId와 tripId가 필요합니다.")

        # crew 테이블에서 해당 tripId가 존재하는지 확인
        crew_count = session.query(crew).filter(crew.tripId == trip_id).count()
        if crew_count > 0:
            raise HTTPException(status_code=400, detail="크루 참여가 있는 여행은 삭제할 수 없습니다.")

        # tripPlans 테이블에서 해당 tripId와 관련된 모든 계획 삭제
        session.query(tripPlans).filter(tripPlans.tripId == trip_id).delete()

        # myTrips 테이블에서 해당 tripId 삭제
        session.query(myTrips).filter(myTrips.tripId == trip_id, myTrips.userId == user_id).delete()
        
        # MongoDB에서 관련 문서 삭제
        ChatData_collection.delete_many({"userId": user_id, "tripId": trip_id})
        SavePlace_collection.delete_many({"userId": user_id, "tripId": trip_id})
        SerpData_collection.delete_many({"userId": user_id, "tripId": trip_id})

        # 변경사항 커밋
        session.commit()
        return {"result code": 200, "message": "트립이 성공적으로 삭제되었습니다."}
    except HTTPException as e:
        # HTTPException 발생 시 그대로 전달
        raise e
    except Exception as e:
        # 기타 예외 발생 시 500 오류 반환
        session.rollback()
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")
    finally:
        # 세션 종료
        session.close()