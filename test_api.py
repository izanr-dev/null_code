import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def run_api_tests():
    print("=== INICIANDO PRUEBAS DE LA API REST ===")
    
    # 1. Comprobar estado del servidor
    print("\n[INFO] 1. Comprobando estado del servidor...")
    try:
        res = requests.get(f"{BASE_URL}/")
        print(f"Respuesta: {res.json()}")
    except requests.exceptions.ConnectionError:
        print("[ERROR] El servidor no esta corriendo. Ejecuta 'uvicorn main:app --reload' primero.")
        return

    # 2. Registrar/Obtener Usuario
    print("\n[INFO] 2. Creando usuario de prueba via API...")
    user_payload = {"email": "api_test@micompilador.com"}
    res_user = requests.post(f"{BASE_URL}/api/users", json=user_payload)
    user_data = res_user.json()
    print(f"Usuario: {user_data.get('email')} | ID: {user_data.get('id')}")
    
    user_id = user_data.get('id')

    # 3. Crear Proyecto
    print("\n[INFO] 3. Creando proyecto via API...")
    proj_payload = {
        "user_id": user_id,
        "name": "Proyecto de Prueba API"
    }
    res_proj = requests.post(f"{BASE_URL}/api/projects", json=proj_payload)
    proj_data = res_proj.json()
    print(f"Proyecto: {proj_data.get('name')} | ID: {proj_data.get('id')}")
    
    project_id = proj_data.get('id')

    # 4. Compilar Código
    print("\n[INFO] 4. Enviando pseudocodigo al compilador IA via API...")
    compile_payload = {
        "user_id": user_id,
        "project_id": project_id,
        "filename": "calculadora.pse",
        "pseudocode": "pide dos numeros enteros y muestra su suma por pantalla"
    }
    
    res_compile = requests.post(f"{BASE_URL}/api/compile", json=compile_payload)
    
    if res_compile.status_code == 200:
        print("[EXITO] Respuesta del compilador:")
        print(json.dumps(res_compile.json(), indent=4, ensure_ascii=False))
    else:
        print(f"[ERROR] Fallo la compilacion. Status Code: {res_compile.status_code}")
        print(res_compile.text)

    # 5. Probar generacion de Checkout de Stripe
    print("\n[INFO] 5. Solicitando URL de Stripe via API...")
    checkout_payload = {
        "email": user_data.get('email'),
        "user_id": user_id
    }
    res_checkout = requests.post(f"{BASE_URL}/api/checkout", json=checkout_payload)
    if res_checkout.status_code == 200:
        print("[EXITO] URL de Checkout generada:")
        print(res_checkout.json().get("url"))
    else:
        print(f"[ERROR] Fallo al generar Checkout. Status Code: {res_checkout.status_code}")

if __name__ == "__main__":
    run_api_tests()