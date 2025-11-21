import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './QuizModal.css';

export default function QuizModal({ isOpen, onClose, notebookId }) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [allQuestions, setAllQuestions] = useState([]);
  const [selectedQuestions, setSelectedQuestions] = useState([]);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [showQuestionSelector, setShowQuestionSelector] = useState(false);
  const [numQuestionsToSelect, setNumQuestionsToSelect] = useState(5);
  const [inputValue, setInputValue] = useState('');
  const [messages, setMessages] = useState([]);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [quizAnswers, setQuizAnswers] = useState({});
  const [quizStarted, setQuizStarted] = useState(false);
  
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (isOpen && !quizStarted) {
      // Reset state when modal opens
      setMessages([]);
      setAllQuestions([]);
      setSelectedQuestions([]);
      setCurrentQuestionIndex(0);
      setQuizAnswers({});
      setInputValue('');
      
      // Automatically start generating questions when modal opens
      handleGenerateQuiz();
    }
  }, [isOpen]);

  const handleGenerateQuiz = async () => {
    if (!notebookId) {
      alert('Please select a notebook first');
      return;
    }

    setIsGenerating(true);
    setShowQuestionSelector(false); // Hide selector during generation
    
    try {
      const response = await fetch('http://localhost:8001/quiz/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          notebook_id: notebookId,
          num_questions: 20
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to generate quiz');
      }

      const data = await response.json();
      
      // Only show selector after questions are successfully generated
      if (data.questions && data.questions.length > 0) {
        setAllQuestions(data.questions);
        setIsGenerating(false); // Stop loading before showing selector
        setShowQuestionSelector(true);
      } else {
        throw new Error('No questions were generated');
      }
      
    } catch (error) {
      console.error('Error generating quiz:', error);
      alert(`Error generating quiz: ${error.message}`);
      setIsGenerating(false);
      setShowQuestionSelector(false);
    }
  };

  const handleStartQuiz = async () => {
    if (numQuestionsToSelect < 1 || numQuestionsToSelect > allQuestions.length) {
      alert(`Please select between 1 and ${allQuestions.length} questions`);
      return;
    }

    try {
      const response = await fetch('http://localhost:8001/quiz/select', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          notebook_id: notebookId,
          num_questions: numQuestionsToSelect
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to select questions');
      }

      const data = await response.json();
      setSelectedQuestions(data.questions);
      setCurrentQuestionIndex(0);
      setQuizStarted(true);
      setShowQuestionSelector(false);
      
      // Display first question
      const firstQuestion = data.questions[0];
      setMessages([{
        role: 'assistant',
        content: `**Question 1 of ${data.questions.length}**\n\n${firstQuestion.question}\n\n*Difficulty: ${firstQuestion.difficulty} | Type: ${firstQuestion.type}*`,
        isQuizQuestion: true,
        timestamp: new Date().toISOString()
      }]);

      // Focus on input
      setTimeout(() => inputRef.current?.focus(), 100);
      
    } catch (error) {
      console.error('Error starting quiz:', error);
      alert(`Error starting quiz: ${error.message}`);
    }
  };

  const handleSubmitAnswer = async () => {
    if (!inputValue.trim() || isEvaluating) return;

    const currentQuestion = selectedQuestions[currentQuestionIndex];
    const userAnswer = inputValue;

    // Display user's answer
    setMessages(prev => [...prev, {
      role: 'user',
      content: userAnswer,
      timestamp: new Date().toISOString()
    }]);

    setInputValue('');
    setIsEvaluating(true);

    try {
      const response = await fetch('http://localhost:8001/quiz/evaluate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          notebook_id: notebookId,
          question_id: currentQuestion.question_id,
          question: currentQuestion.question,
          user_answer: userAnswer
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to evaluate answer');
      }

      const evaluation = await response.json();
      
      // Store answer result
      setQuizAnswers(prev => ({
        ...prev,
        [currentQuestion.question_id]: {
          question: currentQuestion.question,
          user_answer: userAnswer,
          evaluation: evaluation
        }
      }));

      // Format evaluation message with expected answer
      const evaluationMessage = `## 📊 Evaluation Results\n\n### Score: ${evaluation.score}/100\n\n**Correct Answer:**\n${evaluation.expected_answer || 'See reference content below'}\n\n**Feedback:**\n${evaluation.feedback}\n\n**Strengths:**\n${evaluation.strengths && evaluation.strengths.length > 0 ? evaluation.strengths.map(s => `✓ ${s}`).join('\n') : 'None identified'}\n\n**Areas for Improvement:**\n${evaluation.weaknesses && evaluation.weaknesses.length > 0 ? evaluation.weaknesses.map(w => `• ${w}`).join('\n') : 'None identified'}\n\n**Suggestions:**\n${evaluation.suggestions}`;

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: evaluationMessage,
        isEvaluation: true,
        evaluation: evaluation,
        timestamp: new Date().toISOString()
      }]);

      // Check if there are more questions
      if (currentQuestionIndex < selectedQuestions.length - 1) {
        // Show next question after a short delay
        setTimeout(() => {
          const nextIndex = currentQuestionIndex + 1;
          const nextQuestion = selectedQuestions[nextIndex];
          
          setCurrentQuestionIndex(nextIndex);
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: `**Question ${nextIndex + 1} of ${selectedQuestions.length}**\n\n${nextQuestion.question}\n\n*Difficulty: ${nextQuestion.difficulty} | Type: ${nextQuestion.type}*`,
            isQuizQuestion: true,
            timestamp: new Date().toISOString()
          }]);
        }, 2000);
      } else {
        // Quiz completed
        const totalScore = Object.values({ ...quizAnswers, [currentQuestion.question_id]: { evaluation } })
          .reduce((sum, answer) => sum + answer.evaluation.score, 0);
        const avgScore = Math.round(totalScore / selectedQuestions.length);
        
        setTimeout(() => {
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: `## 🎉 Quiz Completed!\n\nYou've answered all ${selectedQuestions.length} questions.\n\n**Average Score: ${avgScore}/100**\n\n${avgScore >= 80 ? '🌟 Excellent work!' : avgScore >= 60 ? '👍 Good job!' : '💪 Keep practicing!'}`,
            isCompletion: true,
            timestamp: new Date().toISOString()
          }]);
        }, 2000);
      }

    } catch (error) {
      console.error('Error evaluating answer:', error);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `❌ Error evaluating answer: ${error.message}`,
        timestamp: new Date().toISOString()
      }]);
    } finally {
      setIsEvaluating(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmitAnswer();
    }
  };

  const handleClose = () => {
    setQuizStarted(false);
    setMessages([]);
    setAllQuestions([]);
    setSelectedQuestions([]);
    setCurrentQuestionIndex(0);
    setQuizAnswers({});
    setShowQuestionSelector(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="quiz-modal-overlay">
      <div className="quiz-modal">
        <div className="quiz-modal-header">
          <h2>📝 Quiz Mode</h2>
          <button className="quiz-close-button" onClick={handleClose}>
            ✕
          </button>
        </div>

        {/* Question Selector Modal */}
        {showQuestionSelector && (
          <div className="question-selector-overlay">
            <div className="question-selector-modal">
              <h3>Select Number of Questions</h3>
              <p>Total questions generated: {allQuestions.length}</p>
              
              <div className="question-selector-input">
                <label>How many questions do you want to answer?</label>
                <input
                  type="number"
                  min="1"
                  max={allQuestions.length}
                  value={numQuestionsToSelect}
                  onChange={(e) => setNumQuestionsToSelect(parseInt(e.target.value) || 1)}
                  className="number-input"
                />
              </div>

              <div className="questions-preview">
                <p className="preview-label">Question Types:</p>
                <div className="difficulty-breakdown">
                  <span className="badge easy">
                    Easy: {allQuestions.filter(q => q.difficulty === 'easy').length}
                  </span>
                  <span className="badge medium">
                    Medium: {allQuestions.filter(q => q.difficulty === 'medium').length}
                  </span>
                  <span className="badge hard">
                    Hard: {allQuestions.filter(q => q.difficulty === 'hard').length}
                  </span>
                </div>
              </div>

              <div className="selector-buttons">
                <button 
                  className="selector-button cancel" 
                  onClick={() => setShowQuestionSelector(false)}
                >
                  Cancel
                </button>
                <button 
                  className="selector-button start" 
                  onClick={handleStartQuiz}
                >
                  Start Quiz
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="quiz-modal-content">
          {isGenerating ? (
            <div className="quiz-start-screen">
              <div className="quiz-loading-container">
                <div className="quiz-loading-spinner"></div>
                <h3>Generating Quiz Questions...</h3>
                <p>Analyzing your documents using RAG to create personalized questions</p>
                <div className="loading-steps">
                  <div className="loading-step">
                    <span className="step-icon">📄</span>
                    <span>Reading documents</span>
                  </div>
                  <div className="loading-step">
                    <span className="step-icon">🧠</span>
                    <span>Extracting key concepts</span>
                  </div>
                  <div className="loading-step">
                    <span className="step-icon">✨</span>
                    <span>Generating questions</span>
                  </div>
                </div>
              </div>
            </div>
          ) : !quizStarted ? (
            <div className="quiz-start-screen">
              <div className="quiz-icon">📚</div>
              <h3>Ready to Start Quiz</h3>
              <p>Questions have been generated from your documents</p>
              
              <button
                className="generate-quiz-button"
                onClick={handleGenerateQuiz}
                disabled={isGenerating}
              >
                <span className="button-icon">✨</span>
                Generate New Quiz
              </button>

              <div className="quiz-info">
                <h4>How it works:</h4>
                <ol>
                  <li>AI analyzes your documents and generates questions</li>
                  <li>Choose how many questions you want to answer</li>
                  <li>Answer questions and get instant feedback with scores</li>
                  <li>Review your performance and learn from detailed explanations</li>
                </ol>
              </div>
            </div>
          ) : (
            <>
              <div className="quiz-progress-bar">
                <div 
                  className="quiz-progress-fill" 
                  style={{ 
                    width: `${((currentQuestionIndex + 1) / selectedQuestions.length) * 100}%` 
                  }}
                />
                <span className="quiz-progress-text">
                  Question {currentQuestionIndex + 1} of {selectedQuestions.length}
                </span>
              </div>

              <div className="quiz-messages-container">
                {messages.length === 0 ? (
                  <div className="quiz-empty-state">
                    <p>Loading quiz...</p>
                  </div>
                ) : (
                  <>
                    {messages.map((msg, index) => (
                      <div 
                        key={index} 
                        className={`quiz-message ${msg.role} ${msg.isQuizQuestion ? 'quiz-question' : ''} ${msg.isEvaluation ? 'evaluation' : ''} ${msg.isCompletion ? 'completion' : ''}`}
                      >
                        <div className="quiz-message-avatar">
                          {msg.role === 'user' ? '👤' : msg.isQuizQuestion ? '❓' : msg.isEvaluation ? '📊' : msg.isCompletion ? '🎉' : '🤖'}
                        </div>
                        <div className="quiz-message-content">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.content}
                          </ReactMarkdown>
                          {msg.evaluation && (
                            <div className="score-bar-container">
                              <div className="score-bar">
                                <div 
                                  className="score-fill" 
                                  style={{
                                    width: `${msg.evaluation.score}%`,
                                    backgroundColor: msg.evaluation.score >= 70 ? '#4caf50' : msg.evaluation.score >= 50 ? '#ff9800' : '#f44336'
                                  }}
                                />
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                    {isEvaluating && (
                      <div className="quiz-message assistant">
                        <div className="quiz-message-avatar">🤖</div>
                        <div className="quiz-message-content">
                          <div className="typing-indicator">
                            <span></span>
                            <span></span>
                            <span></span>
                          </div>
                        </div>
                      </div>
                    )}
                    <div ref={messagesEndRef} />
                  </>
                )}
              </div>

              {currentQuestionIndex < selectedQuestions.length && (
                <div className="quiz-input-container">
                  <textarea
                    ref={inputRef}
                    className="quiz-input"
                    placeholder="Type your answer here..."
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyPress={handleKeyPress}
                    disabled={isEvaluating}
                    rows="3"
                  />
                  <button
                    className="quiz-submit-button"
                    onClick={handleSubmitAnswer}
                    disabled={isEvaluating || !inputValue.trim()}
                  >
                    <span className="submit-icon">✓</span>
                    Submit Answer
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
