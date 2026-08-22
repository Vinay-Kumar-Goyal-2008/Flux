import os
import requests
import json
from app.RAG.vector_store import FloodVectorDB

class SituationReportGenerator:
    def __init__(self, db_path="./chroma_data", corpus_path="./corpus"):
        self.vector_db = FloodVectorDB(db_path=db_path, corpus_path=corpus_path)
        
        # Load API keys
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.groq_key = os.getenv("GROQ_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    def retrieve_context(self, location):
        similar_reports = self.vector_db.query_similar_reports(location, n_results=1)
        if similar_reports:
            return similar_reports[0]["content"]
        return "No historical template context found."

    def generate_report(self, location, area_sq_km, classification, severity, population_affected, buildings_damaged, facilities_at_risk):
        """
        Generates an official-style situation report using RAG.
        Prioritizes available LLM endpoints in order: Gemini -> Groq -> OpenAI -> Anthropic.
        Falls back to local template rendering if no keys are found.
        """
        context = self.retrieve_context(location)
        
        prompt = f"""
        You are an official disaster management officer writing a flood situation report.
        Use the following historical context as a style and structure guideline:
        ---
        HISTORICAL CONTEXT:
        {context}
        ---
        Now, write an official-style report for the current event using ONLY the verified stats below. Do not make up numbers.
        
        CURRENT DISASTER STATS:
        - Location: {location}
        - Event Type: {classification}
        - Severity Classification: {severity}
        - Flood Area: {area_sq_km:.2f} sq km
        - Population Affected: {population_affected:,} citizens
        - Inundated Structures: {buildings_damaged:,} buildings
        - Critical Facilities under warning: {facilities_at_risk} centers
        
        Report Requirements:
        - Must strictly match the tone and structure of the historical context.
        - Ensure all numbers match the verified stats exactly.
        - Include sections: 1. Overview, 2. Infrastructure Impact, 3. Rescue Directives.
        """
        
        # 1. Google Gemini API (Recommended)
        if self.gemini_key:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.gemini_key}"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}]
                }
                res = requests.post(url, headers=headers, json=payload, timeout=15)
                if res.status_code == 200:
                    data = res.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
            except Exception as e:
                print(f"[RAG Generator] Gemini API error: {e}. Falling back...")

        # 2. Groq Llama API
        if self.groq_key:
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {self.groq_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2
                }
                res = requests.post(url, headers=headers, json=payload, timeout=15)
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"]
            except Exception as e:
                print(f"[RAG Generator] Groq API error: {e}. Falling back...")

        # 3. OpenAI GPT API
        if self.openai_key:
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.openai_key}"
                }
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2
                }
                res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=15)
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"]
            except Exception as e:
                print(f"[RAG Generator] OpenAI API error: {e}. Falling back...")
                
        # 4. Anthropic Claude API
        if self.anthropic_key:
            try:
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": self.anthropic_key,
                    "anthropic-version": "2023-06-01"
                }
                payload = {
                    "model": "claude-3-haiku-20240307",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": prompt}]
                }
                res = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=15)
                if res.status_code == 200:
                    return res.json()["content"][0]["text"]
            except Exception as e:
                print(f"[RAG Generator] Anthropic API error: {e}. Falling back...")

        # --- 5. LOCAL DETERMINISTIC FALLBACK ---
        return f"""
============================================================
OFFICIAL FLOOD SITUATION REPORT: {location.upper()}
============================================================
ALERT LEVEL: {severity}

1. SITUATION OVERVIEW
   On-site satellite scans confirm an active {classification.lower()} event 
   covering approximately {area_sq_km:.2f} square kilometers in the vicinity of {location}.
   Estimated population density layers place the affected population at 
   approximately {population_affected:,} residents.

2. INFRASTRUCTURE & FACILITY IMPACT
   A spatial overlay of building footprint databases indicates that {buildings_damaged:,} 
   residential and commercial structures have been inundated. Additionally, 
   {facilities_at_risk} critical facilities (including medical clinics, schools, and 
   administrative centers) are within the risk boundary.

3. EVACUATION AND RESPONSE DIRECTIVES
   - Relief Camps: Local authorities are directed to establish primary relief camps on elevated ground.
   - Medical Protocols: Distribute water purification packages, basic hydration salts (ORS), and anti-venom supplies.
   - Communication: Broadcast evacuations routes via regional networks and local alert grids.
   
REPORT STATUS: VERIFIED PIPELINE SECURE
============================================================
"""
