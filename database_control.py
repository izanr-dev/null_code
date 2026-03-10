import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

class AdminController:
    
    def __init__(self):
        url: str = os.getenv("SUPABASE_URL")
        key: str = os.getenv("SUPABASE_KEY")
        self.supabase: Client = create_client(url, key)

    # ==========================================
    # ESTADÍSTICAS
    # ==========================================
    def show_statistics(self):
        print("\n--- ESTADISTICAS DE LA PLATAFORMA ---")
        try:
            users = self.supabase.table("users").select("id").execute().data
            projects = self.supabase.table("projects").select("id").execute().data
            files = self.supabase.table("files").select("id").execute().data
            
            print(f"Total Usuarios:  {len(users)}")
            print(f"Total Proyectos: {len(projects)}")
            print(f"Total Archivos:  {len(files)}")
        except Exception as e:
            print(f"[ERROR] Obteniendo estadisticas: {e}")

    # ==========================================
    # GESTION DE USUARIOS
    # ==========================================
    def list_users(self):
        try:
            response = self.supabase.table("users").select("*").execute()
            print("\n--- LISTA DE USUARIOS ---")
            for u in response.data:
                print(f"[{u['plan'].upper()}] {u['email']} (ID: {u['id']})")
        except Exception as e:
            print(f"[ERROR] Listando usuarios: {e}")

    def create_user_manual(self, email: str, plan: str):
        try:
            # In Supabase Auth, a password is required. We assign a default one for manual creation.
            default_password = "NullCodeAdmin123!"
            self.supabase.auth.sign_up({
                "email": email,
                "password": default_password
            })
            
            # After creation, update their plan in the public table
            self.supabase.table("users").update({"plan": plan}).eq("email", email).execute()
            
            print(f"[EXITO] Usuario {email} creado con plan {plan}.")
            print(f"[INFO] Contraseña temporal asignada: {default_password}")
        except Exception as e:
            print(f"[ERROR] Creando usuario: {e}")

    def change_subscription(self, email: str, new_plan: str):
        try:
            user_data = self.supabase.table("users").select("id").eq("email", email).execute().data
            if not user_data:
                print(f"[ERROR] Usuario {email} no encontrado.")
                return
            
            user_id = user_data[0]['id']
            
            self.supabase.table("users").update(
                {
                    "plan": new_plan
                }
            ).eq("id", user_id).execute()
            
            print(f"[EXITO] Suscripcion de {email} actualizada a {new_plan}.")
        except Exception as e:
            print(f"[ERROR] Cambiando suscripcion: {e}")

    def delete_user(self, email: str):
        try:
            response = self.supabase.table("users").delete().eq("email", email).execute()
            if response.data:
                print(f"[INFO] Usuario {email} y todos sus datos eliminados en cascada.")
            else:
                print(f"[ERROR] Usuario {email} no encontrado.")
        except Exception as e:
            print(f"[ERROR] Eliminando usuario: {e}")

    # ==========================================
    # GESTION DE ARCHIVOS
    # ==========================================
    def list_all_files(self):
        try:
            response = self.supabase.table("files").select("id, filename, ai_language, project_id").execute()
            print("\n--- LISTA DE ARCHIVOS GLOBALES ---")
            for f in response.data:
                lang = f['ai_language'] if f['ai_language'] else "No traducido"
                print(f"Archivo: {f['filename']} | Lenguaje IA: {lang} | ID: {f['id']}")
        except Exception as e:
            print(f"[ERROR] Listando archivos: {e}")

    def view_file_content(self, file_id: str):
        try:
            response = self.supabase.table("files").select("*").eq("id", file_id).execute()
            if not response.data:
                print("[ERROR] Archivo no encontrado.")
                return
            
            f = response.data[0]
            print(f"\n=== ARCHIVO: {f['filename']} ===")
            print(f"ID Proyecto: {f['project_id']}")
            print(f"Lenguaje IA: {f['ai_language']}")
            print("\n--- PSEUDOCODIGO (Usuario) ---")
            print(f['pseudocode'])
            print("\n--- CODIGO TRADUCIDO (IA) ---")
            print(f['translated_code'])
            print("==================================")
        except Exception as e:
            print(f"[ERROR] Leyendo archivo: {e}")

    # ==========================================
    # ZONA DE PELIGRO
    # ==========================================
    def nuke_database(self):
        print("\n[ADVERTENCIA] ESTO BORRARA TODOS LOS DATOS DE LA PLATAFORMA")
        confirmacion = input("Escribe 'BORRAR TODO' para confirmar: ")
        
        if confirmacion == "BORRAR TODO":
            try:
                self.supabase.table("users").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
                print("[INFO] Base de datos reiniciada por completo. Todo ha sido eliminado.")
            except Exception as e:
                print(f"[ERROR] Al intentar vaciar la base de datos: {e}")
        else:
            print("[INFO] Operacion cancelada.")


# ==========================================
# MENU INTERACTIVO (CLI)
# ==========================================
def menu():
    admin = AdminController()
    
    while True:
        print("\n" + "="*45)
        print("    PANEL DE CONTROL ADMIN - NL2EXEC")
        print("="*45)
        print("1. Ver estadisticas")
        print("2. Listar todos los usuarios")
        print("3. Crear usuario manualmente")
        print("4. Cambiar plan de usuario (Free/Unlimited)")
        print("5. Listar todos los archivos globales")
        print("6. Inspeccionar contenido de un archivo")
        print("7. Eliminar un usuario (y todos sus datos)")
        print("8. [NUKE] Borrar toda la base de datos")
        print("0. Salir")
        
        opcion = input("\nElige una opcion: ")

        if opcion == "1":
            admin.show_statistics()
            
        elif opcion == "2":
            admin.list_users()
            
        elif opcion == "3":
            email = input("Email del nuevo usuario: ")
            plan = input("Plan (free/unlimited): ")
            admin.create_user_manual(email, plan)
            
        elif opcion == "4":
            email = input("Email del usuario a modificar: ")
            plan = input("Nuevo plan (free/unlimited): ")
            admin.change_subscription(email, plan)
            
        elif opcion == "5":
            admin.list_all_files()
            
        elif opcion == "6":
            file_id = input("Introduce el ID exacto del archivo: ")
            admin.view_file_content(file_id)
            
        elif opcion == "7":
            email = input("Email del usuario a ELIMINAR: ")
            admin.delete_user(email)
            
        elif opcion == "8":
            admin.nuke_database()
            
        elif opcion == "0":
            print("[INFO] Saliendo del panel de control...")
            break
            
        else:
            print("[ERROR] Opcion no valida.")

if __name__ == "__main__":
    menu()