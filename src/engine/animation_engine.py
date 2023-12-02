import cv2
import os
import subprocess
import uuid
import requests
import shutil
from urllib.parse import urlparse
import numpy as np
from moviepy.editor import *
from PIL import Image, ImageSequence
from enum import Enum
import math

from .animation_utils import effect_sale_badge, effect_slides, effect_close_up_and_slide_down, \
                             effect_blue_starts_many, effect_pixels, effect_flames, \
                             effect_flashlights_many, effect_flashlights, effect_sale_many, \
                             effect_sale_one, effect_glare

fps = 60
animations_mov_folder = 'db/animations_mov/'

class Effect(Enum):
    GLARE = 1
    SALE_BADGE = 2
    SLIDES = 3
    CLOSE_UP_AND_SLIDE_DOWN = 4
    BLUE_STARTS_MANY = 5
    PIXELS = 6
    FLAMES = 7
    FLASHLIGHTS_MANY = 8
    FLASHLIGHTS = 9
    SALE_MANY = 10
    SALE_ONE = 11
    
EFFECTS_USING_FFMPEG = [
    Effect.BLUE_STARTS_MANY,
    Effect.PIXELS,
    Effect.FLAMES,
    Effect.FLASHLIGHTS_MANY,
    Effect.FLASHLIGHTS,
    Effect.SALE_MANY,
    Effect.SALE_ONE
]


string_to_effect = {
    'Блеск': Effect.GLARE,
    'Значок скидки': Effect.SALE_BADGE,
    'Слайды': Effect.SLIDES,
    'Крупный план и движение вниз': Effect.CLOSE_UP_AND_SLIDE_DOWN,
    'Много синих звезд': Effect.BLUE_STARTS_MANY,
    'Пиксели': Effect.PIXELS,
    'Огонь': Effect.FLAMES,
    'Много фонарей': Effect.FLASHLIGHTS_MANY,
    'Фонари': Effect.FLASHLIGHTS,
    'Много скидок': Effect.SALE_MANY,
    'Одна скидка': Effect.SALE_ONE
}

def get_effect_from_string(name):
    return string_to_effect.get(name, 'Блеск')


effects_accepting_many_images = [Effect.SLIDES]


def download_image(url, retries=3):
    local_path = None
    while retries > 0:
        try:
            response = requests.get(url, stream=True, timeout=10)
            if response.status_code == 200:
                # Extract the file extension from the URL
                parsed_url = urlparse(url)
                file_extension = os.path.splitext(parsed_url.path)[1]
                
                # Generate a UUID-based filename with the original extension
                local_filename = f"db/images/{uuid.uuid4()}{file_extension}"
                with open(local_filename, 'wb') as f:
                    shutil.copyfileobj(response.raw, f)
                local_path = local_filename
                break
        except Exception:
            retries -= 1
    return local_path


def apply_effect(image_paths, output_path, effect_name: Effect, do_add_watermark):
    effect_name_to_function = {
        Effect.GLARE: effect_glare,
        Effect.SALE_BADGE: effect_sale_badge,
        Effect.SLIDES: effect_slides,
        Effect.CLOSE_UP_AND_SLIDE_DOWN: effect_close_up_and_slide_down,
        Effect.BLUE_STARTS_MANY: effect_blue_starts_many,
        Effect.PIXELS: effect_pixels,
        Effect.FLAMES: effect_flames,
        Effect.FLASHLIGHTS_MANY: effect_flashlights_many,
        Effect.FLASHLIGHTS: effect_flashlights,
        Effect.SALE_MANY: effect_sale_many,
        Effect.SALE_ONE: effect_sale_one,
    }
    
    if output_path.split('.')[-1] != 'mp4':
        raise ValueError(f'Can produce only mp4 files')
        
    # if len(image_paths) > 1 and effect_name not in effects_accepting_many_images:
    #     raise ValueError(f'Effect {effect_name.name} accepts only one image')
    
    # Process each path in the array
    for i, path in enumerate(image_paths):
        if path.startswith("http://") or path.startswith("https://"):
            local_path = download_image(path)
            if local_path:
                image_paths[i] = local_path

    resize_if_too_big_or_odd(image_paths)

    output_path_tmp = '.'.join(output_path.split('.')[-1:]) + '_tmp.' + output_path.split('.')[-1] \
        if do_add_watermark else output_path

    if effect_name in EFFECTS_USING_FFMPEG:
        combine_videos(image_paths[0], effect_name, output_path_tmp)
    else:
        effect_function = effect_name_to_function[effect_name]
        if effect_name in effects_accepting_many_images:
            frames = effect_function(image_paths)
        else:
            frames = effect_function(image_paths[0])
        
        current_duration = len(frames) / float(fps)
        num_loops = math.ceil(8.0 / current_duration)  # Ceiling division to get the least integer greater than or equal to the result
        clip = ImageSequenceClip(frames, fps=fps)
        looped_clips = [clip] * int(num_loops)  # Convert to int to avoid type error
        looped_clip = concatenate_videoclips(looped_clips)
        looped_clip.write_videofile(output_path_tmp, codec='libx264', bitrate='4000k', ffmpeg_params=['-crf', '20'], logger=None)

    if do_add_watermark:
        add_watermark(output_path_tmp, 'db/examples/watermark.png', output_path)

