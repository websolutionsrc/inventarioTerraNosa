from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView
from django.contrib.auth import authenticate

from .models import Usuario, Producto, EntradaInventario, Venta, SalidaInventario
from .serializers import UsuarioSerializer, ProductoSerializer, EntradaInventarioSerializer, VentaSerializer, SalidaInventarioSerializer
from django.http import JsonResponse

class LoginView(APIView):
    def post(self, request):
        print("Received request data:", request.data)
        username = request.data.get("username")
        password = request.data.get("password")
        
        user = authenticate(username=username, password=password)
        print(f"Authenticated user: {user}")  # Debugging

        if user:
            token, created = Token.objects.get_or_create(user=user)
            return Response({"token": token.key}, status=status.HTTP_200_OK)

        print("Invalid username or password")  # Debugging output
        return Response({"error": "Invalid username or password"}, status=status.HTTP_400_BAD_REQUEST)
    
    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]


class AllowStaffOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_staff
    
# Custom permission for staff-only POST requests
class StaffOnlyPostPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        # Allow GET for everyone, but POST only for staff users
        if request.method in ['POST', 'DELETE']:
            return request.user.is_staff
        return True  # Allow GET and other safe methods

class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all()
    serializer_class = UsuarioSerializer
    permission_classes = [permissions.IsAuthenticated, AllowStaffOnly] 

class ProductoViewSet(viewsets.ModelViewSet):
    queryset = Producto.objects.all()
    serializer_class = ProductoSerializer
    permission_classes = [permissions.IsAuthenticated, StaffOnlyPostPermission] 
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response({"message": "Entry deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

class EntradaInventarioViewSet(viewsets.ModelViewSet):
    queryset = EntradaInventario.objects.all()
    serializer_class = EntradaInventarioSerializer
    permission_classes = [permissions.IsAuthenticated, AllowStaffOnly] 
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response({"message": "Entry deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

class VentaViewSet(viewsets.ModelViewSet):
    queryset = Venta.objects.all().filter(is_deleted=False)
    serializer_class = VentaSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def create(self, request, *args, **kwargs):
        """ Create a venta and return its ID """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        venta = serializer.save()  # Save the venta instance

        return Response({"id": venta.id}, status=status.HTTP_201_CREATED)
    
    def destroy(self, request, *args, **kwargs):
        """ Soft delete instead of actual deletion """
        instance = self.get_object()
        instance.delete()
        return Response({"message": "Record marked as deleted."}, status=status.HTTP_204_NO_CONTENT)
    
class SalidaInventarioViewSet(viewsets.ModelViewSet):
    queryset = SalidaInventario.objects.filter(is_deleted=False)
    serializer_class = SalidaInventarioSerializer
    permission_classes = [permissions.IsAuthenticated] 
    
    def destroy(self, request, *args, **kwargs):
        """ Soft delete instead of actual deletion """
        instance = self.get_object()
        instance.delete()
        return Response({"message": "Record marked as deleted."}, status=status.HTTP_204_NO_CONTENT)

# Admin views
class VentaAdminViewSet(viewsets.ModelViewSet):
    queryset = Venta.objects.all()
    serializer_class = VentaSerializer
    permission_classes = [permissions.IsAuthenticated, AllowStaffOnly]
    

class SalidaInventarioAdminViewSet(viewsets.ModelViewSet):
    queryset = SalidaInventario.objects.all()  # Show all records, including deleted
    serializer_class = SalidaInventarioSerializer
    permission_classes = [permissions.IsAuthenticated, AllowStaffOnly]  # Only admins can access this
