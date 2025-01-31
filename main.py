# resume_generator/main.py

import sys
import argparse
import logging
import os

from .logging_config import setup_logging
from .gui import run_gui
from .data_handler import load_data, validate_data, check_images, enrich_data_with_age
from .generator import generate_resume


def main():
    # Настройка логирования (один раз)
    setup_logging()

    parser = argparse.ArgumentParser(description="Генератор резюме")

    # Взаимоисключающая группа: GUI или CLI
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--gui', action='store_true', help="Запустить графический интерфейс")
    group.add_argument('--run-cli', action='store_true', help="Запустить генерацию резюме через CLI")

    # Аргументы для CLI
    parser.add_argument(
        '--data',
        type=str,
        default='data/resume_data.yaml',
        help="Путь к YAML файлу с данными (по умолчанию: data/resume_data.yaml)"
    )
    parser.add_argument(
        '--template',
        type=str,
        default='base.html',
        help="Название HTML шаблона (по умолчанию: base.html)"
    )
    parser.add_argument(
        '--output-html',
        type=str,
        default='output/resume.html',
        help="Путь для сохранения сгенерированного HTML (по умолчанию: output/resume.html)"
    )
    parser.add_argument(
        '--output-pdf',
        type=str,
        default=None,
        help="Путь для сохранения PDF (опционально)"
    )

    args = parser.parse_args()

    if args.gui:
        # Запуск GUI
        try:
            from PyQt5 import QtWidgets  # лениво проверяем, что PyQt5 установлен
        except ImportError:
            print("PyQt5 не установлен. Установите его: pip install PyQt5")
            sys.exit(1)
        run_gui()
    else:
        # Запуск CLI-режима
        try:
            # 1. Загрузка данных
            data = load_data(args.data)

            # 2. Валидация + проверка изображений
            validate_data(data)
            check_images(data)

            # 3. Обогащение данных возрастом
            data = enrich_data_with_age(data)

            # 4. Генерация резюме
            generate_resume(
                data=data,
                template_dir=os.path.join(os.path.dirname(__file__), "templates"),
                template_name=args.template,
                output_html=args.output_html,
                output_pdf=args.output_pdf
            )
            logging.info("Резюме успешно сгенерировано.")
        except Exception as e:
            logging.error(f"Процесс генерации резюме завершился с ошибкой: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
