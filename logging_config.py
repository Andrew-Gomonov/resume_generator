# resume_generator/logging_config.py

import logging
import logging.config
import yaml
import os

def setup_logging(default_path='logging_config.yaml', default_level=logging.INFO, env_key='LOG_CFG'):
    """Настройка логирования из конфигурационного файла YAML."""
    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, 'rt', encoding='utf-8') as f:
            config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)
        logging.warning(f"Файл конфигурации логирования '{path}' не найден. Используются настройки по умолчанию.")
