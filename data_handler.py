import os
import logging
import yaml
import urllib.request
from urllib.parse import urlparse
from datetime import datetime

# Глобальный кэш для скачанных URL
_download_cache = set()


def load_data(data_file: str) -> dict:
    """
    Загружает YAML-данные из указанного файла и возвращает словарь.
    """
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        logging.info(f"[load_data] Данные успешно загружены из '{data_file}'.")
        return data
    except OSError as err:
        logging.error(f"[load_data] Не удалось открыть файл '{data_file}': {err}")
        raise
    except Exception as e:
        logging.error(f"[load_data] Ошибка загрузки данных из '{data_file}': {e}")
        raise


def validate_data(data):
    """
    Проверяет наличие основных полей, не позволяя им быть пустыми.
    При несоответствии выбрасывает ValueError.
    """
    required_fields = {
        "name": "Имя",
        "date_of_birth": "Дата рождения",  # Добавлено
        "position": "Должность",
        "email": "Email",
        "phone": "Телефон",
        "summary": "Краткое описание",
        "experience": "Опыт работы",
        "education": "Образование",
        "skills": "Навыки",
        "languages": "Языки",
        "projects": "Проекты"
    }

    missing_fields = []
    empty_fields = []

    for field, field_name in required_fields.items():
        if field not in data:
            missing_fields.append(field_name)
        else:
            value = data[field]
            # Проверяем, что поле не пустое
            if isinstance(value, (list, dict)):
                if not value:
                    empty_fields.append(field_name)
            elif isinstance(value, str):
                if not value.strip():
                    empty_fields.append(field_name)

    if missing_fields:
        logging.error(f"Отсутствуют обязательные поля: {', '.join(missing_fields)}")
    if empty_fields:
        logging.error(f"Обязательные поля не должны быть пустыми: {', '.join(empty_fields)}")

    if missing_fields or empty_fields:
        raise ValueError("Валидация данных не пройдена.")

    logging.info("Валидация данных прошла успешно.")


def calculate_age(date_of_birth_str: str) -> int:
    """
    Вычисляет возраст на основе даты рождения в формате YYYY-MM-DD.
    """
    try:
        date_of_birth = datetime.strptime(date_of_birth_str, "%Y-%m-%d").date()
        today = datetime.today().date()
        age = today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
        return age
    except Exception as e:
        logging.error(f"Ошибка при вычислении возраста: {e}")
        return 0


def download_image(url, save_dir='images'):
    """
    Скачивает изображение по URL в указанную папку.
    Возвращает локальный путь или пустую строку, если не удалось.
    Использует кэш, чтобы не загружать повторно.
    """
    if not url:
        return ""

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    filename = os.path.basename(urlparse(url).path)
    filepath = os.path.join(save_dir, filename)

    # Если уже скачивали этот URL, и файл на месте — возвращаем сразу
    if url in _download_cache and os.path.exists(filepath):
        logging.info(f"Изображение {url} уже загружено ранее, используем кэш: {filepath}")
        return filepath

    try:
        urllib.request.urlretrieve(url, filepath)
        _download_cache.add(url)
        logging.info(f"Изображение загружено из {url} в {filepath}")
        return filepath
    except Exception as e:
        logging.error(f"Не удалось загрузить изображение из {url}: {e}")
        return ""


def process_image(image_data, save_dir='images'):
    """
    Преобразует описание изображения (dict) в локальный путь или URL.
    """
    if not isinstance(image_data, dict):
        logging.warning("Неправильный формат данных изображения. Ожидался словарь с 'type', 'value' и 'download'.")
        return ""

    img_type = image_data.get("type")
    img_value = image_data.get("value", "")
    download_flag = image_data.get("download", False)

    if not img_value:
        # Пустая строка — нет смысла обрабатывать
        return ""

    if img_type == "url":
        if download_flag:
            # Скачиваем и подменяем на локальный путь
            downloaded_path = download_image(img_value, save_dir)
            if downloaded_path:
                return downloaded_path
            else:
                # Если не вышло — оставляем URL как есть
                logging.warning(f"Не удалось скачать изображение по URL '{img_value}'. Используем URL напрямую.")
                return img_value
        else:
            # Просто оставляем URL
            return img_value

    elif img_type == "path":
        if os.path.isfile(img_value):
            return img_value
        else:
            logging.warning(f"Файл изображения '{img_value}' не найден. Путь будет удален.")
            return ""

    else:
        logging.warning(f"Неизвестный тип изображения '{img_type}'. Ожидалось 'url' или 'path'.")
        return ""


def check_images(data):
    """
    Проверяет (и при необходимости скачивает) изображения:
      - data["profile_image"]
      - data["projects"][..]["image"]
    """
    output_html_path = data.get("output_html", "output/resume.html")
    out_dir = os.path.join(os.path.dirname(os.path.abspath(output_html_path)), 'images')

    # Профиль
    profile = data.get("profile_image")
    if profile:
        data["profile_image"] = process_image(profile, save_dir=out_dir)

    # Проекты
    for project in data.get("projects", []):
        if "image" in project:
            project["image"] = process_image(project["image"], save_dir=out_dir)


def enrich_data_with_age(data: dict) -> dict:
    """
    Добавляет поле 'age' в данные резюме на основе 'date_of_birth'.
    """
    dob_str = data.get("date_of_birth")
    if dob_str:
        age = calculate_age(dob_str)
        data["age"] = age
    else:
        data["age"] = 0
        logging.warning("Поле 'date_of_birth' отсутствует. Возраст установлен в 0.")
    return data
