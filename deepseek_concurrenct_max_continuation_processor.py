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

# Load environment variables
load_dotenv()

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

        # Statistics
        self.processed_files = 0
        self.truncated_responses = 0
        self.failed_files = 0

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
                    raise
                wait_time = self.retry_delay * (attempt + 1)
                print(f"⚠️ API Error (attempt {attempt + 1}): {e}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            except Exception as e:
                print(f"Unexpected error: {e}")
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
                        print(f"⚠️ Response truncated after {continuation_count} continuations")
                        return full_response

                    continuation_count += 1
                    print(f"↩️ Continuing truncated response (continuation {continuation_count})")

                    # Add assistant response and new user prompt to continue
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": "Please continue from where you left off."})
                else:
                    return full_response

            except Exception as e:
                print(f"Error getting complete response: {e}")
                return full_response if full_response else None

    def validate_response(self, response_text: str) -> bool:
        """Basic response validation"""
        if not response_text:
            return False
        if len(response_text.strip()) < 50:  # Very short responses are likely errors
            return False
        if "error" in response_text.lower() or "sorry" in response_text.lower():
            return False
        return True

    async def process_single_file(self, filepath: Path):
        """Process a single file with enhanced error handling"""
        filename = filepath.name
        output_filename = filename.replace("prompt_", "response_")
        output_path = self.responses_dir / output_filename

        # Skip if already processed
        if output_path.exists():
            print(f"⏩ Skipping already processed: {filename}")
            self.processed_files += 1
            return True

        print(f"🔍 Processing: {filename}")

        # Read prompt with error handling
        try:
            prompt = filepath.read_text(encoding='utf-8').strip()
            if not prompt:
                print(f"✗ Empty prompt in {filename}")
                self.failed_files += 1
                return False
        except Exception as e:
            print(f"✗ Error reading {filename}: {e}")
            self.failed_files += 1
            return False

        # Get complete response
        response = await self.get_complete_response(prompt)
        if not response or not self.validate_response(response):
            print(f"✗ Invalid/empty response for {filename}")
            self.failed_files += 1
            return False

        # Save response
        try:
            output_path.write_text(response, encoding='utf-8')
            print(f"✅ Successfully processed: {filename}")
            self.processed_files += 1
            return True
        except Exception as e:
            print(f"✗ Error saving response for {filename}: {e}")
            self.failed_files += 1
            return False

    async def process_files_concurrently(self, chapter_numbers: List[int]):
        """Process multiple files concurrently with progress tracking"""
        prompt_files = []
        for chapter_num in chapter_numbers:
            chapter_str = f"{chapter_num:02d}"
            pattern = str(self.prompts_dir / f"prompt_chapter_{chapter_str}.md")
            matching_files = glob.glob(pattern)
            prompt_files.extend([Path(f) for f in matching_files])

        if not prompt_files:
            print("❌ No matching files found!")
            return

        print(f"📂 Found {len(prompt_files)} files to process")
        print("🚀 Starting concurrent processing...")
        print("-" * 50)

        start_time = time.time()
        tasks = [self.process_single_file(filepath) for filepath in prompt_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle results
        successful = sum(1 for result in results if result is True)
        failed = len(results) - successful
        elapsed_time = time.time() - start_time

        print("-" * 50)
        print("📊 Processing Summary:")
        print(f"✅ Successful: {successful}")
        print(f"❌ Failed: {failed}")
        print(f"⚠️ Truncated responses: {self.truncated_responses}")
        print(f"⏱ Total time: {elapsed_time:.2f} seconds")
        print(f"⚡ Average time per file: {elapsed_time/max(1, len(results)):.2f} seconds")

async def main():
    try:
        processor = EnhancedDeepSeekProcessor(
            enable_continuations=True,
            max_continuations=3
        )

        # Specify which chapters to process
        chapters_to_process = [*range(1, 30)]
        print(f"Processing chapters: {chapters_to_process}")

        await processor.process_files_concurrently(chapters_to_process)

    except KeyboardInterrupt:
        print("\n🛑 Process interrupted by user")
    except Exception as e:
        print(f"🔥 Critical error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
