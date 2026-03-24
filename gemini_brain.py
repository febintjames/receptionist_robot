import os
import time
import re
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed — will use environment variables directly

from google import genai

# Optional Groq fallback
try:
    from groq import Groq
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False

class ChatBrain:
    def __init__(self):
        # ── Gemini (primary) ──
        self.api_key = os.environ.get("GEMINI_API_KEY")

        if not self.api_key or self.api_key == "paste-your-key-here":
            print("Warning: GEMINI_API_KEY not found or not set!")
            print("Get a free key at: https://aistudio.google.com/apikey")
            print("Then paste it into the .env file")
            self.client = None
        else:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"Failed to initialize Gemini: {e}")
                self.client = None

        self.model_name = "gemini-2.0-flash"

        # ── Groq (fallback) ──
        self.groq_client = None
        groq_key = os.environ.get("GROQ_API_KEY")
        if _GROQ_AVAILABLE and groq_key and groq_key != "your-groq-key-here":
            try:
                self.groq_client = Groq(api_key=groq_key)
                self.groq_model = "llama-3.3-70b-versatile"
                print("Groq fallback: ready ✓")
            except Exception as e:
                print(f"Groq fallback init failed: {e}")

        # System instruction for Luminar receptionist
        self.system_prompt = (
            "You are the AI Receptionist for Luminar Technolab, situated in Kakkanad, Kochi (near Infopark). "
            "Luminar Technolab is an ISO 9001:2015 certified IT finishing school affiliated with NACTET. "
            "STRICT RULES:\n"
            "- ONLY answer questions about Luminar Technolab courses, placements, timings, and location.\n"
            "- If someone asks anything unrelated, politely say: 'I can only help with Luminar Technolab information.'\n"
            "- Respond in the SAME LANGUAGE the user speaks (Malayalam, Hindi, or English).\n"
            "- Key courses: Data Science & AI/ML (6 months), Python Full Stack (6 months), "
            "MEAN/MERN Stack (6 months), Software Testing (4 months), Flutter (4 months), "
            "Digital Marketing (3 months), Robotics with AI & IoT (6 months).\n"
            "- Luminar's mission is 100% placement support with resume prep and mock interviews.\n"
            "- Be professional, friendly, and concise.\n"
            "- DO NOT use any action brackets like [nods] or [points] or [waves].\n"
            "- Do NOT start every answer with the full introduction 'Welcome to Luminar Technolab, located in the heart of Kakkanad...'. Start your answers naturally."
        )

        self.conversation_history = []
        self.response_count = 0

    def reset(self):
        """Clear conversation history — call between interaction sessions."""
        self.conversation_history = []
        self.response_count = 0

    def get_response(self, user_input):
        """Sends user input and returns AI response. Tries Groq first, Gemini as fallback."""
        if not self.client and not self.groq_client:
            return "I'm sorry, no AI backend is configured. Please add GROQ_API_KEY or GEMINI_API_KEY to .env file."

        self.conversation_history.append({"role": "user", "content": user_input})

        # Style hint based on conversation progress
        if self.response_count == 0:
            style_hint = (
                "\nThis is the visitor's first question. Give a warm, detailed, and comprehensive answer. "
                "Your response MUST be between 120 and 150 words long to provide thorough information."
            )
        else:
            style_hint = (
                "\nThis is a follow-up question. Your answer MUST be between 60 and 90 words long. "
                "CRITICAL INSTRUCTION: Do NOT repeat any information you have already provided in previous responses! "
                "Provide exclusively new, helpful information."
            )

        # ── Try Groq first (faster, higher free quota) ──
        if self.groq_client:
            try:
                completion = self.groq_client.chat.completions.create(
                    model=self.groq_model,
                    messages=[
                        {"role": "system", "content": self.system_prompt + style_hint},
                        *[{"role": m["role"], "content": m["content"]} for m in self.conversation_history]
                    ],
                    temperature=0.7,
                    max_tokens=1024,
                )
                reply = completion.choices[0].message.content
                self.conversation_history.append({"role": "assistant", "content": reply})
                self.response_count += 1
                return reply
            except Exception as e:
                print(f"Groq failed: {e}, trying Gemini fallback...")

        # ── Gemini fallback ──
        if self.client:
            try:
                contents = []
                for msg in self.conversation_history:
                    role = "user" if msg["role"] == "user" else "model"
                    contents.append({"role": role, "parts": [{"text": msg["content"]}]})

                for attempt in range(2):
                    try:
                        response = self.client.models.generate_content(
                            model=self.model_name,
                            contents=contents,
                            config={
                                "system_instruction": self.system_prompt + style_hint,
                                "temperature": 0.7,
                                "max_output_tokens": 1024,
                            }
                        )
                        reply = response.text
                        self.conversation_history.append({"role": "assistant", "content": reply})
                        self.response_count += 1
                        return reply
                    except Exception as e:
                        err_str = str(e)
                        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                            match = re.search(r'retry in (\d+\.?\d*)', err_str, re.IGNORECASE)
                            wait_time = float(match.group(1)) if match else 5
                            print(f"Gemini rate limited (attempt {attempt+1}/2). Waiting {wait_time:.0f}s...")
                            time.sleep(min(wait_time, 15))
                        else:
                            print(f"Gemini error: {e}")
                            break
            except Exception as e:
                print(f"Gemini fallback failed: {e}")

        return "I'm having trouble connecting right now. Please try again in a moment."


if __name__ == "__main__":
    brain = ChatBrain()
    print(brain.get_response("Hello, who are you?"))
    print("---")
    print(brain.get_response("What courses do you offer?"))
