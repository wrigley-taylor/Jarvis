import os
import speech_recognition as sr
import subprocess
import requests
from datetime import datetime
import re
import openai
import logging
import random
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_env_file(Path(__file__).resolve().parent / ".env")

# CONFIGURATION
DUMMY_FLIP_URL = "http://example.com/fake-flip"
EXIT_WORDS = ["goodbye", "exit", "quit"]
SMART_HOME_KEYWORDS = ["flip the switch", "turn off", "turn on", "toggle light"]
OLLAMA_MODEL = "phi3:mini"
TTS_VOICE = "ash"
MAX_TTS_LENGTH = 500

# LOG CONFIGURATION
logger = logging.getLogger("Jarvis")
logger.setLevel(logging.DEBUG)

# FILE HANDLER
file_handler = logging.FileHandler('jarvis.log')
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                                   datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(file_formatter)

# CONSOLE STREAM HANDLER
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('[%(levelname)s] %(message)s')
console_handler.setFormatter(console_formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# OPENAI API KEY
openai.api_key = os.getenv("OPENAI_API_KEY", "").strip()
if not openai.api_key:
    logger.error("OPENAI_API_KEY not set. Add it to .env (see .env.example).")
    print("Please set OPENAI_API_KEY in .env or your environment.")
    exit(1)

# STEP MOTOR SIMULATION
class StepperMotorSim:
    def __init__(self):
        self.position = 0

    def rotate(self, degrees):
        self.position += degrees
        logger.info(f"StepperMotorSim rotated {degrees}° -> Current position: {self.position}°")
        speak(f"Rotated {degrees} degrees.")

motor = StepperMotorSim()

# SIMULATED SENSOR
class SimSensor:
    def __init__(self, name):
        self.name = name
        self.value = 0

    def read(self):
        self.value = random.uniform(-10, 10)
        logger.info(f"{self.name} sensor reading: {self.value:.2f}")
        return self.value

gyro_sensor = SimSensor("Gyroscope")

# TEXT TO SPEECH
def speak(text):
    if not text.strip():
        logger.info("Jarvis: (no response to speak)")
        return

    logger.info(f"Jarvis responding: {text}")

    cleaned = re.sub(r"[^\x00-\x7F]+", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > MAX_TTS_LENGTH:
        cleaned = cleaned[:MAX_TTS_LENGTH].rsplit(" ", 1)[0] + "..."

    try:
        with openai.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=TTS_VOICE,
            input=cleaned
        ) as response:
            response.stream_to_file("jarvis.mp3")
        subprocess.run(["afplay", "jarvis.mp3"])
    except Exception as e:
        logger.error("TTS API error", exc_info=True)

# LISTEN FUNCTION
def listen(timeout=5, phrase_limit=6):
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        logger.info("Listening for user command...")
        try:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
        except sr.WaitTimeoutError:
            logger.warning("No speech detected during listening.")
            return ""

    try:
        text = recognizer.recognize_google(audio)
        logger.info(f"User said: {text}")
        return text.lower()
    except sr.UnknownValueError:
        logger.warning("Could not understand user audio.")
        return ""
    except sr.RequestError as e:
        logger.warning(f"Speech recognition service error: {e}")
        return ""

# ACTION FUNCTIONS
def flip_switch_simulated():
    logger.info("Simulated flipping the switch.")
    try:
        requests.get(DUMMY_FLIP_URL)
        speak("Okay, flipping the switch.")
    except Exception as e:
        logger.warning(f"Failed to simulate switch action: {e}")
        speak("Couldn't simulate the switch action.")

def get_current_time():
    now = datetime.now()
    current_time = now.strftime("The time is %I:%M %p")
    logger.info(f"Providing current time: {current_time}")
    return current_time

def ask_ollama(model, prompt):
    logger.debug(f"Sending prompt to Ollama ({model}): {prompt}")
    try:
        process = subprocess.Popen(
            ['ollama', 'run', model],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(input=prompt, timeout=30)
        if stderr:
            logger.warning(f"Ollama stderr: {stderr.strip()}")
        logger.debug(f"Ollama response: {stdout.strip()}")
        return stdout.strip() or "I didn’t get a response."
    except subprocess.TimeoutExpired:
        process.kill()
        logger.warning("Ollama request timed out.")
        return "Sorry, Ollama took too long to respond."
    except Exception as e:
        logger.error(f"Ollama error: {e}", exc_info=True)
        return "Something went wrong with Ollama."

# MAIN LOOP
def main():
    speak("Jarvis is online. I am listening for your commands.")

    while True:
        command = listen(timeout=8, phrase_limit=8)
        if not command:
            continue

        # Exit
        if any(exit_word in command for exit_word in EXIT_WORDS):
            speak("Goodbye!")
            break

        # Light switch
        if any(keyword in command for keyword in SMART_HOME_KEYWORDS):
            flip_switch_simulated()

        # Time request
        elif "what time is it" in command:
            speak(get_current_time())

        # Motor command
        elif "rotate motor" in command:
            match = re.search(r"rotate motor (\d+) degrees", command)
            if match:
                degrees = int(match.group(1))
                motor.rotate(degrees)
            else:
                speak("Please specify degrees to rotate.")

        # Sensor command
        elif "check sensor" in command or "read sensor" in command:
            value = gyro_sensor.read()
            speak(f"{gyro_sensor.name} reading is {value:.2f}")

        # AI response
        else:
            prompt = f"You are Jarvis, my personal AI assistant. I am located in [INSERT CITY], [INSERT STATE]. Answer very briefly and clearly: {command}"
            response = ask_ollama(OLLAMA_MODEL, prompt)
            speak(response)

if __name__ == "__main__":
    main()
