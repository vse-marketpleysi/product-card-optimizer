import json
import os


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def create_json_if_not_exist(path, json_fields):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        save_json(path, json_fields)
