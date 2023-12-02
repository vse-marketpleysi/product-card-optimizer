import cv2
import os
import subprocess
import numpy as np
from moviepy.editor import *
from PIL import Image, ImageSequence
from enum import Enum
import math

# Parameters
animations_folder = 'db/animations/'
fps = 60

def blur_edges_near_transparancy(mask):
    edges = cv2.Canny(mask, 100, 200)
    dilated_edges = cv2.dilate(edges, None, iterations=1)

    k = 5
    blurred_img = cv2.GaussianBlur(mask, (k, k), 0)
    for i in range(2):
        blurred_img = cv2.GaussianBlur(blurred_img, (k, k), 0)

    final_img = np.where(dilated_edges[:, :, None].astype(bool), blurred_img, mask)
    return final_img

# Function to pad images to the same size
def pad_img(img, target_height, target_width):
    height, width, _ = img.shape
    delta_w = target_width - width
    delta_h = target_height - height
    top, bottom = delta_h // 2, delta_h - (delta_h // 2)
    left, right = delta_w // 2, delta_w - (delta_w // 2)
    color = [255, 255, 255]  # White padding
    return cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)

def load_preprocess_imgs(images_path, make_squared=False):
    max_width, max_height = 0, 0
    for image_file in images_path:
        img = cv2.imread(image_file)
        height, width, _ = img.shape
        max_height = max(max_height, height)
        max_width = max(max_width, width)

    if make_squared:
        max_width, max_height = [max(max_width, max_height)] * 2

    image_list = []
    for image_file in images_path:
        img = cv2.imread(image_file)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_padded = pad_img(img, max_height, max_width)
        image_list.append(img_padded)
    return image_list


def decompose_gif_into_frames(gif_path, duration=None, fps=30):
    frames = []
    img = Image.open(gif_path)
    
    # Calculate original duration in seconds
#     original_duration = img.info['duration'] * img.n_frames / 1000.0
    original_duration = img.info.get('duration', 100) * img.n_frames / 1000.0  
    
    if duration is not None:
        # Calculate the factor by which to stretch or compress the GIF
        factor = original_duration / duration
    else:
        factor = 1.0
    
    for frame in ImageSequence.Iterator(img):
        rgba_frame = frame.convert("RGBA")
        numpy_frame = np.array(rgba_frame)
        
        # Duplicate frames based on the factor
        num_duplicates = max(1, int(fps * (original_duration / img.n_frames) / factor))
        
        for _ in range(num_duplicates):
            frames.append(numpy_frame)
            
    return frames

def get_rotated_gradient(width):
    line_width = 200
    gradient_width = width + line_width * 2
    center = line_width // 2

    # Create a two-sided alpha array for color
    alpha_top = np.linspace(0, 200, center)
    alpha_bottom = np.linspace(200, 0, line_width - center)
    alpha_color = np.concatenate([alpha_top, alpha_bottom])

    # Create the gradient with an alpha channel for transparency
    gradient = np.zeros((line_width, gradient_width, 4), dtype=np.uint8)
    gradient[:, :, :3] = 255  # Set RGB channels. Change to any other color if you wish.
    gradient[:, :, 3] = alpha_color[:, np.newaxis]  # Set alpha channel for transparency

    # Broadcast to fill the width
    gradient = np.broadcast_to(gradient, (line_width, gradient_width, 4))

    # Assuming `gradient` is your image
    rows, cols = gradient.shape[:2]

    # getRotationMatrix2D needs coordinates in reverse order (width, height) compared to shape
    M = cv2.getRotationMatrix2D((cols/2, rows/2), -45, 1)

    # rotate image without cropping corners
    abs_cos = abs(M[0,0]) 
    abs_sin = abs(M[0,1])

    bound_w = int(rows * abs_sin + cols * abs_cos)
    bound_h = int(rows * abs_cos + cols * abs_sin)

    M[0, 2] += bound_w/2 - cols/2
    M[1, 2] += bound_h/2 - rows/2

    rotated_gradient = cv2.warpAffine(gradient, M, (bound_w, bound_h))
    rotated_gradient = rotated_gradient[line_width:-line_width, line_width:-line_width]
    rotated_gradient = cv2.resize(rotated_gradient, (width, width))
    return rotated_gradient


def paste_img(img, overlay, coords):
    """
    Paste 'overlay' on top of 'img' at 'coords' position.

    :param img: The background image as a numpy array (Height x Width x 4 for transparent)
    :param overlay: The image to paste, as a numpy array (Height x Width x 4 for transparent)
    :param coords: Tuple specifying the (x, y) position to paste 'overlay' onto 'img'
    """
    x, y = coords
    if x < 0:  # If x is negative, adjust the overlay and coordinate
        w_offset = abs(x)
        overlay = overlay[:, w_offset:]
        x = 0

    if y < 0:  # If y is negative, adjust the overlay and coordinate
        h_offset = abs(y)
        overlay = overlay[h_offset:, :]
        y = 0

    # Dimensions
    h_img, w_img = img.shape[:2]
    h_overlay, w_overlay = overlay.shape[:2]

    # Calculate the region to paste on
    x1 = max(0, x)
    x2 = min(x + w_overlay, w_img)
    y1 = max(0, y)
    y2 = min(y + h_overlay, h_img)
    
    # If the overlay has an alpha channel
    if overlay.shape[2] == 4:  
        alpha_mask = overlay[(y1-y):(y2-y), (x1-x):(x2-x), 3] / 255.0
        alpha_mask = np.expand_dims(alpha_mask, axis=2) 
        img[y1:y2, x1:x2, :3] = \
            (1 - alpha_mask) * img[y1:y2, x1:x2, :3] + alpha_mask * overlay[(y1-y):(y2-y), (x1-x):(x2-x), :3]

    else:
        img[y1:y2, x1:x2] = overlay[(y1-y):(y2-y), (x1-x):(x2-x)]

    return img

