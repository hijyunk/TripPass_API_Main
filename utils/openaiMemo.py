import os
import google.generativeai as genai

def openaiMemo(contry, city, GEMINI_API_KEY):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    query = f"{city}, {contry} 여행 할 때 신경써야할 점을 한국어 200자 이내로 알려줘 '\n'(개행) 꼭 넣어서"

    response = model.generate_content(query)
    
    result = response.text
    return result

def openaiPlanMemo(places, GEMINI_API_KEY):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    query = f"{places} 여행 할 때 신경써야할 점을 한국어 200자 이내로 알려줘 '\n'(개행) 꼭 넣어서 "
    response = model.generate_content(query)
    
    result = response.text
    return result
