from stripe_manager import StripeManager
from database import DatabaseManager

def test_stripe_connection():
    db = DatabaseManager()
    pagos = StripeManager()
    
    print("=== INICIANDO PRUEBA DE CONEXION CON STRIPE ===")
    
    # 1. Preparamos un usuario de prueba en la BBDD
    email_prueba = "cliente_premium@test.com"
    print(f"\n[INFO] 1. Verificando/Creando usuario: {email_prueba}")
    
    user = db.get_user_by_email(email_prueba)
    if not user:
        user = db.create_user(email_prueba)
        print(f"       Usuario creado con ID: {user['id']}")
    else:
        print(f"       Usuario existente con ID: {user['id']}")
        print(f"       Plan actual: {user['plan']}")

    # 2. Generar enlace de pago
    print("\n[INFO] 2. Solicitando sesion de Checkout a Stripe...")
    checkout_data = pagos.create_checkout_session(
        user_email = user['email'],
        user_id = user['id']
    )
    
    if checkout_data["status"] == "success":
        print("\n[EXITO] Sesion de pago creada correctamente.")
        print("-" * 50)
        print("URL DE PAGO (Haz Ctrl+Clic para abrir en el navegador):")
        print(checkout_data["url"])
        print("-" * 50)
        print("\nINSTRUCCIONES PARA PROBAR:")
        print("1. Abre la URL en tu navegador.")
        print("2. Usa una tarjeta de prueba de Stripe (ej. 4242 4242 4242 4242, cualquier fecha futura, cualquier CVC).")
        print("3. Realiza el pago.")
    else:
        print("\n[ERROR] No se pudo crear la sesion de pago. Verifica tu STRIPE_API_KEY y STRIPE_PRICE_ID.")

if __name__ == "__main__":
    test_stripe_connection()