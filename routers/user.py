from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException, Request, APIRouter
from fastapi.responses import RedirectResponse, JSONResponse
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from models.models import myTrips, user, crew, tripPlans, joinRequests
from database import sqldb, KAKAO_CLIENT_ID, KAKAO_REDIRECT_URI
import base64
import uuid
import httpx

router = APIRouter()

bcrypt_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

@router.get('/getUser', description="mySQL user Table 접근해서 정보 가져오기, userId는 선택사항")
async def getUserTable(
    userId: str = None,
    session: Session = Depends(sqldb.sessionmaker)):
    try:
        query = session.query(user)
        if userId is not None:
            query = query.filter(user.userId == userId)
        user_data = query.all()
        results = []
        for userdata in user_data:
            user_dict = {
                "userId": userdata.userId,
                "id": userdata.id,
                "passwd": userdata.passwd,
                "nickname": userdata.nickname,
                "birthDate": userdata.birthDate,
                "sex": userdata.sex,
                "personality": userdata.personality,
                "profileImage": base64.b64encode(userdata.profileImage).decode('utf-8') if userdata.profileImage else None,
                "mainTrip": userdata.mainTrip
            }
            results.append(user_dict)
        return {"result code": 200, "response": results}
    finally:
        session.close()

@router.get('/getUserId', description="mySQL user Table 중복 아이디 검사")
async def getUserIdTable(
    id: str = None,
    session: Session = Depends(sqldb.sessionmaker)):
    if id is None:
        raise HTTPException(status_code=400, detail="ID is required")
    try:
        existing_user = session.query(user).filter(user.id == id).first()
        if existing_user:
            return {"is_duplicate": True, "message": "이미 존재하는 아이디입니다"}
        else:
            return {"is_duplicate": False, "message": "사용 가능한 아이디입니다"}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")
    finally:
        session.close()
 

@router.post('/insertUser', description="mySQL user Table에 추가, userId는 uuid로 생성")
async def insertUserTable(
    id: str = Form(...), 
    passwd: str = Form(...), 
    nickname: str = Form(...),
    birthDate: str = Form(...),
    sex: str = Form(...),
    personality: str = Form(None),
    profileImage: UploadFile = File(None),
    socialProfileImage : str = Form(None),
    mainTrip: str = Form(None),
    session: Session = Depends(sqldb.sessionmaker)
):
    image_data = await profileImage.read() if profileImage else None
    hashed_password = bcrypt_context.hash(passwd)

    try:
        userId = str(uuid.uuid4())
        new_user = user(
            userId=userId, 
            id=id, 
            passwd=hashed_password, 
            nickname=nickname, 
            profileImage=image_data, 
            birthDate=birthDate, 
            sex=sex, 
            personality=personality, 
            socialProfileImage=socialProfileImage,
            mainTrip=mainTrip
        )
        session.add(new_user)
        session.commit()
        session.refresh(new_user)
        return {"result code": 200, "response": userId}
    
    finally:
        session.close()

@router.delete('/deleteUser', description="mySQL user Table에서 특정 사용자 삭제")
async def deleteUserTable(
    userId: str,
    session: Session = Depends(sqldb.sessionmaker)):
    try:
        with session.begin():
            session.query(joinRequests).filter(joinRequests.userId == userId).delete()
            session.query(crew).filter(crew.crewLeader == userId).delete()
            session.query(tripPlans).filter(tripPlans.userId == userId).delete()
            session.query(myTrips).filter(myTrips.userId == userId).delete()
            query = session.query(user).filter(user.userId == userId)
            user_data = query.first()
            if user_data:
                session.delete(user_data)
                session.commit()
                return {"result code": 200, "response": "User deleted"}
            else:
                return {"result code": 404, "response": "User not found"}
    except Exception as e:
        session.rollback()
        return {"result code": 500, "response": str(e)}
    finally:
        session.close()


@router.post('/updateUserProfileImage', description="Update profile image in the user table of mySQL")
async def updateUserProfileImage(
    userId: str = Form(...), 
    profileImage: UploadFile = File(...),
    session: Session = Depends(sqldb.sessionmaker)
):
    image_data = await profileImage.read()

    try:
        query = session.query(user).filter(user.userId == userId)
        user_data = query.first()

        if user_data:
            user_data.profileImage = image_data  
            profile_image_data = base64.b64encode(user_data.profileImage).decode('utf-8')
            session.commit()
            return {
                "result code": 200, "response": profile_image_data
            }
        else:
            return {"result code": 404, "response": "User not found"}
    except Exception as e:
        session.rollback()
        return {"result code": 500, "response": str(e)}
    finally:
        session.close()

