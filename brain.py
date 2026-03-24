import os
from groq import Groq

class ChatBrain:
    def __init__(self, api_key=None):
        # Try to get API key from environment
        self.api_key = os.environ.get("GROQ_API_KEY")
        
        if not self.api_key or self.api_key.startswith("gsk_."):
            # Check if there's a hardcoded one (last resort, though not recommended)
            self.api_key = api_key if (api_key and not api_key.startswith("gsk_.")) else None
            
        if not self.api_key:
            print("Warning: Groq API Key not found in environment or brain.py")
            self.client = None
        else:
            try:
                self.client = Groq(api_key=self.api_key)
            except Exception as e:
                print(f"Failed to initialize Groq client: {e}")
                self.client = None

        self.model = "llama-3.3-70b-versatile"
        
        # System instruction for robotic personality
        self.system_prompt = (
            "You are the AI Receptionist for Luminar Technolab, situated in Kakkanad, Kochi (near Infopark). "
            "Luminar Technolab is an ISO 9001:2015 certified IT finishing school affiliated with NACTET. "
            "Your goal is to help students with course details and placement information. "
            "Key courses include: Data Science & Big Data (AI/ML), Python Full Stack (Django/Angular), MEAN/MERN Stack, Software Testing, Flutter, Digital Marketing, and Robotics with AI & IoT. "
            "Luminar mission is 100% placement support. Mention resume preparation and mock interviews if asked about jobs. "
            "Be professional, friendly, and concise. Your arm configuration has elbows and wrists (no shoulders). "
            "When appropriate, describe a hand gesture you might do in brackets like [waves] or [points]."
        )

        self.conversation_history = []
        self.response_count = 0  # Track response count for style switching

    def reset(self):
        """Clear conversation history — call between interaction sessions."""
        self.conversation_history = []
        self.response_count = 0

    def get_response(self, user_input):
        """Sends user input to Groq and returns the text response."""
        if not self.client:
            return "I'm sorry, I'm not currently connected to my cloud brain (internet). Please check my configuration."

        self.conversation_history.append({"role": "user", "content": user_input})

        try:
            # First response: detailed. Subsequent: concise pointwise.
            if self.response_count == 0:
                style_hint = (
                    "\nThis is the visitor's first question. Give a warm, detailed, and comprehensive answer "
                    "to make a great first impression. Be thorough and welcoming."
                )
            else:
                style_hint = (
                    "\nThis is a follow-up question. Keep your answer SHORT and CONCISE. "
                    "Use 2-3 bullet points maximum. No long paragraphs. Be direct and to the point."
                )

            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt + style_hint},
                    *self.conversation_history
                ],
                temperature=0.7,
                max_tokens=512,
                top_p=1,
                stream=False,
                stop=None,
            )
            reply = completion.choices[0].message.content
            self.conversation_history.append({"role": "assistant", "content": reply})
            self.response_count += 1
            return reply
        except Exception as e:
            print(f"Error calling Groq API: {e}")
            return "I'm having a bit of trouble connecting to the internet right now. Please try again in a moment."

if __name__ == "__main__":
    # Test script (requires GROQ_API_KEY env var)
    brain = ChatBrain()
    print(brain.get_response("Hello, who are you?"))
