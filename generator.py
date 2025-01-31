# resume_generator/generator.py

import os
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape
from .data_handler import enrich_data_with_age

# Опционально: для генерации PDF
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False


# -------------------------------------
# Глобальный кэш окружений Jinja2
_jinja_env_cache = {}
# -------------------------------------


def get_jinja_env(template_dir):
    """
    Возвращает (или создаёт) Environment для указанной директории шаблонов.
    Благодаря кэшу не пересоздаём окружение при повторных вызовах.
    """
    if template_dir not in _jinja_env_cache:
        env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )
        _jinja_env_cache[template_dir] = env
    return _jinja_env_cache[template_dir]


def generate_resume(
    data: dict,
    template_dir: str,
    template_name: str,
    output_html: str,
    output_pdf: str = None
) -> None:
    """
    Генерирует 2 версии резюме:
      - Обычное (полное) HTML => output_html
      - При необходимости PDF-версию:
          * Сначала генерируется отдельный HTML (временный, "pdf_mode = True")
          * Затем WeasyPrint превращает этот HTML в output_pdf

    :param data: Словарь данных резюме (уже прошедший валидацию).
    :param template_dir: Папка, где лежат шаблоны HTML.
    :param template_name: Имя (файл) шаблона.
    :param output_html: Путь для сохранения итогового «полного» HTML.
    :param output_pdf: (опционально) Путь для сохранения PDF, если нужен.
    :raises Exception: При любой ошибке рендеринга или записи.
    """
    try:
        # Обогащаем данные возрастом
        data = enrich_data_with_age(data)
        # 1. Создадим директорию для output_html, если её нет
        os.makedirs(os.path.dirname(output_html), exist_ok=True)
        
        # 2. Получим окружение Jinja2
        env = get_jinja_env(template_dir)
        template = env.get_template(template_name)

        # 3. Сначала всегда генерируем "обычный" HTML (pdf_mode=False)
        rendered_html_normal = template.render(data, pdf_mode=False)

        with open(output_html, 'w', encoding='utf-8') as f:
            f.write(rendered_html_normal)

        logging.info(f"[generate_resume] Полная версия HTML сохранена в '{output_html}'")

        # 4. Если пользователь просил PDF...
        if output_pdf:
            # Проверим, установлена ли WeasyPrint
            if WEASYPRINT_AVAILABLE:
                # Создадим отдельный HTML (pdf_mode=True)
                # Можно назвать его `output_html_pdf = output_html.replace('.html','_pdf.html')`
                # или, например, "output/resume_pdf.html"
                pdf_html_name = os.path.splitext(output_html)[0] + "_pdf.html"
                pdf_html_path = pdf_html_name

                # Генерируем "pdf-версию" HTML
                rendered_html_pdf = template.render(data, pdf_mode=True)

                with open(pdf_html_path, 'w', encoding='utf-8') as f:
                    f.write(rendered_html_pdf)
                
                logging.info(f"[generate_resume] Упрощённый HTML для PDF сохранён в '{pdf_html_path}'")

                # Теперь превращаем этот html в PDF
                HTML(
                    pdf_html_path,
                    base_url=os.path.abspath(os.path.dirname(pdf_html_path))
                ).write_pdf(output_pdf)

                logging.info(f"[generate_resume] PDF-версия резюме сохранена в '{output_pdf}'")

            else:
                logging.error("[generate_resume] WeasyPrint не установлен. PDF не будет сгенерирован.")
                
    except Exception as e:
        logging.error(f"[generate_resume] Ошибка генерации резюме: {e}")
        raise