def add_watermark(input_video, watermark_image, output_video):
    try:
        subprocess.run([
            'ffmpeg', 
            '-i', input_video,
            '-i', watermark_image,
            '-y',
            '-filter_complex', 'overlay=W-w-10:H-h-10', 
            '-an',  # Skip audio to speed up the process
            '-preset', 'ultrafast',
            '-an',  # Skip audio to speed up the process
            '-preset', 'ultrafast',  # Preset to speed up the encoding process
            '-threads', '0',  # Use as many threads as available
            '-crf', '30',  # Constant rate factor, lower values mean better quality but slower speed
            output_video
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        error_message = (f"FFmpeg command failed with error: {e.returncode}\n"
                            f"Standard Output: {e.stdout}\n"
                            f"Standard Error: {e.stderr}")
        raise Exception(error_message)
    except Exception as e:
        raise Exception(f"An unexpected error occurred: {e}")
    


def combine_videos(image_path, effect: Effect, output_path):
    try:
        result = subprocess.run([
            'ffmpeg',
            '-hwaccel', 'auto',
            '-i', image_path,
            '-i', f'{animations_mov_folder}{effect.name}_top.mov',
            '-i', f'{animations_mov_folder}{effect.name}_bottom.mov',
            '-y',
            '-tune', 'stillimage',
            '-shortest',
            '-filter_complex', "[0][1]overlay=0:0[tmp];[tmp][2]overlay=W-w:H-h[video];[video]tpad=stop_duration=3:stop_mode=clone",
            '-preset', 'ultrafast',
            '-an',  # Skip audio to speed up the process
            '-preset', 'ultrafast',  # Preset to speed up the encoding process
            '-threads', '0',  # Use as many threads as available
            '-crf', '30',  # Constant rate factor, lower values mean better quality but slower speed
            output_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)


    except subprocess.CalledProcessError as e:
        error_message = (f"FFmpeg command failed with error: {e.returncode}\n"
                            f"Standard Output: {e.stdout}\n"
                            f"Standard Error: {e.stderr}")
        raise Exception(error_message)
    except Exception as e:
        raise Exception(f"An unexpected error occurred: {e}")


def resize_if_too_big_or_odd(image_paths):
    for i, local_path in enumerate(image_paths):
        with Image.open(local_path) as img:
            width, height = img.size
            
            # Determine the scaling factor
            max_dim = max(width, height)
            scaling_factor = 1100 / max_dim
            new_width = int(width * scaling_factor)
            new_height = int(height * scaling_factor)

            # Ensure the dimensions are even
            if new_width % 2 != 0:
                new_width -= 1
            if new_height % 2 != 0:
                new_height -= 1
                
            new_size = (new_width, new_height)

            # Resize and save if necessary
            if new_size != (width, height):
                img = img.resize(new_size)  # Using ANTIALIAS for better quality
            img.save(local_path)




            # # Make the image square by cropping, if needed
            # if width != height:
            #     new_dimension = min(width, height)
            #     left = (width - new_dimension) / 2
            #     top = (height - new_dimension) / 2
            #     right = (width + new_dimension) / 2
            #     bottom = (height + new_dimension) / 2
            #     img = img.crop((left, top, right, bottom))

            # width, height = img.size
            