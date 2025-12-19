"""
LLM Client - Interface to LiteLLM API
Handles all LLM interactions with retry logic
"""

import logging
import os
import time
from typing import Optional

from openai import APIError, OpenAI

logger = logging.getLogger(__name__)

# LiteLLM Configuration
LITELLM_BASE_URL = "http://3.110.18.218"
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "")
DEFAULT_MODEL = "gemini-2.5-flash"


class LLMClient:
    """
    LLM Client with retry logic and rate limiting handling.
    Uses OpenAI-compatible API through LiteLLM proxy.
    """
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or LITELLM_API_KEY
        self.base_url = base_url or LITELLM_BASE_URL
        
        if not self.api_key:
            logger.warning("LITELLM_API_KEY not set. LLM calls will fail.")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        logger.info(f"LLM Client initialized with base URL: {self.base_url}")
    
    async def generate(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
        max_retries: int = 5
    ) -> str:
        """
        Generate text using the LLM with exponential backoff retry.
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        base_delay = 1
        
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                return response.choices[0].message.content
                
            except APIError as e:
                if e.status_code == 429:
                    wait_time = base_delay * (2 ** attempt)
                    logger.warning(f"Rate limited (429). Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"API Error (Status: {e.status_code}): {e.message}")
                    raise
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                if attempt < max_retries - 1:
                    wait_time = base_delay * (2 ** attempt)
                    time.sleep(wait_time)
                else:
                    raise
        
        raise Exception("Failed to generate response after multiple retries")
    
    async def generate_with_functions(
        self,
        prompt: str,
        functions: list[dict],
        model: str = DEFAULT_MODEL,
        temperature: float = 0.3
    ) -> dict:
        """
        Generate with function calling support.
        """
        messages = [{"role": "user", "content": prompt}]
        
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                tools=[{"type": "function", "function": f} for f in functions],
                tool_choice="auto"
            )
            
            message = response.choices[0].message
            
            if message.tool_calls:
                return {
                    "type": "function_call",
                    "function_name": message.tool_calls[0].function.name,
                    "arguments": message.tool_calls[0].function.arguments
                }
            else:
                return {
                    "type": "text",
                    "content": message.content
                }
                
        except Exception as e:
            logger.error(f"Function calling error: {e}")
            raise
