from PIL import Image, ImageOps
import requests
from io import BytesIO
from typing import Union
import rembg
import io
import base64
import numpy as np
import json
import re

import requests
import uuid
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

background_url = 'background.PNG'#'https://www.ergogrips.net/wp-content/uploads/2016/06/ergo-background-2.jpg'
#'https://divnil.com/wallpaper/ipad/img/app/4/a/4abdace74f6175bcb6d262b90f05c9fa_cea1cefe51dd3a0094bb2fc5b9c24391_raw.jpg'
#https://freevector-images.s3.amazonaws.com/uploads/vector/preview/31503/abstract-blocks-blue-main.jpg'
img_source = 'https://eco-dush.ru/upload/iblock/dd1/dd12186acee71ef2cadaccc647e93bb7.jpg'

product_title = 'Электронная крышка-биде для унитаза Bidetko BK-688'

description = '''Электронная крышка-биде для унитаза Bidetko BK-688 – специальное сиденье на унитаз, разработанное с целью регулярного соблюдения правил интимной гигиены. Эта технологичная и комфортная приставка является качественной заменой стандартного биде, габариты которых достаточно велики, и не всегда умещаются в ванную комнату.

Умная накладка значительно упростит принятие гигиенического душа людям с ограниченными возможностями, пожилым и детям. Применение крышки-биде абсолютно безопасно для здоровья. Умное устройство – это отличный подарок бабушке, дедушке или родителям.

Гигиенические накладки на унитаз предназначены для поддержания чистоты и свежести интимных частей тела после похода в туалет. Биде приставка в сравнении с классическим беде имеет куда меньшие размеры и не требует дополнительного места в туалете для установки. Оно помещается поверх унитаза, а точнее становится заменой для обычного сидения с крышкой, и выполняет очистительно-моечную функцию.

Гигиеническое сиденье для унитаза Bidetko BK-688 по внешним данным и оформлению фактически не имеет никаких характерных отличий от обычных стульчаков. Накладка-биде так же имеет встроенный пульт управления, которым осуществляется контроль функционала, устанавливаются различные настройки: температура воды, позиция форсунки, подогрев сиденья, детский режим и другие. 

Пульт управления располагается с правой стороны электронного приспособления, поэтому находится всегда под рукой, что доставляет максимальный комфорт и удобство при использовании. Еще одно преимущество изделия – простая установка, понадобится лишь разводной ключ и отвертка.

Вы по достоинству оцените соотношение цены и высокого корейского качества. Электронное биде прошло сертификацию, имеет все необходимые документы и гарантию производителя 1 год.'''


ICON_GENERATOR_PROMPT = 'маленькая цветастая иконка для буллет поинта "%s"'

def download_image(url: str) -> Image.Image:
    """Download an image from a URL and return it as a PIL image."""
    response = requests.get(url)
    response.raise_for_status()
    return Image.open(BytesIO(response.content))

def load_image(source: str) -> Image.Image:
    """Load an image from a URL or a local file."""
    if source.startswith('http://') or source.startswith('https://'):
        return download_image(source)
    else:
        try:
            return Image.open(source)
        except FileNotFoundError:
            raise Exception('The provided file path does not exist.')

def place_image_on_background(
    transparent_image: Image.Image, 
    background: Image.Image, 
    margin_ratio: float = 0.05,
    position_to_right_ratio = 0.5
) -> Image.Image:
    """Place a transparent image on the right-hand side of a square background image."""

    # Determine maximum size for the transparent image, considering the margin
    margin = int(min(background.size) * margin_ratio)
    max_width = int(background.width * (1 - position_to_right_ratio)) - margin * 2
    max_height = background.height - (2 * margin)
    
    # Calculate resize ratio for the transparent image
    width_based = (max_width / transparent_image.width) < (max_height / transparent_image.height)
    ratio = max_width / transparent_image.width if width_based else max_height / transparent_image.height
    
    # Resize the transparent image
    transparent_image = transparent_image.resize(
        (int(transparent_image.width * ratio), int(transparent_image.height * ratio)),
        Image.LANCZOS
    )

    # Calculate `x` and `y` to place the image on the right, margin pixels from center
    x = int(background.width * position_to_right_ratio) + margin
    y = (background.height - transparent_image.height) // 2
    
    # Place the image
    background.paste(transparent_image, (x, y), transparent_image)
    return background

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import textwrap

