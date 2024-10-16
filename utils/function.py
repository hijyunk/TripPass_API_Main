import os
import json
import openai
from serpapi import GoogleSearch
from deep_translator import GoogleTranslator
from sqlalchemy.ext.declarative import declarative_base
import re
import uuid
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker
import google.generativeai as genai
from database import sqldb, OPENAI_API_KEY, GEMINI_API_KEY, SERP_API_KEY,db
from models.models import myTrips, tripPlans, user
from langchain.memory import ConversationBufferMemory
from langchain.schema import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain.embeddings import OpenAIEmbeddings
from sklearn.metrics.pairwise import cosine_similarity
from typing import Optional
import datetime
from utils.openaiMemo import openaiPlanMemo

openai.api_key = OPENAI_API_KEY

# ConversationBufferMemory 초기화
if 'memory' not in globals():
    memory = ConversationBufferMemory()

pending_updates = {}

def get_embedding(text):
    response = openai.Embedding.create(input=text, model="text-embedding-ada-002")
    return response['data'][0]['embedding']

def message_to_dict(msg: BaseMessage):

    if isinstance(msg, HumanMessage):
        return {"role": "user", "content": msg.content}
    elif isinstance(msg, AIMessage):
        return {"role": "assistant", "content": msg.content}
    elif isinstance(msg, SystemMessage):
        return {"role": "system", "content": msg.content}
    else:
        raise ValueError(f"Unknown message type: {type(msg)}")

def call_openai_function(query: str, userId: str, tripId: str, latitude: Optional[float] = None, longitude: Optional[float] = None, personality: Optional[str] = None):
    isSerp = False
    geo_coordinates = []
    function_name = None
    
    if query.strip().lower() == "확인":
        result = update_trip_plan_confirmed(userId)
        memory.save_context({"input": query}, {"output": result})
        return {"result": result, "geo_coordinates": geo_coordinates, "isSerp": isSerp, "function_name": "update_trip_plan_confirmed"}

    if userId in pending_updates and query.strip().lower() != "확인":
        pending_updates.pop(userId)
        result = "일정 수정을 취소합니다! 수정을 원하시면 다시 수정사항을 말씀해주세요!"
        memory.save_context({"input": query}, {"output": result})
        return {"result": result, "geo_coordinates": geo_coordinates, "isSerp": isSerp, "function_name": "cancel_update"}

    memory.save_context({"input": query}, {"output": ""})
    print(memory.chat_memory)
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant that helps users plan their travel plans."},
    ] + [message_to_dict(msg) for msg in memory.chat_memory.messages] + [
        {"role": "user", "content": query}
    ]
    
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=messages,
        functions=[
            {
                "name": "search_places",
                "description": "Search for various types of places based on user query, such as 'popular cafes in Barcelona'. This function should be used for general searches where the user is looking for multiple options or recommendations.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query for finding places. Include keywords like 'find', 'popular', 'recommend', 'cafes', 'restaurants', etc. If the query isn't in English, translate it to English."
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "just_chat",
                "description": "Respond to general questions and provide information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The user's general query"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "save_place",
                "description": "사용자의 query에서 숫자가 있다면 숫자를 추출하여 SerpData의 MongoDB 데이터를 SavePlace MongoDB에 저장합니다. 사용자가 숫자와 함께, 또는 숫자 없이 '저장', '추가', '갈래' 등의 다양한 표현으로 저장을 요청할 수 있습니다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "사용자가 숫자와 함께 또는 숫자 없이 저장 또는 추가를 요청하는 다양한 표현의 쿼리 문자열"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "save_plan",
                "description": "SavePlace의 placeData를 mysql tripPlans Table에 저장",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "사용자가 여행 계획 짜줘, 여행 일정 만들어줘, 최종 일정 만들어줘, 그걸로 일정 짜줘 등 여행 관련 일정을 만들어달라는 요청하는 모든 말을 했을 때 실행"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "update_trip_plan",
                "description": "Update a trip plan with the given details",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "사용자가 일정을 수정하고 싶다는 내용을 담은 문자열"
                        },
                        "userId": {
                            "type": "string",
                            "description": "The user ID for the search context"
                        },
                        "tripId": {
                            "type": "string",
                            "description": "The trip ID for the search context"
                        }
                    },
                    "required": ["query", "userId", "tripId"]
                }
            },
            {
                "name": "search_place_details",
                "description": "Fetch detailed information about a specific place based on the place name. This function should be used when the user provides a specific place name and wants detailed information about it.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The name of the place to get details for. If the query isn't english, translate it in english."
                        }
                    },
                    "required": ["query"]
                }
            }
        ],
        function_call="auto"
    )

    try:
        function_call = response.choices[0].message["function_call"]
        function_name = function_call["name"]

        # 호출된 함수 이름을 출력
        print(f"Calling function: {function_name}")

        if function_name == "search_places":
            args = json.loads(function_call["arguments"])
            search_query = args["query"]

            result, geo_coordinates = search_places(search_query, userId, tripId, latitude, longitude, personality)
            isSerp = True

        elif function_name == "search_place_details":
            args = json.loads(function_call["arguments"])
            search_query = args["query"]
            
            result, geo_coordinates = search_place_details(search_query, userId, tripId, latitude, longitude)
            isSerp = True
        elif function_name == "just_chat":
            args = json.loads(function_call["arguments"])
            result = just_chat(args["query"])
        elif function_name == "save_place":
            args = json.loads(function_call["arguments"])
            result = savePlace(args["query"], userId, tripId)
        elif function_name == "save_plan":
            args = json.loads(function_call["arguments"])
            result = savePlans(userId, tripId)
        elif function_name == "update_trip_plan":
            args = json.loads(function_call["arguments"])
            result = handle_update_trip_plan(args["query"], userId, tripId)
        else:
            result = response.choices[0].message["content"]
    except KeyError:
        result = response.choices[0].message["content"]

    # 대화 메모리에 응답 추가
    memory.save_context({"input": query}, {"output": result})

    return {"result" : result, 
            "geo_coordinates": geo_coordinates, 
            "isSerp": isSerp, 
            "function_name": function_name}


