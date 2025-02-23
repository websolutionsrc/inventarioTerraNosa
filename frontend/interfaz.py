import sys
import requests
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QSpacerItem, QSizePolicy, QListWidget, QComboBox, 
    QFrame, QScrollArea, QMainWindow, QSpinBox
)
from PyQt6.QtGui import QGuiApplication, QFont
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from ventas_ui import Ui_VentasWindow

MONITOR_PERCENT = 0.8


class ProductSelectionWidget(QWidget):

    remove_requested = pyqtSignal(QWidget)

    def __init__(self, parent_screen, color):
        super().__init__()

        self.parent_screen = parent_screen
        self.color = color
        self.set_ui_size()
        self.init_ui()

        # Allow stretching
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    
    def set_ui_size(self):
        """Set window size to 30% of the screen"""
        screen = QGuiApplication.primaryScreen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        self.window_width = float(screen_width * 0.65)
        self.window_height = float(screen_height * 0.65)

    def init_ui(self):
        """Initialize UI components for product selection"""
        self.layout = QVBoxLayout()
        self.container = QFrame()
        self.container.setStyleSheet(" background-color: "+self.color+"; border-radius: 10px; padding: 10px;")
        self.container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        main_layout = QVBoxLayout(self.container)

        # Search Bar Layout
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar producto...")
        self.search_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.search_input.textChanged.connect(self.filter_products)
        spacer = QSpacerItem(87, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        search_layout.addItem(spacer)
        
        self.search_input.setStyleSheet("background-color: white; border-radius: 0px; border: 1px solid black;")
        search_layout.addWidget(self.search_input, alignment=Qt.AlignmentFlag.AlignLeft)

        # Product Selection Layout
        product_layout = QHBoxLayout()
        self.producto_label = QLabel("Producto:")
        self.producto_label.setStyleSheet("""font-size: 13px;""")
        self.product_dropdown = QComboBox()
        self.product_dropdown.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.product_dropdown.currentTextChanged.connect(lambda: self.parent_screen.update_subtotal())
        
        self.product_dropdown.currentIndexChanged.connect(self.display_stock)
        self.product_dropdown.setStyleSheet("background-color: white; border-radius: 0px; border: 1px solid black;")

        self.quantity_label = QLabel("Cantidad:")
        self.quantity_label.setStyleSheet("""font-size: 13px;""")
        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(1, 100)
        self.quantity_input.setValue(1)
        self.quantity_input.setFixedWidth(55)
        self.quantity_input.setStyleSheet("background-color: white; border-radius: 0px; border: 1px solid black;")
        self.quantity_input.textChanged.connect(lambda: self.parent_screen.update_subtotal())

        product_layout.addWidget(self.producto_label)
        product_layout.addWidget(self.product_dropdown)
        product_layout.addWidget(self.quantity_label)
        product_layout.addWidget(self.quantity_input)

        product_layout.addStretch()  # Push delete button to right

        # Delete Button
        self.delete_button = QPushButton("Borrar")
        self.delete_button.setFixedWidth(70)
        self.delete_button.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-size: 14px;
                padding: 5px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #b52b3a;
            }
        """)
        self.delete_button.clicked.connect(lambda: self.parent_screen.remove_product_entry(self))

        product_layout.addWidget(self.delete_button, alignment=Qt.AlignmentFlag.AlignRight)

        # Stock Layout
        stock_layout = QHBoxLayout()
        self.stock_label = QLabel("Cantidad en el deposito: -")
        spacer2 = QSpacerItem(76, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        stock_layout.addItem(spacer2)
        stock_layout.addWidget(self.stock_label)

        # Add layouts to main layout
        main_layout.addLayout(search_layout)
        main_layout.addLayout(product_layout)
        main_layout.addLayout(stock_layout)

        self.layout.addWidget(self.container)
        self.setLayout(self.layout)
    
    def set_products(self, products):
        """Set full product list and populate dropdown"""
        self.products = products
        self.filtered_products = products[:]
        self.product_dropdown.addItem("-")
        self.populate_product_dropdown()

    def populate_product_dropdown(self):
        """Fill the dropdown with filtered products"""
        for product in self.filtered_products:
            display_text = f"{product['nombre']} - {product.get('proveedor')} - ${product['precio']}"
            self.product_dropdown.addItem(display_text)
        
        self.product_dropdown.setCurrentIndex(0)

    def filter_products(self):
        """Filter dropdown based on search input"""
        search_text = self.search_input.text().strip().lower()
        self.filtered_products = [
            p for p in self.products
            if search_text in p["nombre"].lower() or search_text in p.get("proveedor", "").lower()
        ]
        
        self.product_dropdown.clear()
        self.populate_product_dropdown()

    def display_stock(self):
        """Show stock of the selected product"""
        selected_index = self.product_dropdown.currentIndex()
        if selected_index >= 0 and selected_index < len(self.filtered_products):
            product = self.filtered_products[selected_index]
            self.stock_label.setText(f"Cantidad en el deposito: {product['stock']}")

    def remove_product_entry(self, entry):
        self.remove_requested.emit(self)

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

        window_width = int(screen_width * 0.3)
        window_height = int(screen_height * 0.3)

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
        password_container.addStretch()
        password_container.addWidget(self.password_input)
        password_container.addStretch()
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

    def authenticate_user(self):
        """Handles authentication via GET request"""
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(self, "Error", "Please enter both username and password.")
            return

        api_url = f"http://127.0.0.1:5000/auth?username={username}&password={password}"

        try:
            response = requests.get(api_url)
            if response.status_code == 200:
                data = response.json()
                if data.get("authenticated"):
                    print(data.get("message")) # Extract Token
                    #QMessageBox.information(self, "Success", "Login successful!")
                    self.open_main_app()
                else:
                    QMessageBox.warning(self, "Error", "Invalid credentials.")
            else:
                QMessageBox.warning(self, "Error", "Server error. Try again later.")
        except requests.exceptions.RequestException as e:
            QMessageBox.critical(self, "Error", f"Connection error: {str(e)}")

    def open_main_app(self):
        """Opens main app window after successful login"""
        self.close()  # Close login window
        self.main_app = VentaScreen()
        self.main_app.show()


class VentaScreen(BaseWindow):
    """Screen for adding sales"""
    def __init__(self):
        super().__init__("Venta de Productos")

        self.products = []  # To store products from API
        self.product_entries = []
        self.index = 1
        self.entries_container = QVBoxLayout()

        self.request_products()
        self.init_ui()
        

    def set_ui_size(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        self.window_width = int(screen_width * 0.8)
        self.window_height = int(screen_height * 0.8)

        x_position = (screen_width - self.window_width) // 2
        y_position = (screen_height - self.window_height) // 2

        self.setGeometry(x_position, y_position, self.window_width, self.window_height)

    def init_ui(self):
        """Create UI elements"""
        self.title_label = QLabel("Registrar Venta")
        self.title_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self.title_label.setStyleSheet("padding: 20px;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.title_label)

        mainLayout = QHBoxLayout()

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)  # Allows dynamic resizing
        self.scroll_area.setStyleSheet("border: none;")  # Remove border for clean UI

        self.entries_container = QWidget()
        self.entries_layout = QVBoxLayout()
        self.entries_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.entries_container.setLayout(self.entries_layout)
        
        self.scroll_area.setWidget(self.entries_container)
        self.scroll_area.setFixedWidth(int(self.window_width * 0.56))
        mainLayout.addWidget(self.scroll_area, alignment=Qt.AlignmentFlag.AlignLeft)
        
        self.scroll_subtotal_area = QScrollArea()
        self.scroll_subtotal_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none;")

        self.subtotal_container = QWidget()
        self.subtotal_layout = QVBoxLayout()
        self.subtotal_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.subtotal_container.setLayout(self.subtotal_layout)

        self.scroll_subtotal_area.setWidget(self.subtotal_container)
        self.scroll_subtotal_area.setFixedWidth(int(self.window_width * 0.40))
        mainLayout.addWidget(self.scroll_subtotal_area, alignment=Qt.AlignmentFlag.AlignRight)

        

        self.add_product_layout = QHBoxLayout()
        self.add_product_button = QPushButton("+ Agregar Producto")
        self.add_product_button.setFixedWidth(200)
        self.add_product_button.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border-radius: 10px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        self.add_product_button.clicked.connect(self.add_product_entry)
        self.add_product_layout.addWidget(self.add_product_button, alignment=Qt.AlignmentFlag.AlignLeft)
        
        self.layout.addLayout(self.add_product_layout)

        self.layout.addLayout(mainLayout)


        # Sell Button
        self.sell_button = QPushButton("Registrar Venta")
        self.sell_button.setFixedWidth(200)
        self.sell_button.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.sell_button.clicked.connect(self.register_sale)
        self.layout.addWidget(self.sell_button , alignment=Qt.AlignmentFlag.AlignRight)

        self.add_product_entry()

    def request_products(self):
        """Fetch product data from API"""
        api_url = "http://127.0.0.1:5000/productos"
        try:
            response = requests.get(api_url)
            if response.status_code == 200:
                self.products = response.json()
            else:
                QMessageBox.critical(self, "Error", "Error al obtener productos del servidor")
        except requests.exceptions.RequestException:
            QMessageBox.critical(self, "Error", "No se pudo conectar con el servidor")

    def load_products(self, entry):
        entry.set_products(self.products)

    def register_sale(self):
        """Simulate sale registration"""
        selected_index = self.product_dropdown.currentIndex()
        if selected_index < 0 or selected_index >= len(self.filtered_products):
            QMessageBox.warning(self, "Error", "Seleccione un producto")
            return

        quantity = self.quantity_input.text()
        if not quantity.isdigit() or int(quantity) <= 0:
            QMessageBox.warning(self, "Error", "Ingrese una cantidad válida")
            return

        product = self.filtered_products[selected_index]

        if int(quantity) > product['stock']:
            QMessageBox.warning(self, "Error", "Stock insuficiente")
            return

        QMessageBox.information(self, "Venta Registrada", f"Se vendieron {quantity} unidades de {product['nombre']}.")
    
    def add_product_entry(self):
        color_entry = ["#DBDBDB","#A1E3F9"]
        
        product_entry = ProductSelectionWidget(self, color_entry[self.index])
        self.index = 0 if self.index == 1 else 1 
        product_entry.remove_requested.connect(self.remove_product_entry)
        self.load_products(product_entry)
        self.product_entries.append(product_entry)

        # Add new entry to the vertical layout
        
        self.entries_layout.addWidget(product_entry)

        title_label = QLabel("Subtotal venta")
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.subtotal_layout.addWidget(title_label)

        for i in reversed(range(self.entries_layout.count())):
            item = self.entries_layout.itemAt(i)
            if isinstance(item, QSpacerItem):
                self.entries_layout.removeItem(item)

        # Add a small stretch at the bottom to avoid excessive spacing
        self.entries_layout.addStretch(1)

        # Auto-scroll to show the newly added entry
        QTimer.singleShot(100, self.scroll_to_bottom)

    def scroll_to_bottom(self):
        self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().maximum())
    
    def remove_product_entry(self, widget):
        if widget in self.product_entries:
            self.product_entries.remove(widget)
            widget.setParent(None)
            widget.deleteLater()
            
class MainWindow(QMainWindow, Ui_VentasWindow):
    def __init__(self):
        super().__init__()
        self.set_ui_size()
        self.setupUi(self)  # Set up the UI
        self.setWindowTitle("My Application")
        
        self.products = []  # To store products from API
        self.product_entries = []
        self.product_subtotal = ""
        self.index = 1
        self.entries_container = QVBoxLayout()
        self.entries_container = QVBoxLayout()

        self.request_products()
        self.init_ui()
        
    def set_ui_size(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        self.window_width = int(screen_width * 0.9)
        self.window_height = int(screen_height * 0.9)

        x_position = (screen_width - self.window_width) // 2
        y_position = (screen_height - self.window_height) // 2

        self.setGeometry(x_position, y_position, self.window_width, self.window_height)
        
    def init_ui(self):
        self.entries_container = QWidget()
        self.entries_layout = QVBoxLayout()
        self.entries_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.entries_container.setLayout(self.entries_layout)
        self.scrollArea.setStyleSheet("border: none;") 
        self.scrollArea.setWidget(self.entries_container)
        
        self.subtotal_container = QWidget()
        self.subtotal_layout = QVBoxLayout()
        self.subtotal_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.subtotal_container.setLayout(self.subtotal_layout)
        self.scrollArea_2.setWidget(self.subtotal_container) 
        
        self.pushButton.clicked.connect(self.add_product_entry)
        self.pushButton_2.clicked.connect(self.register_sale)
        self.add_product_entry()
        
    def on_button_click(self):
        print("Button clicked!")
    
    def request_products(self):
        """Fetch product data from API"""
        api_url = "http://127.0.0.1:5000/productos"
        try:
            response = requests.get(api_url)
            if response.status_code == 200:
                self.products = response.json()
            else:
                QMessageBox.critical(self, "Error", "Error al obtener productos del servidor")
        except requests.exceptions.RequestException:
            QMessageBox.critical(self, "Error", "No se pudo conectar con el servidor")

    def load_products(self, entry):
        entry.set_products(self.products)
    
    def add_product_entry(self):
        color_entry = ["#DBDBDB","#A1E3F9"]
        
        product_entry = ProductSelectionWidget(self, color_entry[self.index])
        self.index = 0 if self.index == 1 else 1 
        product_entry.remove_requested.connect(self.remove_product_entry)
        self.load_products(product_entry)
        self.product_entries.append(product_entry)

        # Add new entry to the vertical layout
        
        self.entries_layout.addWidget(product_entry)
    
        for i in reversed(range(self.entries_layout.count())):
            item = self.entries_layout.itemAt(i)
            if isinstance(item, QSpacerItem):
                self.entries_layout.removeItem(item)

        # Add a small stretch at the bottom to avoid excessive spacing
        self.entries_layout.addStretch(1)

        # Auto-scroll to show the newly added entry
        QTimer.singleShot(100, self.scroll_to_bottom)

    def scroll_to_bottom(self):
        self.scrollArea.verticalScrollBar().setValue(self.scrollArea.verticalScrollBar().maximum())
    
    def remove_product_entry(self, widget):
        if widget in self.product_entries:
            self.product_entries.remove(widget)
            widget.setParent(None)
            widget.deleteLater()
            
    def register_sale(self):
        """Simulate sale registration"""
        selected_index = self.product_dropdown.currentIndex()
        if selected_index < 0 or selected_index >= len(self.filtered_products):
            QMessageBox.warning(self, "Error", "Seleccione un producto")
            return

        quantity = self.quantity_input.text()
        if not quantity.isdigit() or int(quantity) <= 0:
            QMessageBox.warning(self, "Error", "Ingrese una cantidad válida")
            return

        product = self.filtered_products[selected_index]

        if int(quantity) > product['stock']:
            QMessageBox.warning(self, "Error", "Stock insuficiente")
            return

        QMessageBox.information(self, "Venta Registrada", f"Se vendieron {quantity} unidades de {product['nombre']}.")
    
    def update_subtotal(self):
        self.product_subtotal = ""
        for entry in self.product_entries:
            self.product_subtotal += f"- {entry.product_dropdown.currentText()}, Cantidad: {entry.quantity_input.text()}, Precio: {"placeHolder"}$ \n\n"
        
        subtotal_info = QLabel(self.product_subtotal)
        subtotal_info.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        subtotal_info.setAlignment(Qt.AlignmentFlag.AlignLeft)
        for i in range(self.subtotal_layout.count()):
            self.subtotal_layout.itemAt(i).widget().setParent(None)
        self.subtotal_layout.addWidget(subtotal_info)
    
         
if __name__ == "__main__":
    app = QApplication(sys.argv)
    login_screen = MainWindow()
    login_screen.show()
    sys.exit(app.exec())
