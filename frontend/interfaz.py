import sys
import requests
import os
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QSpacerItem, QSizePolicy, QListWidget, QComboBox, 
    QFrame, QMainWindow, QSpinBox, QDialog
)
from PyQt5.QtGui import QGuiApplication, QFont, QMovie
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QThread
from ventas_ui import EncargadoWindow
from inventario_ui import AdminWindow
from config import URL_SERVER


class BaseWindow(QWidget):
    """Base class to handle common UI setup (layout initialization)"""
    def __init__(self, title):
        super().__init__()

        self.setWindowTitle(title)
        self.set_ui_size()  # This will be overridden by subclasses

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

    def set_ui_size(self):
        """This method will be overridden in subclasses to set different window sizes"""
        pass


class WorkerThread(QThread):
    """Worker thread to handle authentication without freezing the UI."""
    task_finished = pyqtSignal(bool, str, bool)  # Emit (success, token)

    def __init__(self, username, password):
        super().__init__()
        self.username = username
        self.password = password
        self.token = ""

    def run(self):
        """Runs the login request in a separate thread."""
        api_url = f"http://{URL_SERVER}/api/login/"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        payload = {"username": self.username, "password": self.password}

        try:
            response = requests.post(api_url, json=payload, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                self.token = data.get("token", "")
                self.is_staff = data.get("is_staff", "")
                
                if self.token:
                    self.task_finished.emit(True, self.token, self.is_staff)  # Successful login
                    return
        except requests.exceptions.RequestException:
            pass

        self.task_finished.emit(False, "", False)  # Login failed

class LoadingScreen(QDialog):

        
    """A simple loading screen with a GIF animation."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cargando...")
        screen = QGuiApplication.primaryScreen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        self.window_width = int(screen_width * 0.32)
        self.window_height = int(screen_height * 0.32)
        self.setFixedSize( 300, 300)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setModal(True)

        layout = QVBoxLayout()
        self.loading_label = QLabel(self)
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ✅ Ensure the GIF exists
        self.movie = QMovie(os.path.join(os.getcwd(),"media","carga3.gif"))
        self.loading_label.setMovie(self.movie)
        self.movie.start()

        layout.addWidget(self.loading_label)
        self.setLayout(layout)

class LoginScreen(BaseWindow):
    """Login screen with 30% of screen size"""
    def __init__(self):
        super().__init__("Terra Nosa Inventario App Login")
        self.set_ui_size()
        self.init_ui()

    def set_ui_size(self):
        """Set window size to 30% of the screen"""
        screen = QGuiApplication.primaryScreen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        window_width = int(screen_width * 0.5)
        window_height = int(screen_height * 0.5)

        x_position = (screen_width - window_width) // 2
        y_position = (screen_height - window_height) // 2

        self.setGeometry(x_position, y_position, window_width, window_height)

    def init_ui(self):
        """Create and style the login UI elements"""
        # Main Layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)

        # Title Label
        self.title_label = QLabel("Aplicación Inventario Terra Nosa")
        self.title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.title_label)

        main_layout.addSpacerItem(QSpacerItem(20, 30, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # Username Field (Centered & Smaller)
        self.username_label = QLabel("Usuario")
        self.username_label.setFont(QFont("Arial", 12))
        self.username_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.username_label)

        username_container = QHBoxLayout()
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.username_input.setFixedWidth(250)  # Make it smaller
        self.username_input.setStyleSheet("border: 2px solid black; padding: 8px; border-radius: 5px;")
        username_container.addStretch()
        username_container.addWidget(self.username_input)
        username_container.addStretch()
        main_layout.addLayout(username_container)

        # Password Field (Centered & Smaller)
        self.password_label = QLabel("Contraseña")
        self.password_label.setFont(QFont("Arial", 12))
        self.password_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.password_label)

        password_container = QHBoxLayout()
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setFixedWidth(250)  # Make it smaller
        self.password_input.setStyleSheet("border: 2px solid black; padding: 8px; border-radius: 5px;")
        
         # 👁️ Show/Hide Button
        self.toggle_password_button = QPushButton("Mostrar")
        self.toggle_password_button.setCheckable(True)
        self.toggle_password_button.setFixedWidth(70)
        self.toggle_password_button.clicked.connect(self.toggle_password_visibility)
        
        password_container.addStretch()
        password_container.addWidget(self.password_input)
        password_container.addWidget(self.toggle_password_button)
        password_container.addStretch()
        spacer = QSpacerItem(-80, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        password_container.addItem(spacer)
        main_layout.addLayout(password_container)

        # Spacer to balance layout
        main_layout.addSpacerItem(QSpacerItem(20, 30, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # Login Button
        self.login_button = QPushButton("Acceder")
        self.login_button.setStyleSheet("""
            QPushButton {
                background-color: #3b50ff;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #2a3eb1;
            }
        """)

        self.username_input.returnPressed.connect(self.authenticate_user)
        self.password_input.returnPressed.connect(self.authenticate_user)

        self.login_button.clicked.connect(self.authenticate_user)
        main_layout.addWidget(self.login_button)

        self.layout.addLayout(main_layout)

        # Connect "Enter" key to authentication
        self.username_input.returnPressed.connect(self.authenticate_user)
    
    def toggle_password_visibility(self):
        if self.toggle_password_button.isChecked():
            self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_password_button.setText("Ocultar")
        else:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_password_button.setText("Mostrar")

    def authenticate_user(self):
        """Handles authentication via GET request"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "Error", "Por favor, ingrese el usuario y la contraseña.")
            return

        # Show loading screen
        self.loading_screen = LoadingScreen()
        self.loading_screen.show()

        # Start worker thread for login
        self.worker = WorkerThread(username, password)
        self.worker.task_finished.connect(self.handle_login_response)
        self.worker.start()
        self.close()

    def handle_login_response(self, success, token, is_staff):
        """Handles login response from worker thread"""
        self.loading_screen.close()  # Close loading screen

        if success:
            self.close()  # Close login window
            
            if is_staff == False : 
                self.main_app = EncargadoWindow(token)  # Open the main app
            else : 
                self.main_app = AdminWindow(token)
                
            self.main_app.show()
        else:
            self.show()
            QMessageBox.warning(self, "Error", "Usuario o contraseña incorrectos.")
            
    def obtener_ip_publica(self):
        try:
            respuesta = requests.get("https://api64.ipify.org?format=json")
            if respuesta.status_code == 200:
                ip_publica = respuesta.json()["ip"]
                return ip_publica
            else:
                print("No se pudo obtener la IP pública.")
                return None
        except requests.exceptions.RequestException as e:
            print(f"Error al obtener la IP pública: {e}")
            return None
        
        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    login_screen = LoginScreen()
    login_screen.show()
    sys.exit(app.exec())