def search_places(query: str, userId: str, tripId: str, latitude: float, longitude: float, personality: str):
    
    # JSON 문자열을 파이썬 딕셔너리로 변환
    try:
        # JSON 문자열을 파이썬 딕셔너리로 변환
        personality = json.loads(personality)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")  # JSON 디코딩 에러가 발생한 경우 출력
    except Exception as e:
        print(f"Unexpected error: {e}")  # 예상치 못한 에러가 발생한 경우 출력
    
    # Google Search API를 사용하여 장소 검색
    # ll 파라미터 설정
    ll_param = f"@{latitude},{longitude},14z"
    params = {
        "engine": "google_maps",
        "q": query,
        "hl": "en",
        "api_key": SERP_API_KEY,
        "ll": ll_param
    }
    search = GoogleSearch(params)
    data = search.get_dict()
    
    personality_dict = {
        "money1": "이왕 여행을 간 김에 가격이 비싸고 좋은 곳으로 알려줘",
        "money2": "여행 경비를 아껴야해 가격이 저렴한 곳으로 알려줘",
        "food1": "맛집 웨이팅 기다릴 수 있어 평점이 높은 곳 위주로",
        "food2": "그냥 끌리는대로 다닐래 평점 낮아도 상관 없어",
        "transport1": "경도 위도가 가까운 곳으로 알려줘",
        "transport2": "좀 멀어도 괜찮아",
        "schedule1": "즐기면서 천천히 다니고 싶어",
        "schedule2": "일정 알차게 돌아다니고 싶어",
        "photo1": "사진은 중요하지 않아",
        "photo2": "포토스팟 위주로 알려줘"
    }

    personality_query = "사용자의 성향: "
    for key, value in personality.items():
        personality_query += personality_dict[value] + " "
    
    parsed_results = []
    serp_collection = db['SerpData']
    serp_collection.delete_one({"userId": userId, "tripId": tripId})
    translator = GoogleTranslator(source='en', target='ko')
    
    # 결과 파싱
    for result in data['local_results']:
        title = result.get('title')
        rating = result.get('rating')
        address = result.get('address')
        gps_coordinates = result.get('gps_coordinates', {})
        latitude = gps_coordinates.get('latitude')
        longitude = gps_coordinates.get('longitude')
        description = result.get('description', 'No description available.')
        translated_description = translator.translate(description)
        price = result.get('price', None)

        if not address or not latitude or not longitude:
            continue

        place_data = {
            "title": title,
            "rating": rating,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "description": translated_description,
            "price": price,
            "date": None,
            "time": None
        }
        parsed_results.append(place_data)

    # Gemini API를 사용하여 정렬
    genai.configure(api_key=GEMINI_API_KEY)
    prompt = (personality_query + "\n"
              "장소 목록:\n" +
              '\n'.join([f"{i+1}. 장소 이름: {place['title']}\n    별점: {place['rating']}\n    주소: {place['address']}\n    설명: {place['description']}\n    가격: {place.get('price', '없음')}\n" 
                         for i, place in enumerate(parsed_results)]) + "\n"
              "위 성향에 맞게 장소 목록을 재정렬해주세요. 해당 성향에 적합한 장소를 먼저 정렬해주세요 모든 장소를 사용해야하고 중복되지 않게 해주세요 이 장소 말고 다른 장소는 추가해서 안돼")
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(prompt).text
    
    # 응답에서 정렬된 장소 목록 추출
    sorted_results = response.strip().split('\n')
    
    # parsed_results를 sorted_results 순서에 맞게 정렬
    sorted_parsed_results = []
    for result in sorted_results:
        for place in parsed_results:
            if place['title'] in result:
                sorted_parsed_results.append(place)
                break
    
    # 정렬된 결과를 MongoDB에 저장
    document = {
        "userId": userId,
        "tripId": tripId,
        "data": sorted_parsed_results
    }

    serp_collection.update_one(
        {"userId": userId, "tripId": tripId},
        {"$set": document},
        upsert=True
    )

    # 정렬된 결과를 포맷팅하여 반환
    final_formatted_results = []
    geo_coordinates = []
    for idx, place in enumerate(sorted_parsed_results, 1):
        formatted_place = f"*{idx}. 장소 이름: {place['title']}\n    별점: {place['rating']}\n    주소: {place['address']}\n    설명: {place['description']}\n"
        if place['price']:
            formatted_place += f"    가격: {place['price']}\n"
        final_formatted_results.append(formatted_place)
        geo_coordinates.append((place['latitude'], place['longitude']))
    resultFormatted = '\n'.join(final_formatted_results)
    return resultFormatted, geo_coordinates

