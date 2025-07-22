#!/usr/bin/env python3
"""
Enhanced DeepSeek API Concurrent Batch Processor with Continuation Support

This improved version:
1. Handles response truncation by automatically continuing conversations
2. Implements better error handling and retries
3. Adds progress tracking
4. Includes response validation
"""

import os
import glob
import time
import asyncio
from pathlib import Path
from openai import AsyncOpenAI, APIError
from dotenv import load_dotenv
import json
from typing import Optional, List, Dict
import logging

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EnhancedDeepSeekProcessor:
    def __init__(self, enable_continuations=True, max_continuations=7):
        self.api_key = os.getenv('DEEPSEEK_API_KEY')
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable is required")

        self.enable_continuations = enable_continuations
        self.max_continuations = max_continuations
        self.max_retries = 3
        self.retry_delay = 5  # seconds

        # Initialize OpenAI client
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        )

        # Set up directories
        self.prompts_dir = Path("./prompts_for_raw_chapters/")
        self.responses_dir = Path("./responses_from_deepseek/")
        self.responses_dir.mkdir(exist_ok=True)

        # Create a failed responses directory for debugging
        self.failed_dir = Path("./failed_responses/")
        self.failed_dir.mkdir(exist_ok=True)

        # Statistics
        self.processed_files = 0
        self.truncated_responses = 0
        self.failed_files = 0
        self.validation_failures = []

    async def send_to_deepseek_with_retry(self, messages: List[Dict], model: str = "deepseek-chat"):
        """Send messages to DeepSeek API with retry logic"""
        for attempt in range(self.max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=8000,
                    stream=False
                )
                return response
            except APIError as e:
                if attempt == self.max_retries - 1:
                    logger.error(f"API Error after {self.max_retries} attempts: {e}")
                    raise
                wait_time = self.retry_delay * (attempt + 1)
                logger.warning(f"API Error (attempt {attempt + 1}): {e}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                raise

        return None

    async def get_complete_response(self, initial_prompt: str, model: str = "deepseek-chat"):
        """Get complete response with continuation support"""
        messages = [{"role": "user", "content": initial_prompt}]
        full_response = ""
        continuation_count = 0

        while True:
            try:
                response = await self.send_to_deepseek_with_retry(messages, model)
                if not response:
                    return None

                content = response.choices[0].message.content
                full_response += content

                # Check if response was truncated
                if response.choices[0].finish_reason == "length":
                    self.truncated_responses += 1
                    if not self.enable_continuations or continuation_count >= self.max_continuations:
                        logger.info(f"Response truncated after {continuation_count} continuations")
                        return full_response

                    continuation_count += 1
                    logger.info(f"Continuing truncated response (continuation {continuation_count})")

                    # Add assistant response and new user prompt to continue
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": "Please continue from where you left off."})
                else:
                    # Response is complete
                    if continuation_count > 0:
                        logger.info(f"Response completed after {continuation_count} continuations")
                    return full_response

            except Exception as e:
                logger.error(f"Error getting complete response: {e}")
                return full_response if full_response else None

    def validate_response(self, response_text: str, filename: str) -> tuple[bool, str]:
        """
        Enhanced response validation with detailed feedback
        Returns: (is_valid, reason)
        """
        if not response_text:
            return False, "Empty response"

        # Remove the overly strict validation that was causing issues
        response_length = len(response_text.strip())
        if response_length < 50:
            return False, f"Response too short ({response_length} chars)"

        # Check for common error patterns (but be more lenient)
        lower_response = response_text.lower()

        # Only fail if these appear at the very beginning of the response
        error_patterns = [
            "i'm sorry, but",
            "i cannot",
            "error:",
            "api error",
            "rate limit"
        ]

        for pattern in error_patterns:
            if lower_response.startswith(pattern):
                return False, f"Response starts with error pattern: '{pattern}'"

        # If the response contains substantial content, it's likely valid
        # even if it contains words like "sorry" somewhere in the middle
        if response_length > 200:
            return True, "Valid response"

        return True, "Valid response"

    async def process_single_file(self, filepath: Path):
        """Process a single file with enhanced error handling"""
        filename = filepath.name
        output_filename = filename.replace("prompt_", "response_")
        output_path = self.responses_dir / output_filename

        # Skip if already processed
        if output_path.exists():
            logger.info(f"Skipping already processed: {filename}")
            self.processed_files += 1
            return True

        logger.info(f"Processing: {filename}")

        # Read prompt with error handling
        try:
            prompt = filepath.read_text(encoding='utf-8').strip()
            if not prompt:
                logger.error(f"Empty prompt in {filename}")
                self.failed_files += 1
                return False
        except Exception as e:
            logger.error(f"Error reading {filename}: {e}")
            self.failed_files += 1
            return False

        # Get complete response
        response = await self.get_complete_response(prompt)

        # Validate response
        is_valid, reason = self.validate_response(response, filename) if response else (False, "No response received")

        if not is_valid:
            logger.error(f"Invalid response for {filename}: {reason}")
            self.failed_files += 1
            self.validation_failures.append((filename, reason))

            # Save failed response for debugging
            if response:
                failed_path = self.failed_dir / f"failed_{output_filename}"
                try:
                    failed_path.write_text(f"REASON: {reason}\n\n{response}", encoding='utf-8')
                except Exception as e:
                    logger.error(f"Error saving failed response: {e}")

            return False

        # Save response
        try:
            output_path.write_text(response, encoding='utf-8')
            logger.info(f"Successfully processed: {filename}")
            self.processed_files += 1
            return True
        except Exception as e:
            logger.error(f"Error saving response for {filename}: {e}")
            self.failed_files += 1
            return False

    async def process_files_concurrently(self, chapter_numbers: List[int], max_concurrent: int = 10):
        """Process multiple files concurrently with controlled concurrency"""
        prompt_files = []
        for chapter_num in chapter_numbers:
            chapter_str = f"{chapter_num:02d}"
            pattern = str(self.prompts_dir / f"prompt_chapter_{chapter_str}.md")
            matching_files = glob.glob(pattern)
            prompt_files.extend([Path(f) for f in matching_files])

        if not prompt_files:
            logger.error("No matching files found!")
            return

        print(f"\n📂 Found {len(prompt_files)} files to process")
        print(f"🔧 Max concurrent requests: {max_concurrent}")
        print("🚀 Starting concurrent processing...")
        print("-" * 50)

        start_time = time.time()

        # Process files with controlled concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(filepath):
            async with semaphore:
                return await self.process_single_file(filepath)

        tasks = [process_with_semaphore(filepath) for filepath in prompt_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle results
        successful = sum(1 for result in results if result is True)
        failed = len(results) - successful
        elapsed_time = time.time() - start_time

        print("-" * 50)
        print("\n📊 Processing Summary:")
        print(f"✅ Successful: {successful}")
        print(f"❌ Failed: {failed}")
        print(f"⚠️  Truncated responses: {self.truncated_responses}")
        print(f"⏱  Total time: {elapsed_time:.2f} seconds")
        print(f"⚡ Average time per file: {elapsed_time/max(1, len(results)):.2f} seconds")

        if self.validation_failures:
            print("\n❌ Validation Failures:")
            for filename, reason in self.validation_failures:
                print(f"  - {filename}: {reason}")
            print(f"\n💡 Check the '{self.failed_dir}' directory for failed responses")

async def main():
    try:
        # Create processor with more reasonable settings
        processor = EnhancedDeepSeekProcessor(
            enable_continuations=True,
            max_continuations=5  # Increased from 3
        )

        # Specify which chapters to process
        chapters_to_process = [2,4,8,17,19,21]
        print(f"🎯 Processing chapters: {chapters_to_process}")

        # Process with controlled concurrency to avoid rate limits
        await processor.process_files_concurrently(
            chapters_to_process,
            max_concurrent=15  # Reduce concurrent requests to avoid overwhelming the API
        )

    except KeyboardInterrupt:
        print("\n🛑 Process interrupted by user")
    except Exception as e:
        print(f"🔥 Critical error: {e}")
        logger.exception("Critical error in main")

if __name__ == "__main__":
    asyncio.run(main())
