import os
import stripe
from dotenv import load_dotenv

load_dotenv()

class StripeManager:
    
    def __init__(self):
        stripe.api_key = os.getenv("STRIPE_API_KEY")
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        self.premium_price_id = os.getenv("STRIPE_PRICE_ID")
        self.domain_url = os.getenv("DOMAIN_URL", "http://localhost:8000")

    def create_checkout_session(self, user_email: str, user_id: str) -> dict:
        """
        Genera una sesion de pago en Stripe. 
        Devuelve un diccionario con la URL de pago y el ID de la sesion.
        """
        try:
            session = stripe.checkout.Session.create(
                customer_email = user_email,
                client_reference_id = user_id,
                payment_method_types = 
                [
                    "card"
                ],
                line_items = 
                [
                    {
                        "price": self.premium_price_id,
                        "quantity": 1,
                    }
                ],
                mode = "subscription",
                success_url = f"{self.domain_url}/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url = f"{self.domain_url}/cancel",
            )
            
            return \
            {
                "status": "success",
                "url": session.url,
                "session_id": session.id
            }
            
        except Exception as e:
            print(f"[ERROR] Creando sesion de pago Stripe: {e}")
            return \
            {
                "status": "error",
                "url": None,
                "session_id": None
            }

    def create_customer_portal(self, customer_id: str) -> str:
        """
        Genera la URL del portal de cliente para que cancelen o cambien tarjeta.
        """
        try:
            session = stripe.billing_portal.Session.create(
                customer = customer_id,
                return_url = f"{self.domain_url}/dashboard"
            )
            return session.url
            
        except Exception as e:
            print(f"[ERROR] Creando portal de cliente: {e}")
            return None

    def verify_webhook(self, payload: bytes, sig_header: str):
        """
        Verifica la firma criptografica de Stripe para asegurar que el Webhook es legitimo.
        """
        try:
            event = stripe.Webhook.construct_event(
                payload = payload, 
                sig_header = sig_header, 
                secret = self.webhook_secret
            )
            return event
            
        except stripe.error.SignatureVerificationError as e:
            print(f"[ERROR] Firma de Webhook invalida: {e}")
            return None
        except ValueError as e:
            print(f"[ERROR] Payload de Webhook invalido: {e}")
            return None