class AnimationStep:
    offset = (0, 0)
    scale = 1
    timestamp = 0
    next_step = None
    
    def __init__(self, offset, scale, timestamp):
        self.offset = offset  # (offset_x, offset_y), normalized
        self.scale = scale  # normalized
        self.timestamp = timestamp
    
    def apply(self, frame, img):
        frame_height, frame_width, _ = frame.shape
        img_height, img_width, _ = img.shape
        new_height, new_width = int(img_height * self.scale), int(img_width * self.scale)

        # Scale the image
        scaled_img = cv2.resize(img, (new_width, new_height))

        # Calculate the offset in pixels
        offset_x = int(self.offset[0] * frame_width)
        offset_y = int(self.offset[1] * frame_height)

        # Paste the image
        return paste_img(frame, scaled_img, (offset_x, offset_y))

    def blend(self, animation_step, alpha):
        # Blend offset and scale using linear interpolation
        blended_offset = (
            self.offset[0] * (1 - alpha) + animation_step.offset[0] * alpha,
            self.offset[1] * (1 - alpha) + animation_step.offset[1] * alpha,
        )
        
        blended_scale = self.scale * (1 - alpha) + animation_step.scale * alpha

        return AnimationStep(blended_offset, blended_scale, None)
    
    def __str__(self):
        return f'AnimationStep<{self.offset}, {self.scale}>'
        

def effect_glare(image_path):
    duration = 2.1

    img = cv2.imread(image_path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
    height, width, _ = img.shape

    gradient = get_rotated_gradient(width + 400)

    frames = []
    for t in np.linspace(0, 1, math.ceil(duration * fps)):
        frame = img.copy()
        frame = paste_img(frame, gradient, (-200, int(4 * (-t + 0.5) * height / 2)))
        frames.append(frame)
    return frames


def effect_sale_badge(image_path):
    gif_path = f'{animations_folder}sale.gif'

    gif_frames = decompose_gif_into_frames(gif_path)

    img = cv2.imread(image_path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
    height, width, _ = img.shape

    frames = []
    for gif_frame in gif_frames:
        frame = img.copy()
        frame = paste_img(frame, gif_frame, (width - gif_frame.shape[1], height - gif_frame.shape[0]))
        frames.append(frame)

    return frames


def effect_slides(image_paths):
    imgs = load_preprocess_imgs(image_paths)
    duration_per_image = 8.5 / len(imgs)
    transition_frames = 10

    frames = []
    for i in range(len(imgs)):
        img1 = imgs[i]
        img2 = imgs[(i + 1) % len(imgs)]  # Loops back to the first image from the last

        for t in np.linspace(0, 1, int((duration_per_image * fps) - transition_frames)):
            frame = img1.copy()
            frames.append(frame)

        # transition from img1 to img2
        for t in np.linspace(0, 1, transition_frames):
            blend = cv2.addWeighted(img1, 1 - t, img2, t, 0)
            frames.append(blend)

    return frames


def effect_close_up_and_slide_down(image_path):
    animation = [
        AnimationStep((0, 0), 1, 0),
        AnimationStep((-0.5, 0), 2, 1),
        AnimationStep((-0.5, -1), 2, 3),
        AnimationStep((0, 0), 1, 4),
    ]
    for i in range(len(animation) - 1):
        animation[i].next_step = animation[i + 1]

    img = cv2.imread(image_path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
    height, width, _ = img.shape


    frames = []
    for animation_step in animation[:-1]:
        step_duration = animation_step.next_step.timestamp - animation_step.timestamp
        for t in np.linspace(0, 1, int(step_duration * fps)):
            frame = img.copy()
            animation_slice = animation_step.blend(animation_step.next_step, t)

            frame = animation_slice.apply(frame, img)
            frames.append(frame)

    return frames


def animation_in_angles_template(image_path, animation_name):
    overlay_frames_top = np.load(f'{animations_folder}{animation_name}_top.npy', allow_pickle=True)
    overlay_frames_bottom = np.load(f'{animations_folder}{animation_name}_bottom.npy', allow_pickle=True)

    gif_duration = len(overlay_frames_top) / fps 

    # Read the base image
    img = cv2.imread(image_path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
    height, width, _ = img.shape

    frames = []
    for o1, o2 in zip(overlay_frames_top, overlay_frames_bottom):
        frame = img.copy()
        frame = paste_img(frame, o1, (0, 0))
        frame = paste_img(frame, o2, (width - o2.shape[1], height - o2.shape[0]))
        frames.append(frame)
    return frames


def effect_blue_starts_many(image_path):
    frames = animation_in_angles_template(image_path, 'blue_starts_many')
    return frames


def effect_pixels(image_path):
    frames = animation_in_angles_template(image_path, 'pixels')
    return frames


def effect_flames(image_path):
    frames = animation_in_angles_template(image_path, 'flames')
    return frames


def effect_flashlights_many(image_path):
    frames = animation_in_angles_template(image_path, 'flashlights_many')
    return frames


def effect_flashlights(image_path):
    frames = animation_in_angles_template(image_path, 'flashlights')
    return frames


def effect_sale_many(image_path):
    frames = animation_in_angles_template(image_path, 'sale_many')
    return frames


def effect_sale_one(image_path):
    frames = animation_in_angles_template(image_path, 'sale_one')
    return frames
