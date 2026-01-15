import os
import sqlite3
import pandas as pd
from google import genai
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from abc import ABC, abstractmethod
from typing import Optional
import logging

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
SAVE_PATH = os.getenv("SAVE_PATH")
BODY_WEIGHT = os.getenv("BODY_WEIGHT")
MAX_ROWS_FOR_API = os.getenv("MAX_ROWS_FOR_API")
USER = "martin"

LOG = logging.getLogger('gemini.log')
FORMATTER = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
file_hdlr = logging.FileHandler('gemini.log')
file_hdlr.setFormatter(FORMATTER)
console_hdlr = logging.StreamHandler()
console_hdlr.setFormatter(FORMATTER)
LOG.setLevel(logging.INFO) 
file_hdlr.setLevel(logging.WARNING)
console_hdlr.setLevel(logging.INFO)
LOG.addHandler(file_hdlr)
LOG.addHandler(console_hdlr)


# --- 1. Abstract Base Class for Data Loading (The Strategy) ---
class DataLoader(ABC):
    """
    Abstract base class to enforce a consistent interface for 
    loading data from different sources.
    """
    @abstractmethod
    def load_data(self) -> str:
        """Reads data and returns it as a string formatted for the LLM."""
        pass

# --- 2. Concrete Implementations for Data Sources ---
class CSVLoader(DataLoader):
    def __init__(self, file_path: str):
        self.file_path = file_path

    def load_data(self) -> str:
        try:
            df = pd.read_csv(self.file_path)
            # Convert dataframe to a string format (CSV) the LLM can understand
            return df.to_csv(index=False)
        except FileNotFoundError:
            raise FileNotFoundError(f"CSV file not found at: {self.file_path}")
        except Exception as e:
            raise Exception(f"Error reading CSV: {e}")

class SQLiteLoader(DataLoader):
    def __init__(self, db_path: str, query: str):
        self.db_path = db_path
        self.query = query

    def load_data(self) -> str:
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            df = pd.read_sql_query(self.query, conn)
            return df.to_csv(index=False)
        except sqlite3.Error as e:
            LOG.info(f"db: {self.db_path}")
            raise Exception(f"Database error: {e}")
        finally:
            if conn:
                conn.close()

# --- 3. The Gemini Agent Class ---
class GeminiAgent:
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash"): # Updated default model
        if not api_key:
            raise ValueError("API Key must be provided.")
        
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name # Store the model name
        self.loadprompt()

    def loadprompt(self) -> None:
        # SAVE_PATH/prompts/system_persona.md

        prompt_path = os.path.join(SAVE_PATH, 'prompts', 'system_persona.md')
        try:
            with open(prompt_path, "r") as file:
                self.system_persona = file.read().strip()
        except FileNotFoundError:
            LOG.warning("Prompt file not found. Using default persona.")
            self.system_persona = "You are a helpful assistant." # Fallback

    def analyze_knowledge(self, knowledge_context: str, user_instruction: str) -> str:
        # Explicitly telling the AI about your custom SQL logic
        
        
        prompt = (
            f"{self.system_persona}\n"
            f"DATASET:\n{knowledge_context}\n\n"
            f"USER INSTRUCTION: {user_instruction}"
        )
        LOG.info(f"Full Prompt: {prompt}")
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text
        except Exception as e:
            return f"Error: {e}"
    
# --- 4. The Orchestrator (Main Controller) ---
class ProcessorApp:
    def __init__(self, data_loader: DataLoader, agent: GeminiAgent):
        self.loader = data_loader
        self.agent = agent

    def run(self, action_instruction: str):
        print("--- Step 1: Loading Data... ---")
        try:
            data_context = self.loader.load_data()
            print(f"Data loaded successfully ({len(data_context)} characters).")
        except Exception as e:
            print(f"Failed to load data: {e}")
            return

        print("--- Step 2: Sending to Gemini... ---")
        result = self.agent.analyze_knowledge(data_context, action_instruction)
                
        print("\n--- Step 3: Result ---")
        print(result)

# --- Usage Example ---
if __name__ == "__main__":
    # this will be refactored into hevysync.py later... for now some values are hardcoded

    if SAVE_PATH: #save path has been set
        db = os.path.join(SAVE_PATH, USER, "-hevy.db")
    else:
        LOG.warning(f"SAVE_PATH not set in .env. Using current folder")
        db = f"{USER}-hevy.db"
    query = "SELECT * FROM v_workout_analytics ORDER BY start_time DESC LIMIT 1"

    source = SQLiteLoader(db, query)
    # Initialize Agent
    try:
        agent = GeminiAgent(api_key=API_KEY)
        
        # Initialize Application
        app = ProcessorApp(data_loader=source, agent=agent)

        # Run with specific instruction
        my_instruction = (
    "Analyse my workout data from the DATASET provided. You know the field mappings for this data set. Specifically:\n"
    "1. Look at the current maximum weight being lifted on major compound lifts (squat, deadlift, bench press, overhead press), "
    "as well as other muscle groups and exercises that benefit from progressive overload in the past 4-8 weeks. Provide a recommended weight to use for the next workout \n"
    "2. Identify weak points in the current programme such as junk volume or neglected muscles, based on the last 2-3 weeks of data available\n"
    "3. Identify any plateaus or regressions in performance for key lifts over the past 8 weeks. Suggest strategies to overcome these plateaus. \n"
    "4. Provide general recommendations for improving strength and physique based on the data trends you observe."
        )
        
        app.run(my_instruction)

    except ValueError as ve:
        print(ve)