@router.post('/updateUserPasswd', description="mySQL user Table의 비밀번호 업데이트")
async def updateUserPasswd(
    userId: str = Form(...), 
    passwd: str = Form(...),
    session: Session = Depends(sqldb.sessionmaker)
):
    try:
        query = session.query(user).filter(user.userId == userId)
        user_data = query.first()

        if user_data:
            hashed_password = bcrypt_context.hash(passwd.encode('utf-8'))
            user_data.passwd = hashed_password
            session.commit()
            return {"result code": 200, "response": "Password updated successfully"}
        else:
            return {"result code": 404, "response": "user not found"}
    except Exception as e:
        session.rollback()
        return {"result code": 500, "response": str(e)}
    finally:
        session.close()


@router.post('/updateUserPersonality', description="mySQL user Table의 여행 성향 업데이트")
async def updateUserPersonality(
    userId: str = Form(...), 
    personality : str = Form(...),
    session: Session = Depends(sqldb.sessionmaker)
):
    try:
        query = session.query(user).filter(user.userId == userId)
        user_data = query.first()

        if user_data:
            user_data.personality = personality
            session.commit()
            return {"result code": 200, "response": personality}
        else:
            return {"result code": 404, "response": "User not found"}
    except Exception as e:
        session.rollback()
        return {"result code": 500, "response": str(e)}
    finally:
        session.close()

# 사용자 로그인 처리
@router.post("/login")
async def login(
    id: str = Form(...),
    passwd: str = Form(...),
    session: Session = Depends(sqldb.sessionmaker)):
    try:
        user_data = session.query(user).filter(user.id == id).first()
        if not user_data or not bcrypt_context.verify(passwd, user_data.passwd):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        profile_image_data = base64.b64encode(user_data.profileImage).decode('utf-8') if user_data.profileImage else None
        
        return {
            "userId": user_data.userId,
            "id" : user_data.id,
            "nickname": user_data.nickname,
            "birthDate": user_data.birthDate,
            "sex": user_data.sex,
            "personality": user_data.personality,
            "profileImage": profile_image_data,
            "mainTrip": user_data.mainTrip
        }
    finally:
        session.close()


# 카카오 소셜 로그인
@router.get("/login/kakao")
def kakao_login():
    kakao_auth_url = f"https://kauth.kakao.com/oauth/authorize?client_id={KAKAO_CLIENT_ID}&redirect_uri={KAKAO_REDIRECT_URI}&response_type=code"
    return RedirectResponse(url=kakao_auth_url)
@router.get("/login/callback")
async def kakao_login_callback(code: str):
    session = sqldb.sessionmaker()
    try:
        token_url = "https://kauth.kakao.com/oauth/token"
        token_params = {
            "grant_type": "authorization_code",
            "client_id": KAKAO_CLIENT_ID,
            "redirect_uri": KAKAO_REDIRECT_URI,
            "code": code,
        }

        async with httpx.AsyncClient() as client:
            token_response = await client.post(token_url, data=token_params)
            if token_response.status_code != 200:
                raise HTTPException(status_code=token_response.status_code, detail="Failed to fetch access token from Kakao")

            token_data = token_response.json()
            access_token = token_data.get("access_token")

            profile_url = "https://kapi.kakao.com/v2/user/me"
            headers = {"Authorization": f"Bearer {access_token}"}
            profile_response = await client.get(profile_url, headers=headers)
            if profile_response.status_code != 200:
                raise HTTPException(status_code=profile_response.status_code, detail="Failed to fetch user profile from Kakao")

            profile_data = profile_response.json()

            kakao_id = profile_data["id"]
            nickname = profile_data["properties"]["nickname"]
            social_profile_image = profile_data["properties"].get("profile_image", "")
            user_id = "소셜 로그인 회원입니다"

            # 기존 사용자 확인 및 생성/업데이트
            user_entry = session.query(user).filter(user.id == kakao_id).first()
            if not user_entry:
                user_entry = user(
                    userId=str(uuid.uuid4()),
                    id=kakao_id,
                    passwd="",  
                    nickname=nickname,
                    socialProfileImage=social_profile_image,
                    birthDate='2024-01-01',
                    sex="None",
                    personality=None,
                    mainTrip=Null
                )
                session.add(user_entry)
            else:
                user_entry.nickname = nickname
                user_entry.socialProfileImage = social_profile_image

            session.commit()

            profile_image_data = base64.b64encode(user_entry.profileImage).decode('utf-8') if user_entry.profileImage else None

            return {
                "userId": user_entry.userId,
                "id": user_entry.id,
                "nickname": user_entry.nickname,
                "birthDate": user_entry.birthDate,
                "sex": user_entry.sex,
                "personality": user_entry.personality,
                "socialProfileImage": user_entry.socialProfileImage,
                "mainTrip": user_entry.mainTrip
            }
    finally:
        session.close()