def add_blurred_shadow(draw, position, text, font, shadow_blur=5, shadow_color='black'):
    # Create a temporary image to draw shadows on
    temp_img = Image.new('RGBA', draw.im.size, (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp_img)
    
    # Draw text multiple times with offsets to create a shadow effect
    offsets = [(x, y) for x in range(-shadow_blur, shadow_blur+1, 2) for y in range(-shadow_blur, shadow_blur+1, 2)]
    for offset in offsets:
        shadow_position = (position[0] + offset[0], position[1] + offset[1])
        temp_draw.text(shadow_position, text, font=font, fill=shadow_color)
    
    # Apply a blur filter to the shadows
    temp_img = temp_img.filter(ImageFilter.GaussianBlur(shadow_blur))
    
    # Paste the blurred shadow onto the original image
    draw.bitmap((0, 0), temp_img, fill=None)

def add_bullet_points_to_image(img, bullet_points, icons, font_path='Roboto-Bold.ttf', font_size=50, spacing=20):
    bullet_points = [textwrap.fill(bullet_point, 20) for bullet_point in bullet_points]
    
    # Load the image
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, font_size)

    # Starting positions
    x_position = 140  # Increase x_position to make room for icons
    y_position = 50
    rectangle_margin = 15  # Margin around the text inside the rectangle
    icon_size = (80, 80)  # Define the size for the icons

    # Iterate over the bullet points and their corresponding icons
    for point, icon in zip(bullet_points, icons):
        # Resize icon
        icon = icon.resize(icon_size, Image.LANCZOS)

        # Calculate the y position of the icon to align it with the text
        _, _, text_width, text_height = draw.textbbox((0,0), point, font=font)
        icon_y_position = y_position + (text_height - icon_size[1]) // 2

        # Place the icon on the image
        img.paste(icon, (x_position - icon_size[0] - rectangle_margin, icon_y_position), icon)

        # Add a blurred shadow behind the text
        add_blurred_shadow(draw, (x_position, y_position), point, font)

        # Draw text on top of the shadow
        draw.text((x_position, y_position), point, font=font, fill='black')

        # Update the y position for the next point
        y_position += text_height + spacing + 2 * rectangle_margin

    # Return the edited image
    return img

import json
import time

import requests


class Text2ImageAPI:

    def __init__(self, url, api_key, secret_key):
        self.URL = url
        self.AUTH_HEADERS = {
            'X-Key': f'Key {api_key}',
            'X-Secret': f'Secret {secret_key}',
        }

    def get_model(self):
        response = requests.get(self.URL + 'key/api/v1/models', headers=self.AUTH_HEADERS)
        data = response.json()
        return data[0]['id']

    def generate(self, prompt, model, images=1, width=768, height=768):
        params = {
            "type": "GENERATE",
            "numImages": images,
            "width": width,
            "height": height,
            "generateParams": {
                "query": f"{prompt}"
            }
        }

        data = {
            'model_id': (None, model),
            'params': (None, json.dumps(params), 'application/json')
        }
        response = requests.post(self.URL + 'key/api/v1/text2image/run', headers=self.AUTH_HEADERS, files=data)
        data = response.json()
        return data['uuid']

    def check_generation(self, request_id, attempts=10, delay=10):
        while attempts > 0:
            response = requests.get(self.URL + 'key/api/v1/text2image/status/' + request_id, 
                                    headers=self.AUTH_HEADERS)
            data = response.json()
            if data['status'] == 'DONE':
                return data['images']

            attempts -= 1
            time.sleep(delay)

            
