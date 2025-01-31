# resume_generator/gui.py

import logging
import os
import re
import signal
import sys

import yaml
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve, QSize, QUrl, QDate  # Добавлено QDate
)
from PyQt5.QtGui import (
    QIcon, QFont, QValidator, QColor, QTextCharFormat, QSyntaxHighlighter, QKeySequence, QPixmap
)
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QTextEdit, QPushButton,
    QFileDialog, QVBoxLayout, QHBoxLayout, QMessageBox, QComboBox, QProgressBar,
    QTabWidget, QFormLayout, QSpinBox, QListWidget, QListWidgetItem, QDialog,
    QDialogButtonBox, QInputDialog, QGroupBox, QMenuBar, QAction, QStatusBar, QDateEdit  # Добавлено
)

# Попытка импорта QWebEngineView (предпросмотр HTML). Если нет — preview не работает.
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
except ImportError:
    QWebEngineView = None

# Локальные импорты из проекта
from .data_handler import load_data, validate_data, check_images
from .generator import generate_resume
from .logging_config import setup_logging


###############################################
# ВАЛИДАТОРЫ, КЛАССЫ ДЛЯ ФОРМ, ДОП. КОМПОНЕНТЫ
###############################################

def is_valid_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email)

def is_valid_url(url):
    pattern = r'^(http://|https://)?[\w.-]+(\.[\w\.-]+)+[/#?]?.*$'
    return re.match(pattern, url)

class EmailValidator(QValidator):
    def validate(self, input_str, pos):
        if is_valid_email(input_str):
            return (QValidator.Acceptable, input_str, pos)
        elif input_str == "":
            return (QValidator.Intermediate, input_str, pos)
        else:
            return (QValidator.Invalid, input_str, pos)

class URLValidator(QValidator):
    def validate(self, input_str, pos):
        if is_valid_url(input_str):
            return (QValidator.Acceptable, input_str, pos)
        elif input_str == "":
            return (QValidator.Intermediate, input_str, pos)
        else:
            return (QValidator.Invalid, input_str, pos)