def just_chat(query: str):
    response = openai.ChatCompletion.create(

        model="gpt-4o",

        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": query}
        ]
    )
    return response.choices[0].message["content"]

def savePlace(query, userId, tripId):
    try:
        serp_collection = db['SerpData']
        save_place_collection = db['SavePlace']
        
        document = serp_collection.find_one({"userId": userId, "tripId": tripId})
        
        if not document or 'data' not in document:
            return "No data found for the given userId and tripId."
        
        if re.search(r'\d+', query):
            numbers = re.findall(r'\d+', query)
            indexes = [int(number) for number in numbers]

            serp_data_length = len(document['data'])
            valid_indexes = [index-1 for index in indexes if 0 <= index-1 < serp_data_length]
            
            if not valid_indexes:
                return "No valid indexes found."
        
            selected_places = [document['data'][index] for index in valid_indexes]

        else:
            selected_places = [document['data']]
        
        save_place_collection.update_one(
            {"userId": userId, "tripId": tripId},
            {"$push": {"placeData": {"$each": selected_places}}},
            upsert=True
        )
        
        # 저장된 장소의 제목을 추출
        saved_titles = [place["title"] for place in selected_places]
        
        # 장소 제목을 포함한 응답 메시지 생성
        response_message = f"네, 알겠습니다! {', '.join(saved_titles)}이 저장되었습니다🥳\n\n저장하신 목적지로 최종적인 여행 계획을 원하시면 '여행 일정 만들어줘'라고 말씀해 주세요!"

        return response_message

    except Exception as e:
        return "잠시 오류가 있었어요😭 다시 한번 말해주세요!"