def get_icons_for_bullet_points(product_title, bullet_points):
    api = Text2ImageAPI('https://api-key.fusionbrain.ai/', 
                        '2D5AE6D5A08AF7B3ED8A2CF3067651D7', '88E3E9E29C4744A5A6123CAAF8D3A867')
    model_id = api.get_model()
    
    template = ICON_GENERATOR_PROMPT
    prompts = [template % p for p in bullet_points]
    uuids = [api.generate(prompt, model_id) for prompt in prompts]
    images = [api.check_generation(uuid)[0] for uuid in uuids]

    output_images = []
    
    for base64_image in images:
        image_data = base64.b64decode(base64_image)
        image = Image.open(io.BytesIO(image_data))
        image_array = np.array(image)
        
        img = Image.fromarray(image_array).resize((200, 200))
        output = remove_background_and_crop(img)
        output_images.append(output)
    return output_images

def gigachat_auth():
    # URL and headers
    url = 'https://ngw.devices.sberbank.ru:9443/api/v2/oauth'
    bearer = 'OTk3NDg4ZjYtNThlZi00NGUyLTgxNjMtMDhmMTRkZjc1YzY2OjI1MmI0Y2JlLTE3ZjYtNDIyMC1hZjFmLWJmYjAzZmE4OTk0MA=='
    headers = {
        'Authorization': f'Bearer {bearer}',
        'RqUID': str(uuid.uuid4()),
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'scope': 'GIGACHAT_API_PERS'
    }

    response = requests.post(url, headers=headers, data=data, verify=False)

    if response.status_code == 200:
        access_token = response.json()['access_token']
    else:
        print('Failed with status code:', response.status_code)
        print(response.json())
    return access_token

def gigachat_complete(prompt):
    access_token = gigachat_auth()
    
    url = 'https://gigachat.devices.sberbank.ru/api/v1/chat/completions'

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }

    payload = {
        "model": "GigaChat:latest",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7
    }

    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    response = requests.post(url, headers=headers, data=data, verify=False)

    if response.status_code == 200:
        reply = response.json()['choices'][0]['message']['content']
    else:
        print('Failed with status code:', response.status_code)
        print(response.text)
    return reply


EXTRACT_FEATURES_PROMPT = '''
Выдели из нижеприложенного описания товара его ключевые полезные характеристики для отображения в \
инфографике карточки товара. 3 штуки. Каждый пункт не больше 3 слов. Перефразируй полученные фразы чтобы \
получилось по 3 слова.
Формат ответа: 
1. характеристика 1 (не больше 3 слов)
2. характеристика 2 (не больше 3 слов)
3. характеристика 3 (не больше 3 слов)
Конец

%s'''

def get_bullet_points(description):
    completion = gigachat_complete(EXTRACT_FEATURES_PROMPT % description)
    pattern = r'\d\.\s*(.+)'
    matches = re.findall(pattern, completion)
    return matches[:5]

def remove_background_and_crop(img):
    output = rembg.remove(img)
    alpha = output.getchannel('A')
    bbox = alpha.getbbox()
    res = output.crop(bbox)
    return res

def get_infographic_for_product(image_url, product_title, product_description):
    bullet_points = get_bullet_points(product_description)
    icons = get_icons_for_bullet_points(product_title, bullet_points)

    background = load_image(background_url).resize((1000, 1000))
    transparent_image = load_image(image_url)
    transparent_image = remove_background_and_crop(transparent_image)

    final_image = place_image_on_background(transparent_image, background, position_to_right_ratio=0.45, 
                                            margin_ratio=0.01)
    final_image = add_bullet_points_to_image(final_image, bullet_points, icons)

    path = 'tmp.png'
    final_image.save(path)
    return path
