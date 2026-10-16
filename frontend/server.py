from flask import Flask, request, jsonify

app = Flask(__name__)

# Mock user database (for testing purposes)
USER_DATABASE = {
    "admin": "12345",
    "testuser": "password",
    "john": "doe123"
}

productos = [
    {"id": 1, "nombre": "Laptop", "descripcion": "Laptop de alta gama", "proveedor": "puma", "precio": 1200.50, "stock": 10},
    {"id": 2, "nombre": "Teclado", "descripcion": "Teclado mecánico RGB","proveedor": "puma", "precio": 75.99, "stock": 25},
    {"id": 3, "nombre": "Mouse", "descripcion": "Mouse inalámbrico","proveedor": "puma", "precio": 30.49, "stock": 50},
    {"id": 4, "nombre": "Monitor", "descripcion": "Monitor Full HD 24 pulgadas","proveedor": "puma", "precio": 199.99, "stock": 15},
    {"id": 5, "nombre": "Silla Gamer", "descripcion": "Silla ergonómica para gaming","proveedor": "puma", "precio": 299.99, "stock": 5}
]

@app.route('/productos', methods=['GET'])
def get_all_products():
    """Returns all products in JSON format."""
    return jsonify(productos)

@app.route('/productos/<int:product_id>', methods=['GET'])
def get_product_by_id(product_id):
    """Returns a specific product by ID."""
    product = next((p for p in productos if p["id"] == product_id), None)
    if product:
        return jsonify(product)
    return jsonify({"error": "Producto no encontrado"}), 404

@app.route('/auth', methods=['GET'])
def authenticate():
    username = request.args.get('username')
    password = request.args.get('password')

    if not username or not password:
        return jsonify({"authenticated": False, "message": "Username and password required"}), 400

    # Check if the user exists and the password matches
    if username in USER_DATABASE and USER_DATABASE[username] == password:
        return jsonify({"authenticated": True, "message": "Login successful!"})

    return jsonify({"authenticated": False, "message": "Invalid credentials"})


if __name__ == '__main__':
    app.run(debug=True)  # Runs the server locally on port 5000
