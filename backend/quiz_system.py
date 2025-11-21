import os
import json
import random
from typing import List, Dict
from groq import Groq

class QuizSystem:
    def __init__(self, groq_client):
        """
        Initialize Quiz system with Groq LLM.
        Note: document_store and faiss_index are passed as parameters to methods
        to ensure we always work with the current state.
        """
        self.groq_client = groq_client
        self.generated_questions = []
    
    def generate_questions(self, notebook_id: int, document_store: list, faiss_index, num_questions: int = 20) -> List[Dict]:
        """
        Generate quiz questions from the uploaded documents using RAG.
        
        Steps:
        1. Get document chunks from vector store for the notebook
        2. Use Groq LLM to generate diverse questions
        3. Store questions for later retrieval
        """
        print(f"[QuizSystem] Generating questions for notebook {notebook_id}")
        print(f"[QuizSystem] FAISS index total: {faiss_index.ntotal}")
        print(f"[QuizSystem] Document store size: {len(document_store)}")
        
        if faiss_index.ntotal == 0:
            print("[QuizSystem] ERROR: FAISS index is empty")
            raise Exception("No documents have been processed yet. Please upload and process documents first.")
        
        # Get chunks for this notebook
        notebook_chunks = [doc for doc in document_store if doc.get("notebook_id") == notebook_id]
        
        print(f"[QuizSystem] Found {len(notebook_chunks)} chunks for notebook {notebook_id}")
        
        if not notebook_chunks:
            print(f"[QuizSystem] ERROR: No chunks found for notebook {notebook_id}")
            raise Exception(f"No documents found for this notebook. Please upload and process documents first.")
        
        # Sample multiple chunks to get diverse content
        sample_size = min(10, len(notebook_chunks))
        sampled_chunks = random.sample(notebook_chunks, sample_size)
        
        print(f"[QuizSystem] Sampled {sample_size} chunks for question generation")
        
        # Construct context from sampled chunks
        context = "\n\n".join([
            f"[Section {i+1}]:\n{chunk['chunk']}" 
            for i, chunk in enumerate(sampled_chunks)
        ])
        
        print(f"[QuizSystem] Context length: {len(context)} characters")
        
        prompt = f"""Based on the following document content, generate {num_questions} diverse quiz questions. 
The questions should test understanding, recall, analysis, and application of the content.

Document Content:
{context[:4000]}  

Generate questions of varying difficulty:
- Some should be factual recall questions (easy)
- Some should require understanding and analysis (medium)
- Some should be application-based (hard)
- Include both short-answer and detailed explanation questions

Respond with ONLY a JSON array in this exact format:
[
  {{
    "question": "What is...",
    "difficulty": "easy",
    "type": "factual",
    "expected_key_points": ["point1", "point2", "point3"]
  }},
  {{
    "question": "How does...",
    "difficulty": "medium",
    "type": "analytical",
    "expected_key_points": ["point1", "point2"]
  }},
  {{
    "question": "Apply the concept...",
    "difficulty": "hard",
    "type": "application",
    "expected_key_points": ["point1", "point2"]
  }}
]

Generate exactly {num_questions} questions. Respond ONLY with valid JSON, no additional text."""

        try:
            print(f"[QuizSystem] Calling Groq API to generate {num_questions} questions...")
            
            response = self.groq_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert educational content creator specializing in quiz generation. Respond only with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                max_tokens=3000,
            )
            
            questions_json = response.choices[0].message.content
            print(f"[QuizSystem] Received response from Groq API")
            print(f"[QuizSystem] Response preview: {questions_json[:200]}...")
            
            # Extract JSON from potential markdown code blocks
            if "```json" in questions_json:
                questions_json = questions_json.split("```json")[1].split("```")[0].strip()
            elif "```" in questions_json:
                questions_json = questions_json.split("```")[1].split("```")[0].strip()
            
            questions = json.loads(questions_json)
            print(f"[QuizSystem] Successfully parsed {len(questions)} questions")
            
            # Add unique IDs and notebook_id to questions
            for i, q in enumerate(questions):
                q["question_id"] = len(self.generated_questions) + i + 1
                q["notebook_id"] = notebook_id
            
            # Store questions for this notebook
            self.generated_questions = [q for q in self.generated_questions if q.get("notebook_id") != notebook_id]
            self.generated_questions.extend(questions)
            
            print(f"[QuizSystem] Successfully generated and stored {len(questions)} questions")
            print(f"[QuizSystem] Total questions in system: {len(self.generated_questions)}")
            
            return questions
            
        except json.JSONDecodeError as e:
            print(f"[QuizSystem] JSON parsing error: {e}")
            print(f"[QuizSystem] Raw response: {questions_json}")
            raise Exception(f"Failed to parse questions from AI response: {str(e)}")
        except Exception as e:
            print(f"[QuizSystem] Error generating questions: {e}")
            import traceback
            traceback.print_exc()
            raise Exception(f"Error generating quiz questions: {str(e)}")
    
    def search_relevant_chunks_for_question(self, query: str, notebook_id: int, document_store: list, embedding_model, faiss_index, top_k: int = 3) -> List[Dict]:
        """Search for relevant chunks using the existing search method."""
        import faiss as faiss_lib
        
        if faiss_index.ntotal == 0:
            return []
        
        # Create query embedding
        query_embedding = embedding_model.encode([query]).astype('float32')
        faiss_lib.normalize_L2(query_embedding)
        
        # Search in FAISS
        search_k = min(top_k * 2, faiss_index.ntotal)
        scores, indices = faiss_index.search(query_embedding, search_k)
        
        # Filter by notebook_id
        relevant_chunks = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < len(document_store):
                doc = document_store[idx]
                if doc["notebook_id"] == notebook_id:
                    relevant_chunks.append({
                        "chunk": doc["chunk"],
                        "document_name": doc.get("document_name", "Unknown"),
                        "score": float(score)
                    })
        
        relevant_chunks.sort(key=lambda x: x["score"], reverse=True)
        return relevant_chunks[:top_k]
    
    def evaluate_answer(self, question: str, user_answer: str, notebook_id: int, document_store: list, embedding_model, faiss_index, question_id: int = None) -> Dict:
        """
        Evaluate user's answer using RAG and similarity matching.
        
        Steps:
        1. Use RAG to get the correct/expected answer from documents
        2. Compare user answer with expected answer using LLM
        3. Provide feedback and score
        """
        # Get relevant chunks for the question
        relevant_chunks = self.search_relevant_chunks_for_question(query=question, notebook_id=notebook_id, document_store=document_store, embedding_model=embedding_model, faiss_index=faiss_index, top_k=3)
        
        # Construct expected answer from chunks
        context = "\n\n".join([chunk["chunk"] for chunk in relevant_chunks])
        
        # Find question details if available
        question_details = None
        if question_id:
            question_details = next(
                (q for q in self.generated_questions if q.get("question_id") == question_id and q.get("notebook_id") == notebook_id),
                None
            )
        
        # Construct evaluation prompt
        evaluation_prompt = f"""You are an expert teacher evaluating a student's answer. 

Question: {question}

Student's Answer:
{user_answer}

Reference Content from Documents:
{context[:2000]}

Key Points to Look For:
{json.dumps(question_details.get('expected_key_points', [])) if question_details else 'N/A'}

Evaluate the student's answer and provide:
1. A score from 0-100
2. The correct/expected answer based on the reference content
3. Detailed feedback on what was correct
4. What was missing or incorrect
5. Suggestions for improvement

Respond ONLY with valid JSON in this format:
{{
  "score": 85,
  "expected_answer": "The correct answer is...",
  "feedback": "Your answer was mostly accurate...",
  "strengths": ["point1", "point2"],
  "weaknesses": ["point1", "point2"],
  "suggestions": "To improve your answer..."
}}"""

        try:
            response = self.groq_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a fair and constructive teacher evaluating student answers. Respond only with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": evaluation_prompt
                    }
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.3,
                max_tokens=1500,
            )
            
            evaluation_json = response.choices[0].message.content
            
            # Extract JSON from potential markdown code blocks
            if "```json" in evaluation_json:
                evaluation_json = evaluation_json.split("```json")[1].split("```")[0].strip()
            elif "```" in evaluation_json:
                evaluation_json = evaluation_json.split("```")[1].split("```")[0].strip()
            
            evaluation = json.loads(evaluation_json)
            
            # Add sources
            evaluation["sources"] = [{"text": chunk["chunk"][:200] + "...", "document_name": chunk["document_name"]} for chunk in relevant_chunks]
            
            return evaluation
            
        except Exception as e:
            print(f"Error evaluating answer: {e}")
            return {
                "score": 50,
                "expected_answer": context[:500] + "..." if context else "Please refer to the document content.",
                "feedback": "Unable to evaluate answer automatically. Please review the reference content.",
                "strengths": [],
                "weaknesses": [],
                "suggestions": "Compare your answer with the expected answer below.",
                "sources": [{"text": chunk["chunk"][:200] + "...", "document_name": chunk["document_name"]} for chunk in relevant_chunks],
                "error": str(e)
            }
    
    def get_random_questions(self, notebook_id: int, count: int) -> List[Dict]:
        """
        Get random questions from the generated set for a specific notebook.
        """
        notebook_questions = [q for q in self.generated_questions if q.get("notebook_id") == notebook_id]
        
        if not notebook_questions:
            return []
        
        count = min(count, len(notebook_questions))
        return random.sample(notebook_questions, count)
    
    def get_questions_for_notebook(self, notebook_id: int) -> List[Dict]:
        """Get all questions for a specific notebook."""
        return [q for q in self.generated_questions if q.get("notebook_id") == notebook_id]
    
    def clear_questions(self, notebook_id: int = None):
        """Clear generated questions for a specific notebook or all notebooks."""
        if notebook_id:
            self.generated_questions = [q for q in self.generated_questions if q.get("notebook_id") != notebook_id]
        else:
            self.generated_questions = []
