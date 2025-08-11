import React, { useState, useRef, useEffect } from 'react';
import './App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';
const WS_URL = BACKEND_URL.replace('http', 'ws') + '/api/ws/transcribe';

function App() {
  // State management
  const [stories, setStories] = useState({});
  const [selectedLanguage, setSelectedLanguage] = useState('english');
  const [currentStory, setCurrentStory] = useState(null);
  const [isRecording, setIsRecording] = useState(false);
  const [timeRemaining, setTimeRemaining] = useState(300); // 5 minutes in seconds
  const [transcript, setTranscript] = useState('');
  const [wordCount, setWordCount] = useState(0);
  const [currentMinuteWords, setCurrentMinuteWords] = useState(0);
  const [minuteBreakdown, setMinuteBreakdown] = useState([]);
  const [sessionResults, setSessionResults] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);

  // Refs
  const mediaRecorderRef = useRef(null);
  const websocketRef = useRef(null);
  const timerRef = useRef(null);
  const recordingStartTimeRef = useRef(null);

  // Load stories on component mount
  useEffect(() => {
    loadStories();
  }, []);

  // Timer effect
  useEffect(() => {
    if (isRecording && timeRemaining > 0) {
      timerRef.current = setTimeout(() => {
        setTimeRemaining(prev => prev - 1);
      }, 1000);
    } else if (timeRemaining === 0 && isRecording) {
      stopRecording();
    }

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [isRecording, timeRemaining]);

  const loadStories = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/stories`);
      const data = await response.json();
      setStories(data.stories);
      setCurrentStory(data.stories.english);
    } catch (err) {
      setError('Failed to load stories');
    }
  };

  const handleLanguageChange = (language) => {
    setSelectedLanguage(language);
    setCurrentStory(stories[language]);
  };

  const initializeWebSocket = () => {
    try {
      websocketRef.current = new WebSocket(WS_URL);

      websocketRef.current.onopen = () => {
        setIsConnected(true);
        setError(null);
        console.log('WebSocket connected');
        
        // Start session
        websocketRef.current.send(JSON.stringify({
          type: 'start_session',
          language: selectedLanguage === 'english' ? 'en-US' : 'hi-IN'
        }));
      };

      websocketRef.current.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
      };

      websocketRef.current.onclose = () => {
        setIsConnected(false);
        console.log('WebSocket disconnected');
      };

      websocketRef.current.onerror = (error) => {
        setError('WebSocket connection error');
        console.error('WebSocket error:', error);
      };
    } catch (err) {
      setError('Failed to connect to server');
    }
  };

  const handleWebSocketMessage = (data) => {
    switch (data.type) {
      case 'session_started':
        console.log('Session started:', data.message);
        break;
        
      case 'transcript':
        if (data.is_final) {
          const newTranscript = data.transcript;
          setTranscript(prev => prev + ' ' + newTranscript);
          
          // Count words (remove punctuation)
          const cleanText = newTranscript.replace(/[^\w\s]/g, '').trim();
          const words = cleanText.split(/\s+/).filter(word => word.length > 0);
          const newWordCount = words.length;
          
          setWordCount(prev => prev + newWordCount);
          setCurrentMinuteWords(prev => prev + newWordCount);
        }
        break;
        
      case 'session_results':
        setSessionResults({
          breakdown: data.breakdown,
          averageWpm: data.average_wpm,
          totalWords: data.total_words
        });
        break;
        
      case 'error':
        setError(data.message);
        break;
        
      default:
        break;
    }
  };

  const startRecording = async () => {
    try {
      // Reset state
      setTranscript('');
      setWordCount(0);
      setCurrentMinuteWords(0);
      setMinuteBreakdown([]);
      setSessionResults(null);
      setTimeRemaining(300);
      setError(null);
      
      // Initialize WebSocket
      initializeWebSocket();
      
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          sampleRate: 48000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        } 
      });

      // Setup MediaRecorder
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus',
        audioBitsPerSecond: 64000
      });

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0 && websocketRef.current && websocketRef.current.readyState === WebSocket.OPEN) {
          // Convert blob to base64
          const reader = new FileReader();
          reader.onloadend = () => {
            const base64data = reader.result.split(',')[1];
            websocketRef.current.send(JSON.stringify({
              type: 'audio',
              data: base64data
            }));
          };
          reader.readAsDataURL(event.data);
        }
      };

      mediaRecorder.start(250); // Send data every 250ms
      mediaRecorderRef.current = mediaRecorder;
      recordingStartTimeRef.current = Date.now();
      setIsRecording(true);

    } catch (err) {
      setError('Microphone access denied or not available');
      console.error('Recording error:', err);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
      setIsRecording(false);

      // End session
      if (websocketRef.current && websocketRef.current.readyState === WebSocket.OPEN) {
        websocketRef.current.send(JSON.stringify({
          type: 'end_session'
        }));
      }
    }
  };

  const formatTime = (seconds) => {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  const calculateWordsPerMinute = () => {
    if (!recordingStartTimeRef.current) return 0;
    const elapsedMinutes = (Date.now() - recordingStartTimeRef.current) / (1000 * 60);
    return elapsedMinutes > 0 ? Math.round(wordCount / elapsedMinutes) : 0;
  };

  return (
    <div className="App">
      <header className="app-header">
        <div className="header-content">
          <h1 className="app-title">Speech Rate Analyzer</h1>
          <p className="app-subtitle">Analyze your speaking pace with real-time feedback</p>
        </div>
      </header>

      <main className="main-content">
        {!sessionResults ? (
          <>
            {/* Story Selection */}
            <section className="story-section">
              <h2 className="section-title">Choose Your Reading Material</h2>
              <div className="language-selector">
                <button 
                  className={`lang-btn ${selectedLanguage === 'english' ? 'active' : ''}`}
                  onClick={() => handleLanguageChange('english')}
                  disabled={isRecording}
                >
                  🇺🇸 English
                </button>
                <button 
                  className={`lang-btn ${selectedLanguage === 'hindi' ? 'active' : ''}`}
                  onClick={() => handleLanguageChange('hindi')}
                  disabled={isRecording}
                >
                  🇮🇳 हिंदी
                </button>
              </div>

              {currentStory && (
                <div className="story-content">
                  <h3 className="story-title">{currentStory.title}</h3>
                  <div className="story-text">
                    {currentStory.content}
                  </div>
                </div>
              )}
            </section>

            {/* Recording Controls */}
            <section className="controls-section">
              <div className="recording-controls">
                <div className="timer-display">
                  <span className="timer-label">Time Remaining</span>
                  <span className={`timer-value ${timeRemaining <= 60 ? 'warning' : ''}`}>
                    {formatTime(timeRemaining)}
                  </span>
                </div>

                <button
                  className={`record-btn ${isRecording ? 'recording' : ''}`}
                  onClick={isRecording ? stopRecording : startRecording}
                  disabled={!isConnected && !isRecording}
                >
                  {isRecording ? (
                    <>
                      <span className="record-icon">⏹️</span>
                      Stop Recording
                    </>
                  ) : (
                    <>
                      <span className="record-icon">🎤</span>
                      Start Recording
                    </>
                  )}
                </button>

                <div className="connection-status">
                  <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`}></span>
                  <span className="status-text">
                    {isConnected ? 'Connected' : 'Disconnected'}
                  </span>
                </div>
              </div>

              {/* Real-time Stats */}
              {isRecording && (
                <div className="stats-display">
                  <div className="stat-item">
                    <span className="stat-label">Words Spoken</span>
                    <span className="stat-value">{wordCount}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Current Rate</span>
                    <span className="stat-value">{calculateWordsPerMinute()} WPM</span>
                  </div>
                </div>
              )}
            </section>

            {/* Live Transcript */}
            {transcript && (
              <section className="transcript-section">
                <h3 className="section-title">Live Transcript</h3>
                <div className="transcript-display">
                  {transcript}
                </div>
              </section>
            )}

            {/* Error Display */}
            {error && (
              <div className="error-message">
                <span className="error-icon">⚠️</span>
                {error}
              </div>
            )}
          </>
        ) : (
          /* Results Display */
          <section className="results-section">
            <h2 className="section-title">📊 Your Speaking Analysis</h2>
            
            <div className="results-grid">
              <div className="result-card">
                <h3>Total Words</h3>
                <span className="result-value">{sessionResults.totalWords}</span>
              </div>
              
              <div className="result-card">
                <h3>Average WPM</h3>
                <span className="result-value">{sessionResults.averageWpm}</span>
              </div>
            </div>

            <div className="breakdown-section">
              <h3>Minute-by-Minute Breakdown</h3>
              <div className="breakdown-list">
                {sessionResults.breakdown.map((item, index) => (
                  <div key={index} className="breakdown-item">
                    <span className="breakdown-time">{item.minute}</span>
                    <span className="breakdown-words">{item.words} words</span>
                  </div>
                ))}
              </div>
            </div>

            <button 
              className="reset-btn"
              onClick={() => {
                setSessionResults(null);
                setTranscript('');
                setWordCount(0);
                setTimeRemaining(300);
              }}
            >
              📝 Try Again
            </button>
          </section>
        )}
      </main>
    </div>
  );
}

export default App;