def savePlans(userId, tripId):
    session = sqldb.sessionmaker()
    # 사용자 성향 데이터 가져오기
    user_data = session.query(user).filter(user.userId == userId).first().personality
    personality = json.loads(user_data)
    
    transport_preference = personality.get("transport", "")
    schedule_preference = personality.get("schedule", "")

    # 성향에 따른 설명 매핑
    personality_dict = {
        "transport1": "관광지들끼리 경도 위도가 가까운 곳으로 알려줘",
        "transport2": "관광지들끼리 경도 위도가 좀 멀어도 괜찮아",
        "schedule1": "여행 스케줄을 즐기면서 천천히 다니고 싶어",
        "schedule2": "여행 스케줄 일정 알차게 돌아다니고 싶어"
    }

    # 사용자의 성향에 따른 query 구성
    personality_query = f"사용자의 성향은 {personality_dict.get(transport_preference, '')}, {personality_dict.get(schedule_preference, '')}"
    
    mytrip = session.query(myTrips).filter(myTrips.tripId == tripId).first()
    startDate = mytrip.startDate
    endDate = mytrip.endDate
    genai.configure(api_key=GEMINI_API_KEY)
    save_place_collection = db['SavePlace']
    document = save_place_collection.find_one({"userId": userId, "tripId": tripId})
    if not document:
        response = "아직 저장하신 장소들이 없어요🤔\n제가 추천해드리는 장소를 저장하시거나 가고 싶은 장소를 직접 입력해보세요!"
        return response
    place_data = document['placeData']
    place_data_str = json.dumps(place_data, ensure_ascii=False)
    model = genai.GenerativeModel('gemini-1.5-flash')
    query = f"""
    {startDate}부터 {endDate}까지 다음 장소들만 포함한 상세한 여행 일정을 만들어줘. {place_data_str} 데이터만을 모두 사용해서 모든 날짜에 관광지, 레스토랑, 카페가 균형있게 포함되게 짜주고 되도록 {personality_query} 니까 사용자의 성향에 맞춰서 짜줘. 같은 장소는 여러 일정을 만들지는 말아줘. 되도록 식사시간 그니까 12시, 6시는 식당이나 카페에 방문하게 해주고 
    시간은 시작 시간만 HH:MM:SS 형태로 뽑아주고 날짜는 YYYY-MM-DD이렇게 뽑아줘 description 절대 생략하지 말고 다 넣어줘. title 은 장소에서 해야할 일을 알려주면 좋겠다 예를 들어 에펠탑 관광 이런식으로 뽑아줘.

    일정에 들어가야하는 정보는 다음과 같은 포맷으로 만들어줘: title: [title], date: [YYYY-MM-DD], time: [HH:MM:SS], place: [place], address: [address], latitude: [latitude], longitude: [longitude], description: [description].의 json배열로 뽑아줘
    date랑 time이 null이 아니라면 그 시간으로 일정을 짜줘. startDate 부터 endDate까지 스케줄이 있어야해 다른 장소는 일정 만들 때 사용하지마 절대 내가 넣은 데이터만 사용해야해

    """
    response = model.generate_content(query)
    print(response.text)
    cleaned_string = response.text.strip('```')
    cleaned_string= cleaned_string.replace('json', '').strip()
    
    datas = json.loads(cleaned_string)
    

    for data in datas:
        new_trip = tripPlans(
            planId= str(uuid.uuid4()),
            userId= userId,
            tripId= tripId,
            title=data['title'],
            date=data['date'],
            time=data['time'],
            place=data['place'],
            address=data['address'],
            latitude=data['latitude'],
            longitude=data['longitude'],
            description=data['description']
        )
        session.add(new_trip)
    
    session.commit()

    # 저장한 계획들로 ai가 계획 별 메모 만들어주
    places = [data['place'] for data in datas]
    ai_memo = openaiPlanMemo(places, GEMINI_API_KEY)

    mytrip = session.query(myTrips).filter(myTrips.tripId == tripId).first()
    mytrip.memo = ai_memo
    session.commit()

    save_place_collection.delete_one({"userId": userId, "tripId": tripId})
    session.close()

    query = f"""
    {cleaned_string}이걸 상세하게 설명해서 답변해줘 챗봇이 일정을 만들어준 것처럼 예를 들어 바르셀로나 여행 일정을 완성했어요! 1일차 - 이런식으로
    """
    response = model.generate_content(query).text.replace('*', '')

    return response