class YAMLHighlighter(QSyntaxHighlighter):
    """
    Подсветка ключевых слов в YAML-редакторе.
    """
    def __init__(self, parent=None):
        super(YAMLHighlighter, self).__init__(parent)
        self.highlighting_rules = []

        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#81A1C1"))
        keyword_format.setFontWeight(QFont.Bold)

        keywords = [
            r'\bname\b', r'\bposition\b', r'\bemail\b', r'\bphone\b',
            r'\blinkedin\b', r'\bgithub\b', r'\bsummary\b',
            r'\bexperience\b', r'\beducation\b', r'\bskills\b',
            r'\blanguages\b', r'\bprojects\b', r'\bcertifications\b',
            r'\bblocks\b'
        ]
        import re
        for word in keywords:
            pattern = re.compile(word)
            self.highlighting_rules.append((pattern, keyword_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.highlighting_rules:
            for match in pattern.finditer(text):
                start, end = match.span()
                self.setFormat(start, end - start, fmt)


###############################################
# ПОТОК ДЛЯ ФОНОВОЙ ГЕНЕРАЦИИ
###############################################

class ResumeGeneratorThread(QThread):
    """
    Отдельный поток для генерации резюме (чтобы не «морозить» GUI).
    """
    progress = pyqtSignal(int, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, data, template_dir, template_name, output_html, output_pdf):
        super().__init__()
        self.data = data
        self.template_dir = template_dir
        self.template_name = template_name
        self.output_html = output_html
        self.output_pdf = output_pdf

    def run(self):
        try:
            self.progress.emit(10, "Валидация данных...")
            validate_data(self.data)

            self.progress.emit(30, "Проверка изображений...")
            check_images(self.data)

            self.progress.emit(50, "Генерация HTML резюме...")
            generate_resume(
                data=self.data,
                template_dir=self.template_dir,
                template_name=self.template_name,
                output_html=self.output_html,
                output_pdf=self.output_pdf
            )

            if self.output_pdf:
                self.progress.emit(80, "Генерация PDF резюме...")

            self.progress.emit(100, "Генерация резюме завершена.")
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit()


class GUIHandler(logging.Handler):
    """
    Специальный logging.Handler, перенаправляющий сообщения в GUI через сигнал.
    """
    def __init__(self, signal):
        super().__init__()
        self.signal = signal

    def emit(self, record):
        msg = self.format(record)
        self.signal.emit(msg)


###############################################
# КЛАСС ДИАЛОГА «ДОБАВИТЬ БЛОК» ДЛЯ БЛОКОВОГО РЕДАКТОРА
###############################################
### BLOCK EDITOR: новый диалог
class BlockDialog(QDialog):
    """
    Пример диалога для выбора типа блока (заголовок, текст, изображение) и ввода содержания.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Добавить блок")
        self.setModal(True)
        layout = QFormLayout()

        # Тип блока
        self.block_type_combo = QComboBox()
        self.block_type_combo.addItems(["Заголовок", "Текст", "Изображение"])
        layout.addRow("Тип блока:", self.block_type_combo)

        # Содержимое блока
        self.content_edit = QTextEdit()
        self.content_edit.setFixedHeight(80)
        layout.addRow("Содержимое:", self.content_edit)

        # Кнопки
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setLayout(layout)

    def get_block_data(self):
        """
        Возвращает dict вида:
        {
          "type": "header"/"text"/"image",
          "content": "что ввёл пользователь"
        }
        """
        block_type = self.block_type_combo.currentText()
        # Согласуем английские названия для логики (или оставьте на русском)
        if block_type == "Заголовок":
            internal_type = "header"
        elif block_type == "Текст":
            internal_type = "text"
        else:
            internal_type = "image"

        return {
            "type": internal_type,
            "content": self.content_edit.toPlainText()
        }


###############################################
# ОСНОВНОЕ КЛАСС-ОКНО ГРАФИЧЕСКОГО ИНТЕРФЕЙСА
###############################################

class ResumeGeneratorGUI(QWidget):
    log_signal = pyqtSignal(str)  # Cигнал для перенаправления логов в текстовое поле

    def __init__(self):
        super().__init__()
        self.init_ui()

        # Логические атрибуты
        self.generator_thread = None

        # Подключаем сигнал логирования к методу вывода в GUI
        self.log_signal.connect(self.log_message)

        # Разрешаем Drag & Drop
        self.setAcceptDrops(True)

    ###############################################
    # ИНИЦИАЛИЗАЦИЯ ИНТЕРФЕЙСА
    ###############################################

    def init_ui(self):
        """
        Создаём все основные виджеты, вкладки, меню, кнопки, размещаем их на форме.
        """
        self.load_stylesheet()

        # Основные настройки окна
        self.setWindowTitle("Генератор Резюме")
        self.setWindowIcon(QIcon("resume_generator/icons/app_icon.png"))  # Проверьте путь к иконке
        self.setGeometry(100, 100, 1000, 800)

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Менюбар
        menu_bar = QMenuBar()
        main_layout.setMenuBar(menu_bar)

        file_menu = menu_bar.addMenu("Файл")
        exit_action = QAction("Выход", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = menu_bar.addMenu("Справка")
        about_action = QAction("О приложении", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

        # Шапка с логотипом и заголовком
        header_layout = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QIcon("icons/logo.png").pixmap(50, 50))
        header_layout.addWidget(logo)
        title = QLabel("Генератор Резюме")
        title.setObjectName("titleLabel")
        title.setFont(QFont("Arial", 20))
        header_layout.addWidget(title)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Группбокс: Настройки генерации
        settings_group = QGroupBox("Настройки Генерации")
        settings_layout = QFormLayout()

        # Поле YAML-файла
        self.data_input = QLineEdit()
        self.data_browse = QPushButton()
        self.data_browse.setIcon(QIcon.fromTheme("document-open"))
        self.data_browse.setToolTip("Выбрать YAML файл данных")
        self.data_browse.clicked.connect(self.browse_data_file)

        data_layout = QHBoxLayout()
        data_layout.addWidget(self.data_input)
        data_layout.addWidget(self.data_browse)
        settings_layout.addRow("Файл данных (YAML):", data_layout)

        # Поле выбора шаблона
        self.template_combo = QComboBox()
        self.load_templates()
        settings_layout.addRow("Шаблон:", self.template_combo)

        # Поле для HTML
        self.output_html_input = QLineEdit()
        self.output_html_browse = QPushButton()
        self.output_html_browse.setIcon(QIcon.fromTheme("document-save"))
        self.output_html_browse.setToolTip("Выбрать путь для сохранения HTML")
        self.output_html_browse.clicked.connect(self.browse_output_html)

        output_html_layout = QHBoxLayout()
        output_html_layout.addWidget(self.output_html_input)
        output_html_layout.addWidget(self.output_html_browse)
        settings_layout.addRow("Выходной HTML файл:", output_html_layout)

        # Поле для PDF
        self.output_pdf_input = QLineEdit()
        self.output_pdf_browse = QPushButton()
        self.output_pdf_browse.setIcon(QIcon.fromTheme("document-save"))
        self.output_pdf_browse.setToolTip("Выбрать путь для сохранения PDF (опционально)")
        self.output_pdf_browse.clicked.connect(self.browse_output_pdf)

        output_pdf_layout = QHBoxLayout()
        output_pdf_layout.addWidget(self.output_pdf_input)
        output_pdf_layout.addWidget(self.output_pdf_browse)
        settings_layout.addRow("Выходной PDF файл (опционально):", output_pdf_layout)

        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)

        # Вкладки
        self.tabs = QTabWidget()

        ###########################################
        # PERSONAL DATA (первая вкладка)
        ###########################################
        self.personal_tab = QWidget()
        self.init_personal_tab()
        # Вставляем эту вкладку ПЕРВОЙ (с индексом 0)
        self.tabs.insertTab(0, self.personal_tab, "Личные данные")

        # Остальные вкладки
        self.block_editor_tab = QWidget()
        self.experience_tab = QWidget()
        self.education_tab = QWidget()
        self.skills_tab = QWidget()
        self.languages_tab = QWidget()
        self.projects_tab = QWidget()
        self.certifications_tab = QWidget()
        self.yaml_tab = QWidget()

        self.tabs.addTab(self.block_editor_tab, "Блоковый редактор")
        self.tabs.addTab(self.experience_tab, "Опыт работы")
        self.tabs.addTab(self.education_tab, "Образование")
        self.tabs.addTab(self.skills_tab, "Навыки")
        self.tabs.addTab(self.languages_tab, "Языки")
        self.tabs.addTab(self.projects_tab, "Проекты")
        self.tabs.addTab(self.certifications_tab, "Сертификаты")
        self.tabs.addTab(self.yaml_tab, "Редактор YAML")

        # Инициализация вкладок
        self.init_block_editor_tab()
        self.init_experience_tab()
        self.init_education_tab()
        self.init_skills_tab()
        self.init_languages_tab()
        self.init_projects_tab()
        self.init_certifications_tab()
        self.init_yaml_tab()

        # NEW: Вкладка «Предпросмотр» (если PyQtWebEngine установлена)
        if QWebEngineView:
            self.preview_tab = QWidget()
            self.tabs.addTab(self.preview_tab, "Предпросмотр")
            self.init_preview_tab()
        else:
            self.preview_tab = None

        main_layout.addWidget(self.tabs)

        # Кнопки загрузки/сохранения
        buttons_layout = QHBoxLayout()
        load_data_button = QPushButton("Загрузить данные из YAML")
        load_data_button.setIcon(QIcon.fromTheme("document-open"))
        load_data_button.setToolTip("Загрузить данные из выбранного YAML файла")
        load_data_button.clicked.connect(self.load_data_into_forms)
        load_data_button.setShortcut(QKeySequence("Ctrl+O"))

        save_data_button = QPushButton("Сохранить данные в YAML")
        save_data_button.setIcon(QIcon.fromTheme("document-save"))
        save_data_button.setToolTip("Сохранить текущие данные в YAML файл")
        save_data_button.clicked.connect(self.save_data_from_forms)
        save_data_button.setShortcut(QKeySequence("Ctrl+S"))

        buttons_layout.addWidget(load_data_button)
        buttons_layout.addWidget(save_data_button)
        buttons_layout.addStretch()
        main_layout.addLayout(buttons_layout)

        # Доп. кнопки
        extra_buttons_layout = QHBoxLayout()
        clear_data_button = QPushButton("Очистить все данные")
        clear_data_button.setIcon(QIcon.fromTheme("edit-clear"))
        clear_data_button.setToolTip("Очистить все поля и списки")
        clear_data_button.clicked.connect(self.clear_all_data)
        extra_buttons_layout.addWidget(clear_data_button)

        # Поиск по опыту
        search_experience_input = QLineEdit()
        search_experience_input.setPlaceholderText("Поиск по опыту работы...")
        search_experience_input.textChanged.connect(self.search_experience)
        extra_buttons_layout.addWidget(search_experience_input)

        extra_buttons_layout.addStretch()
        main_layout.addLayout(extra_buttons_layout)

        # Кнопка генерации
        self.generate_button = QPushButton("Сгенерировать резюме")
        self.generate_button.setIcon(QIcon.fromTheme("system-run"))
        self.generate_button.setToolTip("Начать процесс генерации резюме")
        self.generate_button.clicked.connect(self.generate_resume)
        self.generate_button.setShortcut(QKeySequence("Ctrl+G"))
        self.add_hover_animation(self.generate_button)
        main_layout.addWidget(self.generate_button)

        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumHeight(20)
        main_layout.addWidget(self.progress_bar)

        # Лог сообщений
        log_group = QGroupBox("Лог сообщений")
        log_layout = QVBoxLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(150)
        log_layout.addWidget(self.log_output)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        # Статусбар
        self.status_bar = QStatusBar()
        main_layout.addWidget(self.status_bar)

    def load_stylesheet(self):
        """
        Загрузка стиля приложения из styles.qss (если есть).
        """
        stylesheet_path = os.path.join(os.path.dirname(__file__), "styles", "styles.qss")
        if os.path.exists(stylesheet_path):
            with open(stylesheet_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        else:
            logging.warning(f"Файл стилей '{stylesheet_path}' не найден. Используются стандартные стили.")

    def load_templates(self):
        """
        Загрузка списка шаблонов из папки templates.
        """
        templates_dir = os.path.join(os.path.dirname(__file__), "templates")
        if not os.path.isdir(templates_dir):
            QMessageBox.critical(self, "Ошибка", f"Директория шаблонов '{templates_dir}' не найдена.")
            sys.exit(1)
        templates = [f for f in os.listdir(templates_dir) if f.endswith('.html')]
        if not templates:
            QMessageBox.critical(self, "Ошибка", f"В директории '{templates_dir}' не найдено HTML шаблонов.")
            sys.exit(1)
        self.template_combo.addItems(templates)

        # Устанавливаем 'base.html' как выбранный по умолчанию, если он существует
        if 'base.html' in templates:
            self.template_combo.setCurrentText('base.html')
            logging.info("'base.html' установлен как стандартный шаблон.")
        else:
            logging.warning("'base.html' не найден среди доступных шаблонов.")

    ###########################################
    # BLOCK EDITOR: ИНИЦИАЛИЗАЦИЯ
    ###########################################
    def init_block_editor_tab(self):
        layout = QVBoxLayout()

        self.block_list = QListWidget()
        layout.addWidget(self.block_list)

        # Кнопки управления
        btn_layout = QHBoxLayout()

        add_block_btn = QPushButton("Добавить блок")
        add_block_btn.clicked.connect(self.add_block)
        btn_layout.addWidget(add_block_btn)

        remove_block_btn = QPushButton("Удалить блок")
        remove_block_btn.clicked.connect(self.remove_block)
        btn_layout.addWidget(remove_block_btn)

        move_up_btn = QPushButton("Вверх")
        move_up_btn.clicked.connect(self.move_block_up)
        btn_layout.addWidget(move_up_btn)

        move_down_btn = QPushButton("Вниз")
        move_down_btn.clicked.connect(self.move_block_down)
        btn_layout.addWidget(move_down_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.block_editor_tab.setLayout(layout)

    def add_block(self):
        dialog = BlockDialog()
        if dialog.exec_() == QDialog.Accepted:
            block_data = dialog.get_block_data()
            item_text = f"[{block_data['type']}] {block_data['content']}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, block_data)
            self.block_list.addItem(item)

    def remove_block(self):
        selected_items = self.block_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Предупреждение", "Пожалуйста, выберите блок для удаления.")
            return
        reply = QMessageBox.question(
            self, 'Подтверждение удаления',
            f"Вы уверены, что хотите удалить {len(selected_items)} выбранных блоков?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for item in selected_items:
                self.block_list.takeItem(self.block_list.row(item))

    def move_block_up(self):
        row = self.block_list.currentRow()
        if row > 0:
            item = self.block_list.takeItem(row)
            self.block_list.insertItem(row - 1, item)
            self.block_list.setCurrentItem(item)

    def move_block_down(self):
        row = self.block_list.currentRow()
        if row < self.block_list.count() - 1 and row != -1:
            item = self.block_list.takeItem(row)
            self.block_list.insertItem(row + 1, item)
            self.block_list.setCurrentItem(item)

    ###############################################
    # ДРУГИЕ ВКЛАДКИ (НЕ МЕНЯЛОСЬ, кроме порядка)
    ###############################################

    # Внутри класса ResumeGeneratorGUI

    def init_personal_tab(self):
        layout = QFormLayout()
        self.name_input = QLineEdit()
        self.position_input = QLineEdit()
        self.email_input = QLineEdit()
        self.email_input.setValidator(EmailValidator())
        self.phone_input = QLineEdit()
        self.linkedin_input = QLineEdit()
        self.linkedin_input.setValidator(URLValidator())
        self.github_input = QLineEdit()
        self.github_input.setValidator(URLValidator())
        self.summary_input = QTextEdit()
        self.summary_input.setFixedHeight(100)
        
        # Новое поле для даты рождения
        self.dob_input = QDateEdit()
        self.dob_input.setCalendarPopup(True)
        self.dob_input.setDisplayFormat("yyyy-MM-dd")
        self.dob_input.setDate(QDate(1990, 1, 1))  # Установите значение по умолчанию при необходимости

        # Новые виджеты для фото профиля
        self.profile_image_label = QLabel()
        self.profile_image_label.setFixedSize(150, 150)  # Размер изображения
        self.profile_image_label.setStyleSheet("border: 1px solid #ccc;")
        self.profile_image_label.setAlignment(Qt.AlignCenter)
        self.profile_image_label.setText("Фото профиля")

        self.change_image_button = QPushButton("Изменить фото")
        self.change_image_button.clicked.connect(self.change_profile_image)

        # Размещение фото и кнопки в горизонтальном Layout
        image_layout = QHBoxLayout()
        image_layout.addWidget(self.profile_image_label)
        image_layout.addWidget(self.change_image_button)

        # Добавление элементов в форму
        layout.addRow("Имя:", self.name_input)
        layout.addRow("Дата рождения:", self.dob_input)  # Добавлено
        layout.addRow("Должность:", self.position_input)
        layout.addRow("Email:", self.email_input)
        layout.addRow("Телефон:", self.phone_input)
        layout.addRow("LinkedIn:", self.linkedin_input)
        layout.addRow("GitHub:", self.github_input)
        layout.addRow("Краткое описание:", self.summary_input)
        layout.addRow("Фото профиля:", image_layout)  # Добавлено

        self.personal_tab.setLayout(layout)

    def change_profile_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение профиля", "", "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_path:
            # Отображаем выбранное изображение
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(self.profile_image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.profile_image_label.setPixmap(pixmap)
                self.profile_image_label.setText("")  # Убираем текст

                # Обновляем данные YAML
                yaml_text = self.yaml_editor.toPlainText()
                try:
                    data = yaml.safe_load(yaml_text)
                    if not data:
                        data = {}
                except:
                    data = {}

                # Предлагаем пользователю выбрать тип изображения: URL или локальный путь
                choice, ok = QInputDialog.getItem(
                    self, "Тип изображения", "Выберите тип изображения:", ["URL", "Путь к файлу"], 0, False
                )
                if ok and choice:
                    if choice == "URL":
                        url, ok_url = QInputDialog.getText(
                            self, "Введите URL изображения", "URL изображения:"
                        )
                        if ok_url and url.strip():
                            data["profile_image"] = {
                                "type": "url",
                                "value": url.strip(),
                                "download": False
                            }
                    else:
                        # Если пользователь выбрал локальный путь, сохраняем путь к файлу
                        data["profile_image"] = {
                            "type": "path",
                            "value": file_path,
                            "download": False
                        }

                    # Обновляем YAML-редактор
                    self.yaml_editor.setPlainText(yaml.dump(data, allow_unicode=True))
                    QMessageBox.information(self, "Фото профиля", "Фото профиля успешно обновлено.")
                    logging.info("Фото профиля успешно обновлено.")
                else:
                    # Если пользователь отменил выбор типа, не сохраняем изменения
                    QMessageBox.warning(self, "Отмена", "Тип изображения не выбран. Изменение отменено.")
            else:
                QMessageBox.warning(self, "Неверный файл", "Выбранный файл не является изображением или не может быть открыт.")




    def init_experience_tab(self):
        layout = QVBoxLayout()
        self.experience_list = QListWidget()

        add_button = QPushButton("Добавить опыт")
        add_button.setIcon(QIcon.fromTheme("list-add"))
        add_button.clicked.connect(self.add_experience)

        remove_button = QPushButton("Удалить выбранный опыт")
        remove_button.setIcon(QIcon.fromTheme("list-remove"))
        remove_button.clicked.connect(self.remove_experience)

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(remove_button)
        buttons_layout.addStretch()

        layout.addWidget(self.experience_list)
        layout.addLayout(buttons_layout)
        self.experience_tab.setLayout(layout)

    def init_education_tab(self):
        layout = QVBoxLayout()
        self.education_list = QListWidget()

        add_button = QPushButton("Добавить образование")
        add_button.setIcon(QIcon.fromTheme("list-add"))
        add_button.clicked.connect(self.add_education)

        remove_button = QPushButton("Удалить выбранное образование")
        remove_button.setIcon(QIcon.fromTheme("list-remove"))
        remove_button.clicked.connect(self.remove_education)

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(remove_button)
        buttons_layout.addStretch()

        layout.addWidget(self.education_list)
        layout.addLayout(buttons_layout)
        self.education_tab.setLayout(layout)

    def init_skills_tab(self):
        layout = QVBoxLayout()
        self.skills_list = QListWidget()

        add_button = QPushButton("Добавить навык")
        add_button.setIcon(QIcon.fromTheme("list-add"))
        add_button.clicked.connect(self.add_skill)

        remove_button = QPushButton("Удалить выбранный навык")
        remove_button.setIcon(QIcon.fromTheme("list-remove"))
        remove_button.clicked.connect(self.remove_skill)

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(remove_button)
        buttons_layout.addStretch()

        layout.addWidget(self.skills_list)
        layout.addLayout(buttons_layout)
        self.skills_tab.setLayout(layout)

    def init_languages_tab(self):
        layout = QVBoxLayout()
        self.languages_list = QListWidget()

        add_button = QPushButton("Добавить язык")
        add_button.setIcon(QIcon.fromTheme("list-add"))
        add_button.clicked.connect(self.add_language)

        remove_button = QPushButton("Удалить выбранный язык")
        remove_button.setIcon(QIcon.fromTheme("list-remove"))
        remove_button.clicked.connect(self.remove_language)

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(remove_button)
        buttons_layout.addStretch()

        layout.addWidget(self.languages_list)
        layout.addLayout(buttons_layout)
        self.languages_tab.setLayout(layout)

    def init_projects_tab(self):
        layout = QVBoxLayout()
        self.projects_list = QListWidget()

        add_button = QPushButton("Добавить проект")
        add_button.setIcon(QIcon.fromTheme("list-add"))
        add_button.clicked.connect(self.add_project)

        remove_button = QPushButton("Удалить выбранный проект")
        remove_button.setIcon(QIcon.fromTheme("list-remove"))
        remove_button.clicked.connect(self.remove_project)

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(remove_button)
        buttons_layout.addStretch()

        layout.addWidget(self.projects_list)
        layout.addLayout(buttons_layout)
        self.projects_tab.setLayout(layout)

    def init_certifications_tab(self):
        layout = QVBoxLayout()
        self.certifications_list = QListWidget()

        add_button = QPushButton("Добавить сертификат")
        add_button.setIcon(QIcon.fromTheme("list-add"))
        add_button.clicked.connect(self.add_certification)

        remove_button = QPushButton("Удалить выбранный сертификат")
        remove_button.setIcon(QIcon.fromTheme("list-remove"))
        remove_button.clicked.connect(self.remove_certification)

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(remove_button)
        buttons_layout.addStretch()

        layout.addWidget(self.certifications_list)
        layout.addLayout(buttons_layout)
        self.certifications_tab.setLayout(layout)

    def init_yaml_tab(self):
        layout = QVBoxLayout()
        self.yaml_editor = QTextEdit()
        self.yaml_editor.setFont(QFont("Courier", 10))
        self.yaml_highlighter = YAMLHighlighter(self.yaml_editor)
        layout.addWidget(self.yaml_editor)

        # Кнопки YAML
        buttons_layout = QHBoxLayout()

        load_yaml_button = QPushButton("Загрузить YAML")
        load_yaml_button.setIcon(QIcon.fromTheme("document-open"))
        load_yaml_button.clicked.connect(self.load_yaml_into_editor)

        save_yaml_button = QPushButton("Сохранить YAML")
        save_yaml_button.setIcon(QIcon.fromTheme("document-save"))
        save_yaml_button.clicked.connect(self.save_yaml_from_editor)

        update_forms_button = QPushButton("Обновить формы из YAML")
        update_forms_button.setIcon(QIcon.fromTheme("view-refresh"))
        update_forms_button.clicked.connect(self.update_forms_from_yaml)

        buttons_layout.addWidget(load_yaml_button)
        buttons_layout.addWidget(save_yaml_button)
        buttons_layout.addWidget(update_forms_button)
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

        self.yaml_tab.setLayout(layout)

    def init_preview_tab(self):
        """
        Вкладка «Предпросмотр» с QWebEngineView (если PyQtWebEngine доступен).
        """
        layout = QVBoxLayout()

        self.webview = QWebEngineView()
        layout.addWidget(self.webview)

        refresh_button = QPushButton("Обновить предпросмотр")
        refresh_button.clicked.connect(self.refresh_preview)
        layout.addWidget(refresh_button)

        self.preview_tab.setLayout(layout)

    ###############################################
    # DRAG & DROP
    ###############################################

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            return

        urls = event.mimeData().urls()
        if not urls:
            return

        for url in urls:
            local_path = url.toLocalFile()
            if not local_path:
                continue

            extension = os.path.splitext(local_path)[1].lower()

            if extension in ['.yaml', '.yml']:
                self.data_input.setText(local_path)
                self.load_data_into_forms()
                QMessageBox.information(self, "Drag & Drop", f"Загружен файл данных: {local_path}")
            elif extension in ['.png', '.jpg', '.jpeg']:
                self.add_profile_image(local_path)
            else:
                QMessageBox.information(self, "Drag & Drop", f"Файл {local_path} не поддерживается.")

        event.acceptProposedAction()

    def add_profile_image(self, image_path):
        """
        Добавляем перетащенное изображение как profile_image в текущие данные (yaml_editor).
        """
        yaml_text = self.yaml_editor.toPlainText()
        try:
            data = yaml.safe_load(yaml_text)
            if not data:
                data = {}
        except:
            data = {}

        data["profile_image"] = {
            "type": "path",
            "value": image_path,
            "download": False
        }

        self.yaml_editor.setPlainText(yaml.dump(data, allow_unicode=True))
        QMessageBox.information(self, "Изображение добавлено", f"Изображение профиля: {image_path}")

    ###############################################
    # МЕТОДЫ: ЗАГРУЗКА / СОХРАНЕНИЕ / ОБНОВЛЕНИЕ
    ###############################################

    def browse_data_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите YAML файл данных", "", "YAML Files (*.yaml *.yml)"
        )
        if file_path:
            self.data_input.setText(file_path)

    def browse_output_html(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Укажите путь для выходного HTML файла",
            "resume.html", "HTML Files (*.html *.htm)"
        )
        if file_path:
            self.output_html_input.setText(file_path)

    def browse_output_pdf(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Укажите путь для выходного PDF файла",
            "resume.pdf", "PDF Files (*.pdf)"
        )
        if file_path:
            self.output_pdf_input.setText(file_path)

    def load_data_into_forms(self):
        data_file = self.data_input.text().strip()
        if not data_file or not os.path.isfile(data_file):
            QMessageBox.warning(self, "Предупреждение", "Пожалуйста, выберите корректный YAML файл данных.")
            return
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            logging.info(f"Данные успешно загружены из {data_file}")

            # 1. Блоки
            self.block_list.clear()
            blocks = data.get('blocks', [])
            for block in blocks:
                item_text = f"[{block['type']}] {block['content']}"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, block)
                self.block_list.addItem(item)

            # 2. Личные данные
            self.name_input.setText(data.get('name', ''))
            self.dob_input.setDate(QDate.fromString(data.get('date_of_birth', '1990-01-01'), "yyyy-MM-dd"))  # Добавлено
            self.position_input.setText(data.get('position', ''))
            self.email_input.setText(data.get('email', ''))
            self.phone_input.setText(data.get('phone', ''))
            self.linkedin_input.setText(data.get('linkedin', ''))
            self.github_input.setText(data.get('github', ''))
            self.summary_input.setPlainText(data.get('summary', ''))

            # 3. Фото профиля
            profile_image = data.get('profile_image')
            if profile_image:
                img_type = profile_image.get('type')
                img_value = profile_image.get('value', '')
                if img_type == 'path' and os.path.isfile(img_value):
                    pixmap = QPixmap(img_value)
                    if not pixmap.isNull():
                        pixmap = pixmap.scaled(self.profile_image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.profile_image_label.setPixmap(pixmap)
                        self.profile_image_label.setText("")
                elif img_type == 'url':
                    # Вы можете реализовать загрузку изображения по URL, если необходимо
                    # Для упрощения мы пока просто выводим URL как текст
                    self.profile_image_label.setText("URL: " + img_value)
                else:
                    self.profile_image_label.setText("Фото профиля не найдено.")

            # 4. Опыт
            self.experience_list.clear()
            for exp in data.get('experience', []):
                item_text = f"{exp['title']} в {exp['company']} ({exp['start_date']} - {exp['end_date']})"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, exp)
                self.experience_list.addItem(item)

            # 5. Образование
            self.education_list.clear()
            for edu in data.get('education', []):
                item_text = f"{edu['degree']} в {edu['institution']} ({edu['start_date']} - {edu['end_date']})"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, edu)
                self.education_list.addItem(item)

            # 6. Навыки
            self.skills_list.clear()
            for skill in data.get('skills', []):
                item_text = f"{skill['name']} ({skill['level']}%)"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, skill)
                self.skills_list.addItem(item)

            # 7. Языки
            self.languages_list.clear()
            for lang in data.get('languages', []):
                self.languages_list.addItem(lang)

            # 8. Проекты
            self.projects_list.clear()
            for proj in data.get('projects', []):
                item_text = f"{proj['name']} - {proj['description']} ({proj['link']})"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, proj)
                self.projects_list.addItem(item)

            # 9. Сертификаты
            self.certifications_list.clear()
            for cert in data.get('certifications', []):
                item_text = f"{cert['title']} - {cert['institution']} ({cert['date']})"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, cert)
                self.certifications_list.addItem(item)

            # Обновим YAML-редактор
            self.yaml_editor.setPlainText(yaml.dump(data, allow_unicode=True))

            self.log_message("Данные успешно загружены в формы.")
            self.status_bar.showMessage("Данные загружены.", 5000)
        except Exception as e:
            logging.error(f"Ошибка при загрузке данных: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные: {e}")

    def save_data_from_forms(self):
        data = {}

        # 1. Блоки
        data['blocks'] = []
        for index in range(self.block_list.count()):
            item = self.block_list.item(index)
            block = item.data(Qt.UserRole)
            data['blocks'].append(block)

        # 2. Личные данные
        data['name'] = self.name_input.text()
        data['position'] = self.position_input.text()
        data['date_of_birth'] = self.dob_input.date().toString("yyyy-MM-dd")  # Добавлено
        data['email'] = self.email_input.text()
        data['phone'] = self.phone_input.text()
        data['linkedin'] = self.linkedin_input.text()
        data['github'] = self.github_input.text()
        data['summary'] = self.summary_input.toPlainText()

        # 3. Фото профиля
        yaml_text = self.yaml_editor.toPlainText()
        try:
            yaml_data = yaml.safe_load(yaml_text)
            if 'profile_image' in yaml_data:
                data['profile_image'] = yaml_data['profile_image']
        except:
            pass

        # 4. Опыт
        data['experience'] = []
        for index in range(self.experience_list.count()):
            item = self.experience_list.item(index)
            exp = item.data(Qt.UserRole)
            data['experience'].append(exp)

        # 5. Образование
        data['education'] = []
        for index in range(self.education_list.count()):
            item = self.education_list.item(index)
            edu = item.data(Qt.UserRole)
            data['education'].append(edu)

        # 6. Навыки
        data['skills'] = []
        for index in range(self.skills_list.count()):
            item = self.skills_list.item(index)
            skill = item.data(Qt.UserRole)
            data['skills'].append(skill)

        # 7. Языки
        data['languages'] = []
        for index in range(self.languages_list.count()):
            item = self.languages_list.item(index)
            data['languages'].append(item.text())

        # 8. Проекты
        data['projects'] = []
        for index in range(self.projects_list.count()):
            item = self.projects_list.item(index)
            proj = item.data(Qt.UserRole)
            data['projects'].append(proj)

        # 9. Сертификаты
        data['certifications'] = []
        for index in range(self.certifications_list.count()):
            item = self.certifications_list.item(index)
            cert = item.data(Qt.UserRole)
            data['certifications'].append(cert)

        # Обновляем YAML-редактор
        self.yaml_editor.setPlainText(yaml.dump(data, allow_unicode=True))

        # Диалог сохранения
        output_yaml_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить YAML файл", "resume_data.yaml", "YAML Files (*.yaml *.yml)"
        )
        if output_yaml_path:
            try:
                with open(output_yaml_path, 'w', encoding='utf-8') as f:
                    yaml.dump(data, f, allow_unicode=True)
                logging.info(f"Данные успешно сохранены в {output_yaml_path}")
                QMessageBox.information(self, "Успех", f"Данные успешно сохранены в {output_yaml_path}")
                self.status_bar.showMessage("Данные сохранены.", 5000)
            except Exception as e:
                logging.error(f"Ошибка при сохранении данных: {e}")
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить данные: {e}")

    def clear_all_data(self):
        reply = QMessageBox.question(
            self, 'Подтверждение очистки',
            "Вы уверены, что хотите очистить все данные?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            # 1. Блоки
            self.block_list.clear()

            # 2. Личные данные
            self.name_input.clear()
            self.position_input.clear()
            self.email_input.clear()
            self.phone_input.clear()
            self.linkedin_input.clear()
            self.github_input.clear()
            self.summary_input.clear()

            # Списки
            self.experience_list.clear()
            self.education_list.clear()
            self.skills_list.clear()
            self.languages_list.clear()
            self.projects_list.clear()
            self.certifications_list.clear()

            # YAML
            self.yaml_editor.clear()

            self.log_message("Все данные были очищены.")
            self.status_bar.showMessage("Все данные были очищены.", 5000)

    ###############################################
    # МЕТОДЫ: РАБОТА С YAML-РЕДАКТОРОМ
    ###############################################

    def load_yaml_into_editor(self):
        data_file = self.data_input.text().strip()
        if not data_file or not os.path.isfile(data_file):
            QMessageBox.warning(self, "Предупреждение", "Пожалуйста, выберите корректный YAML файл данных.")
            return
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                data = f.read()
            self.yaml_editor.setPlainText(data)
            logging.info(f"YAML данные загружены в редактор из {data_file}")
            self.status_bar.showMessage("YAML данные загружены в редактор.", 5000)
        except Exception as e:
            logging.error(f"Ошибка при загрузке YAML в редактор: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить YAML: {e}")

    def save_yaml_from_editor(self):
        yaml_text = self.yaml_editor.toPlainText()
        try:
            data = yaml.safe_load(yaml_text)
            validate_data(data)
            check_images(data)

            output_yaml_path, _ = QFileDialog.getSaveFileName(
                self, "Сохранить YAML файл",
                "resume_data.yaml", "YAML Files (*.yaml *.yml)"
            )
            if output_yaml_path:
                with open(output_yaml_path, 'w', encoding='utf-8') as f:
                    yaml.dump(data, f, allow_unicode=True)
                logging.info(f"YAML данные успешно сохранены в {output_yaml_path}")
                QMessageBox.information(self, "Успех", f"YAML данные успешно сохранены в {output_yaml_path}")
                self.status_bar.showMessage("YAML данные сохранены.", 5000)
        except Exception as e:
            logging.error(f"Ошибка при сохранении YAML из редактора: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить YAML: {e}")

    def update_forms_from_yaml(self):
        yaml_text = self.yaml_editor.toPlainText()
        try:
            data = yaml.safe_load(yaml_text)
            validate_data(data)
            check_images(data)

            # 1. Блоки
            self.block_list.clear()
            for block in data.get('blocks', []):
                item_text = f"[{block['type']}] {block['content']}"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, block)
                self.block_list.addItem(item)

            # 2. Личные данные
            self.name_input.setText(data.get('name', ''))
            self.position_input.setText(data.get('position', ''))
            self.email_input.setText(data.get('email', ''))
            self.phone_input.setText(data.get('phone', ''))
            self.linkedin_input.setText(data.get('linkedin', ''))
            self.github_input.setText(data.get('github', ''))
            self.summary_input.setPlainText(data.get('summary', ''))

            # 3. Опыт
            self.experience_list.clear()
            for exp in data.get('experience', []):
                item_text = f"{exp['title']} в {exp['company']} ({exp['start_date']} - {exp['end_date']})"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, exp)
                self.experience_list.addItem(item)

            # 4. Образование
            self.education_list.clear()
            for edu in data.get('education', []):
                item_text = f"{edu['degree']} в {edu['institution']} ({edu['start_date']} - {edu['end_date']})"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, edu)
                self.education_list.addItem(item)

            # 5. Навыки
            self.skills_list.clear()
            for skill in data.get('skills', []):
                item_text = f"{skill['name']} ({skill['level']}%)"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, skill)
                self.skills_list.addItem(item)

            # 6. Языки
            self.languages_list.clear()
            for lang in data.get('languages', []):
                self.languages_list.addItem(lang)

            # 7. Проекты
            self.projects_list.clear()
            for proj in data.get('projects', []):
                item_text = f"{proj['name']} - {proj['description']} ({proj['link']})"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, proj)
                self.projects_list.addItem(item)

            # 8. Сертификаты
            self.certifications_list.clear()
            for cert in data.get('certifications', []):
                item_text = f"{cert['title']} - {cert['institution']} ({cert['date']})"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, cert)
                self.certifications_list.addItem(item)

            self.log_message("Формы успешно обновлены на основе YAML данных.")
            self.status_bar.showMessage("Формы обновлены.", 5000)
        except Exception as e:
            logging.error(f"Ошибка при обновлении форм из YAML: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось обновить формы: {e}")

    ###############################################
    # ПРЕДПРОСМОТР (QWebEngineView)
    ###############################################

    def refresh_preview(self):
        """
        Подгружает уже сгенерированный HTML в веб-просмотр, не генерируя заново.
        """
        if not self.preview_tab or not self.webview:
            return

        output_html = self.output_html_input.text().strip()
        if output_html and os.path.isfile(output_html):
            self.webview.load(QUrl.fromLocalFile(os.path.abspath(output_html)))
        else:
            QMessageBox.warning(self, "Предупреждение", "HTML файл ещё не сгенерирован или не найден.")

    ###############################################
    # ОБРАБОТЧИКИ КНОПОК: ДОБАВЛЕНИЕ/УДАЛЕНИЕ ЭЛЕМЕНТОВ
    ###############################################

    def add_experience(self):
        dialog = ExperienceDialog()
        if dialog.exec_() == QDialog.Accepted:
            experience = dialog.get_data()
            item_text = f"{experience['title']} в {experience['company']} ({experience['start_date']} - {experience['end_date']})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, experience)
            self.experience_list.addItem(item)

    def remove_experience(self):
        selected_items = self.experience_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Предупреждение", "Пожалуйста, выберите опыт для удаления.")
            return
        reply = QMessageBox.question(
            self, 'Подтверждение удаления',
            f"Вы уверены, что хотите удалить {len(selected_items)} выбранных опыта?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for item in selected_items:
                self.experience_list.takeItem(self.experience_list.row(item))

    def add_education(self):
        dialog = EducationDialog()
        if dialog.exec_() == QDialog.Accepted:
            education = dialog.get_data()
            item_text = f"{education['degree']} в {education['institution']} ({education['start_date']} - {education['end_date']})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, education)
            self.education_list.addItem(item)

    def remove_education(self):
        selected_items = self.education_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Предупреждение", "Пожалуйста, выберите образование для удаления.")
            return
        reply = QMessageBox.question(
            self, 'Подтверждение удаления',
            f"Вы уверены, что хотите удалить {len(selected_items)} выбранных записей образования?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for item in selected_items:
                self.education_list.takeItem(self.education_list.row(item))

    def add_skill(self):
        dialog = SkillDialog()
        if dialog.exec_() == QDialog.Accepted:
            skill = dialog.get_data()
            item_text = f"{skill['name']} ({skill['level']}%)"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, skill)
            self.skills_list.addItem(item)

    def remove_skill(self):
        selected_items = self.skills_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Предупреждение", "Пожалуйста, выберите навык для удаления.")
            return
        reply = QMessageBox.question(
            self, 'Подтверждение удаления',
            f"Вы уверены, что хотите удалить {len(selected_items)} выбранных навыков?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for item in selected_items:
                self.skills_list.takeItem(self.skills_list.row(item))

    def add_language(self):
        language, ok = QInputDialog.getText(self, "Добавить язык", "Язык:")
        if ok and language.strip():
            self.languages_list.addItem(language.strip())

    def remove_language(self):
        selected_items = self.languages_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Предупреждение", "Пожалуйста, выберите язык для удаления.")
            return
        reply = QMessageBox.question(
            self, 'Подтверждение удаления',
            f"Вы уверены, что хотите удалить {len(selected_items)} выбранных языков?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for item in selected_items:
                self.languages_list.takeItem(self.languages_list.row(item))

    def add_project(self):
        dialog = ProjectDialog()
        if dialog.exec_() == QDialog.Accepted:
            project = dialog.get_data()
            item_text = f"{project['name']} - {project['description']} ({project['link']})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, project)
            self.projects_list.addItem(item)

    def remove_project(self):
        selected_items = self.projects_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Предупреждение", "Пожалуйста, выберите проект для удаления.")
            return
        reply = QMessageBox.question(
            self, 'Подтверждение удаления',
            f"Вы уверены, что хотите удалить {len(selected_items)} выбранных проектов?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for item in selected_items:
                self.projects_list.takeItem(self.projects_list.row(item))

    def add_certification(self):
        dialog = CertificationDialog()
        if dialog.exec_() == QDialog.Accepted:
            cert = dialog.get_data()
            item_text = f"{cert['title']} - {cert['institution']} ({cert['date']})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, cert)
            self.certifications_list.addItem(item)

    def remove_certification(self):
        selected_items = self.certifications_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Предупреждение", "Пожалуйста, выберите сертификат для удаления.")
            return
        reply = QMessageBox.question(
            self, 'Подтверждение удаления',
            f"Вы уверены, что хотите удалить {len(selected_items)} выбранных сертификатов?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for item in selected_items:
                self.certifications_list.takeItem(self.certifications_list.row(item))

    ###############################################
    # ГЕНЕРАЦИЯ РЕЗЮМЕ
    ###############################################

    def generate_resume(self):
        data_file = self.data_input.text().strip()
        template_name = self.template_combo.currentText()
        output_html = self.output_html_input.text().strip()
        output_pdf = self.output_pdf_input.text().strip() or None

        if not data_file or not os.path.isfile(data_file):
            QMessageBox.warning(
                self,
                "Некорректный YAML",
                "Не обнаружен выбранный YAML файл. Укажите корректный путь."
            )
            return

        if not output_html:
            QMessageBox.warning(
                self,
                "Нет пути для HTML",
                "Пожалуйста, укажите путь для сохранения HTML-файла."
            )
            return

        # Настройка логгера
        logger = logging.getLogger()
        logger.handlers = []
        setup_logging()
        log_handler = GUIHandler(self.log_signal)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        log_handler.setFormatter(formatter)
        logger.addHandler(log_handler)

        # Пытаемся загрузить и провалидировать данные
        try:
            data = load_data(data_file)
            data["output_html"] = output_html
            validate_data(data)
            check_images(data)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка данных",
                f"Не удалось загрузить/валидировать YAML: {e}"
            )
            return

        # Запускаем поток
        self.generator_thread = ResumeGeneratorThread(
            data=data,
            template_dir=os.path.join(os.path.dirname(__file__), "templates"),
            template_name=template_name,
            output_html=output_html,
            output_pdf=output_pdf
        )
        self.generator_thread.progress.connect(self.update_progress)
        self.generator_thread.finished.connect(self.on_generation_finished)
        self.generator_thread.error.connect(self.show_error)
        self.generator_thread.start()

        self.generate_button.setEnabled(False)
        self.status_bar.showMessage("Генерация резюме началась...", 5000)

    def update_progress(self, percent, message):
        self.progress_bar.setValue(percent)
        self.log_message(message)

    def show_error(self, message):
        QMessageBox.critical(self, "Ошибка", message)
        self.status_bar.showMessage("Произошла ошибка во время генерации.", 5000)

    def on_generation_finished(self):
        QMessageBox.information(self, "Успех", "Резюме успешно сгенерировано!")
        self.generator_thread = None
        self.progress_bar.setValue(0)
        self.generate_button.setEnabled(True)
        self.status_bar.showMessage("Генерация резюме завершена.", 5000)

        # Если есть вкладка предпросмотра, подгружаем результат
        if self.preview_tab and self.webview:
            output_html = self.output_html_input.text().strip()
            if output_html and os.path.isfile(output_html):
                self.webview.load(QUrl.fromLocalFile(os.path.abspath(output_html)))

    ###############################################
    # ДРУГИЕ ПОЛЕЗНЫЕ МЕТОДЫ
    ###############################################

    def log_message(self, message):
        self.log_output.append(message)
        self.log_output.ensureCursorVisible()
        self.status_bar.showMessage(message, 5000)

    def search_experience(self, text):
        for index in range(self.experience_list.count()):
            item = self.experience_list.item(index)
            item.setHidden(text.lower() not in item.text().lower())

    def add_hover_animation(self, button):
        """
        Добавляет анимацию (увеличение размера) при наведении.
        """
        original_size = QSize(200, 60)
        hover_size = QSize(220, 70)

        button.setFixedSize(original_size)
        button.setFont(QFont("Arial", 14))
        button.setObjectName("generateButton")

        animation = QPropertyAnimation(button, b"size")
        animation.setDuration(200)
        animation.setEasingCurve(QEasingCurve.OutBounce)
        button.hover_animation = animation

        def on_enter(event):
            button.hover_animation.stop()
            button.hover_animation.setStartValue(button.size())
            button.hover_animation.setEndValue(hover_size)
            button.hover_animation.start()
            QPushButton.enterEvent(button, event)

        def on_leave(event):
            button.hover_animation.stop()
            button.hover_animation.setStartValue(button.size())
            button.hover_animation.setEndValue(original_size)
            button.hover_animation.start()
            QPushButton.leaveEvent(button, event)

        button.enterEvent = on_enter
        button.leaveEvent = on_leave

    def show_about_dialog(self):
        about_text = """
        <h2>Генератор Резюме</h2>
        <p>Версия 0.1</p>
        <p>Автор: Андрей Гомонов</p>
        <p>Это приложение позволяет создавать профессиональные резюме на основе ваших данных.</p>
        <p>Поддерживаемые форматы экспорта: HTML, PDF.</p>
        """
        QMessageBox.about(self, "О приложении", about_text)

    def closeEvent(self, event):
        """
        При закрытии окна завершаем поток, если активен.
        """
        if hasattr(self, 'generator_thread') and self.generator_thread and self.generator_thread.isRunning():
            self.generator_thread.terminate()
            self.generator_thread.wait()
        event.accept()


###############################################
# ДИАЛОГОВЫЕ ОКНА ДЛЯ ОПЫТА, ОБРАЗОВАНИЯ И Т.Д.
###############################################

class ExperienceDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Добавить опыт работы")
        self.setModal(True)
        layout = QFormLayout()

        self.title_input = QLineEdit()
        self.company_input = QLineEdit()
        self.location_input = QLineEdit()
        self.start_date_input = QLineEdit()
        self.end_date_input = QLineEdit()
        self.details_input = QTextEdit()
        self.details_input.setFixedHeight(80)

        layout.addRow("Должность:", self.title_input)
        layout.addRow("Компания:", self.company_input)
        layout.addRow("Местоположение:", self.location_input)
        layout.addRow("Дата начала:", self.start_date_input)
        layout.addRow("Дата окончания:", self.end_date_input)
        layout.addRow("Описание:", self.details_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setLayout(layout)

    def get_data(self):
        return {
            'title': self.title_input.text(),
            'company': self.company_input.text(),
            'location': self.location_input.text(),
            'start_date': self.start_date_input.text(),
            'end_date': self.end_date_input.text(),
            'details': self.details_input.toPlainText().split('\n')
        }

class EducationDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Добавить образование")
        self.setModal(True)
        layout = QFormLayout()

        self.degree_input = QLineEdit()
        self.field_input = QLineEdit()
        self.institution_input = QLineEdit()
        self.location_input = QLineEdit()
        self.start_date_input = QLineEdit()
        self.end_date_input = QLineEdit()
        self.description_input = QTextEdit()
        self.description_input.setFixedHeight(80)

        layout.addRow("Степень:", self.degree_input)
        layout.addRow("Специальность:", self.field_input)
        layout.addRow("Учебное заведение:", self.institution_input)
        layout.addRow("Местоположение:", self.location_input)
        layout.addRow("Дата начала:", self.start_date_input)
        layout.addRow("Дата окончания:", self.end_date_input)
        layout.addRow("Описание:", self.description_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setLayout(layout)

    def get_data(self):
        return {
            'degree': self.degree_input.text(),
            'field': self.field_input.text(),
            'institution': self.institution_input.text(),
            'location': self.location_input.text(),
            'start_date': self.start_date_input.text(),
            'end_date': self.end_date_input.text(),
            'description': self.description_input.toPlainText()
        }

class SkillDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Добавить навык")
        self.setModal(True)
        layout = QFormLayout()

        self.name_input = QLineEdit()
        self.level_input = QSpinBox()
        self.level_input.setRange(0, 100)
        self.level_input.setSuffix("%")

        layout.addRow("Навык:", self.name_input)
        layout.addRow("Уровень владения:", self.level_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setLayout(layout)

    def get_data(self):
        return {
            'name': self.name_input.text(),
            'level': self.level_input.value()
        }

class ProjectDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Добавить проект")
        self.setModal(True)
        layout = QFormLayout()

        self.name_input = QLineEdit()
        self.description_input = QTextEdit()
        self.link_input = QLineEdit()
        self.image_input = QLineEdit()

        browse_image_button = QPushButton()
        browse_image_button.setIcon(QIcon.fromTheme("image-x-generic"))
        browse_image_button.setToolTip("Выбрать изображение")
        browse_image_button.clicked.connect(self.browse_image)

        image_layout = QHBoxLayout()
        image_layout.addWidget(self.image_input)
        image_layout.addWidget(browse_image_button)

        layout.addRow("Название проекта:", self.name_input)
        layout.addRow("Описание:", self.description_input)
        layout.addRow("Ссылка:", self.link_input)
        layout.addRow("Путь к изображению:", image_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setLayout(layout)

    def browse_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "", "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_path:
            self.image_input.setText(file_path)

    def get_data(self):
        return {
            'name': self.name_input.text(),
            'description': self.description_input.toPlainText(),
            'link': self.link_input.text(),
            'image': {
                'type': 'path',
                'value': self.image_input.text(),
                'download': False
            }
        }

class CertificationDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Добавить сертификат")
        self.setModal(True)
        layout = QFormLayout()

        self.title_input = QLineEdit()
        self.institution_input = QLineEdit()
        self.date_input = QLineEdit()
        self.link_input = QLineEdit()

        layout.addRow("Название сертификата:", self.title_input)
        layout.addRow("Учреждение:", self.institution_input)
        layout.addRow("Дата получения:", self.date_input)
        layout.addRow("Ссылка на сертификат:", self.link_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setLayout(layout)

    def get_data(self):
        return {
            'title': self.title_input.text(),
            'institution': self.institution_input.text(),
            'date': self.date_input.text(),
            'link': self.link_input.text()
        }


###############################################
# ТОЧКА ЗАПУСКА GUI
###############################################

def run_gui():
    # Отключение политики безопасности CORS
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--disable-web-security --disable-features=IsolateOrigins,site-per-process'
    app = QApplication(sys.argv)
    gui = ResumeGeneratorGUI()
    gui.show()

    def handle_sigint(signal_num, frame):
        gui.close()

    signal.signal(signal.SIGINT, handle_sigint)

    sys.exit(app.exec())
