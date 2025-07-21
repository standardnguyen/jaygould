#!/usr/bin/env python3
"""
DeepSeek API Concurrent Batch Processor - Fixed Type Errors

This version fixes the type annotation errors you're seeing.
"""

import os
import glob
import time
import asyncio
from pathlib import Path
from openai import AsyncOpenAI
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any

# Load environment variables
load_dotenv()

class DeepSeekConcurrentProcessor:
    def __init__(self):
        self.api_key = os.getenv('DEEPSEEK_API_KEY')
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable is required")

        # Initialize OpenAI client with DeepSeek settings
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        )

        # Set up directories
        self.prompts_dir = Path("./prompts_for_raw_chapters/")
        self.responses_dir = Path("./responses_from_deepseek/")

        # Create responses directory if it doesn't exist
        self.responses_dir.mkdir(exist_ok=True)

    def read_prompt_file(self, filepath: str) -> Optional[str]:
        """Read the content of a prompt file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            print(f"Error reading file {filepath}: {e}")
            return None

    async def send_to_deepseek_async(self, prompt: str, model: str = "deepseek-chat") -> Optional[str]:
        """Send prompt to DeepSeek API asynchronously and return response"""
        try:
            # Create messages list with explicit typing
            messages: List[Dict[str, str]] = [
                {"role": "user", "content": prompt}
            ]

            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore
                max_tokens=8000,
                stream=False
            )

            # Check if response was truncated due to max_tokens limit
            if response.choices[0].finish_reason == "length":
                print(f"⚠️ Warning: Response was truncated due to max_tokens limit")

            return response.choices[0].message.content
        except Exception as e:
            print(f"API Error: {e}")
            return None

    def save_response(self, response_text: str, output_filename: str) -> bool:
        """Save response to file"""
        try:
            output_path = self.responses_dir / output_filename
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(response_text)
            print(f"✓ Saved response to {output_path}")
            return True
        except Exception as e:
            print(f"Error saving response to {output_filename}: {e}")
            return False

    def get_specific_prompt_files(self, chapter_numbers: List[int]) -> List[str]:
        """Get specific prompt files for given chapter numbers"""
        files = []
        for chapter_num in chapter_numbers:
            # Format chapter number with leading zero if needed
            chapter_str = f"{chapter_num:02d}"
            pattern = str(self.prompts_dir / f"prompt_chapter_{chapter_str}.md")
            matching_files = glob.glob(pattern)
            if matching_files:
                files.extend(matching_files)
            else:
                print(f"Warning: No file found for chapter {chapter_num} (pattern: {pattern})")

        return sorted(files)

    async def process_single_file(self, filepath: str) -> bool:
        """Process a single file asynchronously"""
        filename = Path(filepath).name
        print(f"Starting processing: {filename}")

        # Read the prompt
        prompt = self.read_prompt_file(filepath)
        if prompt is None:
            print(f"✗ Skipped {filename} (read error)")
            return False

        # Send to DeepSeek
        response = await self.send_to_deepseek_async(prompt)
        if response is None:
            print(f"✗ Failed to get response for {filename}")
            return False

        # Generate output filename
        # Convert prompt_chapter_01.md -> response_chapter_01.md
        output_filename = filename.replace("prompt_", "response_")

        # Save response
        if self.save_response(response, output_filename):
            print(f"✓ Completed processing: {filename}")
            return True
        else:
            print(f"✗ Failed to save response for {filename}")
            return False

    async def process_files_concurrently(self, chapter_numbers: List[int]):
        """Process multiple files concurrently"""
        prompt_files = self.get_specific_prompt_files(chapter_numbers)

        if not prompt_files:
            print(f"No files found for chapters: {chapter_numbers}")
            return

        print(f"Found {len(prompt_files)} files to process concurrently:")
        for file in prompt_files:
            print(f"  - {Path(file).name}")
        print(f"Responses will be saved to: {self.responses_dir}")
        print("-" * 50)

        # Process all files concurrently
        start_time = time.time()
        tasks = [self.process_single_file(filepath) for filepath in prompt_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count results
        successful = sum(1 for result in results if result is True)
        failed = len(results) - successful
        elapsed_time = time.time() - start_time

        print("-" * 50)
        print(f"Concurrent processing complete!")
        print(f"✓ Successful: {successful}")
        print(f"✗ Failed: {failed}")
        print(f"⏱ Total time: {elapsed_time:.2f} seconds")
        print(f"⚡ Average time per file: {elapsed_time/len(results):.2f} seconds")

def main():
    """Main function"""
    try:
        processor = DeepSeekConcurrentProcessor()

        # Specify which chapters to process
        chapters_to_process = [3,6,8,9,10,11,12,*range(13, 30)] # Chapters 13-29

        print(f"Processing chapters: {chapters_to_process}")

        # Run the async processing
        asyncio.run(processor.process_files_concurrently(chapters_to_process))

    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
