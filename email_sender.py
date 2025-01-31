# resume_generator/email_sender.py

import os
import smtplib
import ssl
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication


def send_resume_by_email(
    sender_email: str,
    sender_password: str,
    recipients: list,
    subject: str,
    body_text: str,
    html_path: str = None,
    pdf_path: str = None,
    smtp_server: str = "smtp.gmail.com",
    smtp_port: int = 587
):
    """
    Отправляет письмо с вложением(ями) на список email-адресов.
    
    :param sender_email: Отправитель (например, ваша GMail-почта).
    :param sender_password: Пароль или SMTP App Password.
    :param recipients: Список email-адресов получателей.
    :param subject: Тема письма.
    :param body_text: Текст письма (plain text).
    :param html_path: Путь к HTML-файлу резюме (если нужно вложение).
    :param pdf_path:  Путь к PDF-файлу резюме (если нужно вложение).
    :param smtp_server: SMTP-сервер (по умолчанию GMail).
    :param smtp_port: Порт SMTP (по умолчанию 587 для STARTTLS).
    """
    if not recipients:
        logging.warning("Список получателей пуст. Отправка отменена.")
        return

    logging.info(f"Начало отправки писем на адреса: {', '.join(recipients)}")

    # Создаём объект письма
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    # Добавляем текстовую часть
    msg.attach(MIMEText(body_text, "plain", _charset="utf-8"))

    # Прикрепляем HTML-файл (если указали)
    if html_path and os.path.exists(html_path):
        try:
            with open(html_path, "rb") as f:
                part = MIMEApplication(f.read(), _subtype="html")
            part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(html_path)}"')
            msg.attach(part)
            logging.info(f"HTML-файл '{html_path}' добавлен во вложение.")
        except Exception as e:
            logging.error(f"Не удалось вложить HTML-файл '{html_path}': {e}")

    # Прикрепляем PDF-файл (если указали)
    if pdf_path and os.path.exists(pdf_path):
        try:
            with open(pdf_path, "rb") as f:
                part = MIMEApplication(f.read(), _subtype="pdf")
            part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(pdf_path)}"')
            msg.attach(part)
            logging.info(f"PDF-файл '{pdf_path}' добавлен во вложение.")
        except Exception as e:
            logging.error(f"Не удалось вложить PDF-файл '{pdf_path}': {e}")

    # Настраиваем SMTP (используем STARTTLS)
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        logging.info("Письма успешно отправлены.")
    except Exception as e:
        logging.error(f"Ошибка при отправке писем: {e}")
        raise