def handle_update_trip_plan(query, userId, tripId):
    session = sqldb.sessionmaker()
    plans = session.query(tripPlans).filter_by(userId=userId, tripId=tripId).all()
    
    plan_texts = [f"{plan.title} {plan.date} {plan.time} {plan.place} {plan.address} {plan.description}" for plan in plans]
    plan_embeddings = [get_embedding(text) for text in plan_texts]
    
    query_embedding = get_embedding(query)
    similarities = [cosine_similarity([query_embedding], [embedding])[0][0] for embedding in plan_embeddings]
    
    most_similar_index = similarities.index(max(similarities))
    most_similar_plan = plans[most_similar_index]
    
    extracted_info = extract_info_from_query(query)
    
    new_title = extracted_info.get('title', most_similar_plan.title)
    new_date = extracted_info.get('date', most_similar_plan.date)
    new_time = extracted_info.get('time', most_similar_plan.time)
    
    confirmation_message = (
        f"다음 일정의 정보를 수정하려고 합니다:\n\n"
        f"[현재 일정]\n"
        f"일정명: {most_similar_plan.title}\n"
        f"날짜: {most_similar_plan.date}\n"
        f"시간: {most_similar_plan.time}\n"
        f"장소: {most_similar_plan.place}\n"
        f"주소: {most_similar_plan.address}\n\n"
        f"[변경될 일정]\n"
    )
    
    if new_title != most_similar_plan.title:
        confirmation_message += f"새로운 일정명: {new_title}\n"
    if new_date != most_similar_plan.date:
        confirmation_message += f"새로운 날짜: {new_date}\n"
    if new_time != most_similar_plan.time:
        confirmation_message += f"새로운 시간: {new_time}\n"
    
    confirmation_message += "\n이대로 수정하시겠습니까? '확인'을 입력해주시거나 원치 않으시면 '아니오'라고 입력해주세요!"
    
    pending_updates[userId] = {
        "tripId": tripId,
        "date": most_similar_plan.date,
        "title": most_similar_plan.title,
        "newTitle": new_title,
        "newDate": new_date,
        "newTime": new_time
    }
    
    return confirmation_message

def extract_info_from_query(query: str):
    date_pattern = r'\d{4}-\d{2}-\d{2}|\d{2}년\s?\d{1,2}월\s?\d{1,2}일'
    time_pattern = r'\d{1,2}:\d{2}|\d{1,2}시\s?\d{2}분|\d{1,2}시'

    date_match = re.search(date_pattern, query)
    time_match = re.search(time_pattern, query)

    extracted_info = {}

    if date_match:
        date_str = date_match.group()
        if "년" in date_str:
            date_str = date_str.replace('년', '-').replace('월', '-').replace('일', '').replace(' ', '')
            if len(date_str.split('-')[0]) == 2:
                date_str = '20' + date_str  # assuming all dates are in 21st century
        extracted_info['date'] = date_str

    if time_match:
        time_str = time_match.group()
        if "시" in time_str:
            time_str = time_str.replace('시', ':').replace('분', '').replace(' ', '')
            if len(time_str) == 2:
                time_str += "00"
            if len(time_str) == 3:
                time_str = '0' + time_str  # ensuring HH:mm format
        extracted_info['time'] = time_str

    title = query.split("일정")[0].strip()
    if title:
        extracted_info['title'] = title

    return extracted_info

def update_trip_plan_confirmed(userId: str):
    if userId not in pending_updates:
        return "No pending update found for the user."

    update_details = pending_updates[userId]
    result = update_trip_plan(
        userId=userId,
        tripId=update_details["tripId"],
        date=update_details["date"],
        title=update_details["title"],
        newTitle=update_details["newTitle"],
        newDate=update_details["newDate"],
        newTime=update_details["newTime"]
    )

    del pending_updates[userId]
    return result

