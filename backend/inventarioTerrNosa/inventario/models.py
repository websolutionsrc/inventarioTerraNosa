from django.db import models
from django.db.models import Sum
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

class UsuarioManager(BaseUserManager):
    def create_user(self, username, password, is_admin=False, is_active=True):
        if not username:
            raise ValueError("El usuario debe tener un nombre de usuario")
        user = self.model(username=username, password=password)
        if not password:
            raise ValueError("El usuario debe tener una contraseña")
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, username, password):
        user = self.create_user(username, password)
        user.is_admin = True
        user.is_superuser = True
        user.is_staff = True   
        user.save(using=self._db)
        return user

class Usuario(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=150, unique=True)
    is_admin = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    groups = models.ManyToManyField(
        "auth.Group",
        related_name="usuario_set",  
        blank=True
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        related_name="usuario_permission_set",  
        blank=True
    )
    
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = [] 
    
    objects = UsuarioManager()


class Producto(models.Model):
    nombre = models.CharField(max_length=255)
    tipo = models.CharField(max_length=255)
    proveedor = models.CharField(max_length=255)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField()  # Initial stock

    def __str__(self):
        return f"{self.nombre} - Stock: {self.stock}"
    
class EntradaInventario(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    usuario_admin = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    cantidad = models.IntegerField()
    fecha = models.DateTimeField(auto_now_add=True) 
    
    def save(self, *args, **kwargs):
        if self.pk:  # Updating an existing record
            old_entry = EntradaInventario.objects.get(pk=self.pk)
            diff = self.cantidad - old_entry.cantidad
        else:  # New entry
            diff = self.cantidad

        self.producto.stock += diff
        self.producto.save()
        super().save(*args, **kwargs) 

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs) 

class Venta(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    fecha = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)  # Soft delete flag

    def delete(self, *args, **kwargs):
        """ Soft delete instead of actual delete """
        self.is_deleted = True
        self.save()

class SalidaInventario(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.IntegerField()
    fecha = models.DateTimeField(auto_now_add=True) 
    is_deleted = models.BooleanField(default=False) 

    def save(self, *args, **kwargs):
        if not self.pk:  # New salida
            new_stock_quantity = self.producto.stock - self.cantidad
            if new_stock_quantity < 0:
                raise ValidationError(_("Not enough stock available!"))
            self.producto.stock -= self.cantidad

        self.producto.save()
        super().save(*args, **kwargs)
        
    def delete(self, *args, **kwargs):
        if not self.is_deleted:
            self.is_deleted = True
            self.producto.stock += self.cantidad
            self.save(update_fields=['is_deleted'])