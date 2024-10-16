import openai
import requests
from io import BytesIO
import base64
from deep_translator import GoogleTranslator

def imageGeneration(contry, city, title, OPENAI_API_KEY):
    # OpenAI API 키 설정
    openai.api_key = OPENAI_API_KEY
    
    # 영어로 번역
    text = f'A beautiful travel photo of {city}, {contry}, {title}.'
    result = GoogleTranslator(source='ko', target='en').translate(text)
    
    # 이미지 생성
    response = openai.Image.create(
	prompt=result,
	n=1,
	size='1024x1024'
 )
    image_url = response['data'][0]['url']
    response = requests.get(image_url)
    img = BytesIO(response.content)
    img_base64 = base64.b64encode(img.getvalue()).decode('utf-8')
    return img_base64