def update_trip_plan(userId: str, tripId: str, date: str, title: str, newTitle: str, newDate: str, newTime: str):
    session = sqldb.sessionmaker()
    try:
        plan = session.query(tripPlans).filter_by(userId=userId, tripId=tripId, date=date, title=title).first()
        print(f"Update trip plan query result: {plan}")

        if plan:
            if plan.crewId:
                return "크루가 존재합니다! 일정 변경이 불가능 합니다!"
            
            original_plan = {
                "title": plan.title,
                "date": plan.date,
                "time": plan.time,
                "place": plan.place,
                "address": plan.address,
                "latitude": plan.latitude,
                "longitude": plan.longitude,
                "description": plan.description
            }

            plan.title = newTitle
            plan.date = newDate
            plan.time = newTime
            session.commit()

            updated_plan = {
                "title": plan.title,
                "date": plan.date,
                "time": plan.time,
                "place": plan.place,
                "address": plan.address,
                "latitude": plan.latitude,
                "longitude": plan.longitude,
                "description": plan.description
            }

            return (
                "성공적으로 일정이 수정되었습니다!\n\n"
                f"[수정 전 일정]\n"
                f"일정명: {original_plan['title']}\n"
                f"날짜: {original_plan['date']}\n"
                f"시간: {original_plan['time']}\n"
                f"장소: {original_plan['place']}\n"
                f"주소: {original_plan['address']}\n\n"
                f"[수정 후 일정]\n"
                f"일정명: {updated_plan['title']}\n"
                f"날짜: {updated_plan['date']}\n"
                f"시간: {updated_plan['time']}\n"
                f"장소: {updated_plan['place']}\n"
                f"주소: {updated_plan['address']}\n"
            )
        else:
            return "일정을 찾을 수 없습니다.(update_trip_plan)"
    except Exception as e:
        session.rollback()
        return f"An error occurred: {str(e)}"
    finally:
        session.close()

# 사용자 입력 버튼용 (특정 장소명에 대한 정보를 serp에서 불러오기)
def search_place_details(query: str, userId: str, tripId: str, latitude: float, longitude: float):
    ll_param = f"@{latitude},{longitude},14z"
    params = {
        "engine": "google_maps",
        "q": query,
        "hl": "en",
        "api_key": SERP_API_KEY,
        "ll": ll_param
    }
    search = GoogleSearch(params)
    data = search.get_dict()
    
    translator = GoogleTranslator(source='en', target='ko')
    result = data.get('place_results', {})
    
    # place_results가 비어 있을 경우 처리
    if not result:
        return "입력하신 장소를 찾을 수 없습니다😱\n정확한 장소명으로 다시 입력해주세요!", []
    
    serp_collection = db['SerpData']
    serp_collection.delete_one({"userId": userId, "tripId": tripId})
    
    title = result.get('title')
    rating = result.get('rating')
    address = result.get('address')
    gps_coordinates = result.get('gps_coordinates', {})
    latitude = gps_coordinates.get('latitude')
    longitude = gps_coordinates.get('longitude')
    description = result.get('description', 'No description available.')
    translated_description = translator.translate(description)
    price = result.get('price', None)

    if not address or not latitude or not longitude:
        return "입력하신 장소를 찾을 수 없습니다😱\n정확한 장소명으로 다시 입력해주세요!"
    
    geo_coordinates = [(latitude, longitude)]
    
    place_data = {
        "title": title,
        "rating": rating,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "description": translated_description,
        "price": price,
        "date": None,
        "time": None
    }
    
    formatted_result = f"*장소 이름: {title}\n주소: {address}\n설명: {translated_description}\n"
    if price:
        formatted_result += f"    가격: {price}\n"
    
    formatted_result += "\n이곳이 입력하신 장소가 맞나요?\n저장하고 싶으시면 '저장할게'라고 말씀해주세요😊"
    
    document = {
        "userId": userId,
        "tripId": tripId,
        "data": place_data
    }

    serp_collection.update_one(
        {"userId": userId, "tripId": tripId},
        {"$set": document},
        upsert=True
    )

    return formatted_result, geo_coordinates