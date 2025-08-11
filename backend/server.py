from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import base64
import os
import re
import logging
import tempfile
import requests
from typing import List, Dict, Any
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set up Google API key
GOOGLE_API_KEY = "AIzaSyAfwOUx4w2yFcFgIi_alLNuzwKskGR7TSk"
os.environ['GOOGLE_API_KEY'] = GOOGLE_API_KEY

app = FastAPI(
    title="Speech Rate Analyzer API",
    description="Real-time speech transcription with rate analysis",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Google Speech client (using REST API instead of client library)
speech_client = None  # Will use REST API calls instead

# Sample stories
STORIES = {
    "english": {
        "title": "The Digital Revolution",
        "content": """In the twenty-first century, technology has fundamentally transformed the way we live, work, and communicate. The digital revolution has brought unprecedented changes to virtually every aspect of human existence. From smartphones that connect us instantly to people across the globe, to artificial intelligence systems that can process information faster than any human brain, we are witnessing a transformation that rivals the industrial revolution in its scope and impact.

Social media platforms have redefined how we share information and maintain relationships. Online shopping has revolutionized commerce, allowing consumers to purchase products from anywhere in the world with just a few clicks. Remote work has become commonplace, enabling professionals to collaborate effectively regardless of their physical location. Educational institutions have embraced online learning, making knowledge more accessible than ever before.

However, this digital transformation also presents significant challenges. Privacy concerns have emerged as companies collect vast amounts of personal data. Cybersecurity threats have multiplied, requiring constant vigilance and protection. The digital divide has created disparities between those who have access to technology and those who do not. Social media has sometimes fostered misinformation and reduced face-to-face human interaction.

Despite these challenges, the benefits of the digital revolution are undeniable. Medical advances powered by technology have saved countless lives. Scientific research has accelerated through computational modeling and data analysis. Environmental monitoring has improved through satellite technology and sensors. Transportation has become more efficient through GPS navigation and ride-sharing applications.

Looking forward, emerging technologies like virtual reality, blockchain, and quantum computing promise to bring even more dramatic changes. The key to navigating this digital future successfully lies in balancing technological innovation with human values, ensuring that technology serves humanity rather than the other way around."""
    },
    "hindi": {
        "title": "भारत की सांस्कृतिक विविधता",
        "content": """भारत एक अनोखा देश है जो अपनी समृद्ध सांस्कृतिक विविधता के लिए प्रसिद्ध है। यहाँ विभिन्न धर्म, भाषाएँ, परंपराएँ और जीवनशैली एक साथ फलती-फूलती हैं। उत्तर से दक्षिण तक और पूर्व से पश्चिम तक, हर राज्य की अपनी विशिष्ट संस्कृति है।

भारत में बाईस आधिकारिक भाषाएँ हैं और सैकड़ों स्थानीय बोलियाँ बोली जाती हैं। हिंदी सबसे व्यापक रूप से बोली जाने वाली भाषा है, लेकिन तमिल, बंगाली, मराठी, तेलुगु जैसी अन्य भाषाओं का भी अपना महत्वपूर्ण स्थान है। यह भाषाई विविधता भारत की सबसे बड़ी ताकतों में से एक है।

त्योहारों के मामले में भारत का कोई मुकाबला नहीं है। होली का रंग-बिरंगा उत्सव, दीपावली की रोशनी, ईद की खुशियाँ, क्रिसमस का आनंद, दुर्गा पूजा का उत्साह - ये सभी त्योहार पूरे देश में मनाए जाते हैं। इन त्योहारों के दौरान धर्म, जाति और भाषा की सभी बाधाएँ टूट जाती हैं।

भारतीय खान-पान भी अत्यंत विविधतापूर्ण है। उत्तर भारत के मसालेदार व्यंजनों से लेकर दक्षिण भारत के नारियल आधारित खाद्य पदार्थों तक, हर क्षेत्र का अपना स्वाद है। गुजराती धोकला, बंगाली मिठाई, पंजाबी छोले भटूरे, और केरल की मछली करी जैसे व्यंजन देश भर में प्रसिद्ध हैं।

कला और संस्कृति के क्षेत्र में भी भारत का योगदान अमूल्य है। शास्त्रीय संगीत और नृत्य की विविध परंपराएँ, हस्तशिल्प की समृद्ध विरासत, और आधुनिक कला के नवाचार सभी एक साथ फल-फूल रहे हैं। यह विविधता ही भारत की असली पहचान है और इसी से हमारी एकता मजबूत होती है।"""
    }
}

# Connection manager for WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_configs: Dict[WebSocket, dict] = {}
    
    async def connect(self, websocket: WebSocket, config: dict = None):
        await websocket.accept()
        self.active_connections.append(websocket)
        if config:
            self.connection_configs[websocket] = config
        logger.info(f"New WebSocket connection established. Total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.connection_configs:
            del self.connection_configs[websocket]
        logger.info(f"WebSocket connection closed. Remaining: {len(self.active_connections)}")

manager = ConnectionManager()

class SpeechRateAnalyzer:
    def __init__(self):
        self.words_by_minute = {}
        self.total_words = 0
        self.start_time = None
        
    def add_words(self, transcript: str, timestamp: float):
        """Add words to the analyzer with timestamp"""
        if self.start_time is None:
            self.start_time = timestamp
        
        # Remove punctuation and count words
        clean_text = re.sub(r'[^\w\s]', '', transcript).strip()
        if not clean_text:
            return
            
        words = clean_text.split()
        if not words:
            return
        
        # Calculate which minute this belongs to
        elapsed_time = timestamp - self.start_time
        minute_index = int(elapsed_time // 60)
        
        # Add words to the appropriate minute
        if minute_index not in self.words_by_minute:
            self.words_by_minute[minute_index] = 0
        
        new_words = len(words)
        self.words_by_minute[minute_index] += new_words
        self.total_words += new_words
        
    def get_minute_breakdown(self):
        """Get words per minute breakdown"""
        breakdown = []
        for minute in sorted(self.words_by_minute.keys()):
            word_count = self.words_by_minute[minute]
            breakdown.append({
                "minute": f"{minute}-{minute+1} min",
                "words": word_count
            })
        return breakdown
    
    def get_average_wpm(self):
        """Calculate average words per minute"""
        if not self.words_by_minute:
            return 0
        
        total_minutes = max(self.words_by_minute.keys()) + 1 if self.words_by_minute else 1
        return round(self.total_words / total_minutes) if total_minutes > 0 else 0

async def transcribe_audio_with_google_api(audio_data: bytes, language_code: str = "en-US") -> Dict[str, Any]:
    """Transcribe audio using Google Speech-to-Text REST API"""
    try:
        # Convert audio data to base64
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        # Google Speech-to-Text REST API URL
        url = f"https://speech.googleapis.com/v1/speech:recognize?key={GOOGLE_API_KEY}"
        
        # Request payload
        data = {
            "config": {
                "encoding": "WEBM_OPUS",
                "sampleRateHertz": 48000,
                "languageCode": language_code,
                "enableWordTimeOffsets": True,
                "enableAutomaticPunctuation": True,
                "model": "latest_short",
                "useEnhanced": True
            },
            "audio": {
                "content": audio_base64
            }
        }
        
        # Make API call
        response = requests.post(url, json=data, headers={'Content-Type': 'application/json'})
        
        if response.status_code == 200:
            result = response.json()
            return result
        else:
            logger.error(f"Google API error: {response.status_code} - {response.text}")
            return {"error": f"API error: {response.status_code}"}
            
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        return {"error": str(e)}

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "speech_client_available": speech_client is not None}

@app.get("/api/stories")
async def get_stories():
    """Get available stories"""
    return {"stories": STORIES}

@app.websocket("/api/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    """Real-time speech transcription via WebSocket"""
    await manager.connect(websocket)
    
    # Reset analyzer for new session
    global analyzer
    analyzer = SpeechRateAnalyzer()
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "start_session":
                # Initialize session
                language_code = message.get("language", "en-US")
                await websocket.send_text(json.dumps({
                    "type": "session_started",
                    "language": language_code,
                    "message": "Recording session started"
                }))
                
            elif message.get("type") == "audio":
                # Process audio data
                try:
                    # Decode base64 audio data
                    audio_data = base64.b64decode(message["data"])
                    
                    # For now, simulate transcription (replace with actual Google Speech API call)
                    # In real implementation, you would use Google Speech-to-Text API here
                    await websocket.send_text(json.dumps({
                        "type": "transcript",
                        "transcript": "Sample transcription text",
                        "is_final": True,
                        "timestamp": datetime.now().timestamp()
                    }))
                    
                except Exception as e:
                    logger.error(f"Audio processing error: {str(e)}")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Audio processing failed: {str(e)}"
                    }))
                    
            elif message.get("type") == "end_session":
                # End session and provide results
                breakdown = analyzer.get_minute_breakdown()
                avg_wpm = analyzer.get_average_wpm()
                
                await websocket.send_text(json.dumps({
                    "type": "session_results",
                    "breakdown": breakdown,
                    "average_wpm": avg_wpm,
                    "total_words": analyzer.total_words
                }))
                break
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": str(e)
        }))
    finally:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)