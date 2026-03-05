import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class AICompiler:
    
    def __init__(self):
        self.client = OpenAI(
            api_key = os.getenv("DEEPSEEK_API_KEY"),
            base_url = "https://api.deepseek.com"
        )
        self.model = "deepseek-chat"
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self):
        return """
        You are the core compilation engine of a natural language-based programming environment.
        Your goal is to translate the user's natural language logic into functional, clean Python code.

        STRICT RULES FOR WEB-PYTHON ENVIRONMENT:
        1. Environment: The code runs in a Pyodide WebAssembly environment.
        2. I/O Operations: Use standard `print()`. For user input, the standard `input()` function has been made asynchronous to work with the web terminal. 
           You MUST use `await input("...")`. 
           Example: `name = await input("What is your name? ")`
           DO NOT use custom_prompt or window methods for input. Just use `await input()`.
        3. Visual Interfaces (DOM): 
           - There is a container with id 'ui-container'. Clear it first: `document.getElementById('ui-container').innerHTML = ""`
           - Build interfaces using `from js import document`.
        4. INTERACTIVITY:
           - To make buttons clickeable, use `create_proxy` from `pyodide.ffi`.
           ```python
           from js import document
           from pyodide.ffi import create_proxy
           def on_click(event): print("Clicked!")
           btn = document.createElement("button")
           btn.addEventListener("click", create_proxy(on_click))
           ```
        
        5. YOU MUST respond ONLY with a valid JSON object:
        {
            "status": "success" | "error",
            "code": "string with the Python code" | null,
            "message": "string explaining what is missing" | null,
            "suggestion": "string with a suggestion" | null
        }
        """

    def compile_pseudocode(self, user_text: str) -> dict:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_text}
                ],
                response_format={"type": "json_object"},
                temperature=0.1 
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            return {"status": "error", "code": None, "message": str(e), "suggestion": None}