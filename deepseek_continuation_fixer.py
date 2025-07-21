#!/usr/bin/env python3
"""
DeepSeek Continuation Fixer

This script identifies truncated responses and uses Chat Prefix Completion
to continue them until they're complete.
"""

import os
import glob
import time
import asyncio
from pathlib import Path
from openai import AsyncOpenAI
from dotenv import load_dotenv
import re

# Load environment variables
load_dotenv()

class DeepSeekContinuationFixer:
    def __init__(self):
        self.api_key = os.getenv('DEEPSEEK_API_KEY')
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable is required")

        # Initialize OpenAI client with DeepSeek beta endpoint for continuation
        self.beta_client = AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com/beta"  # Beta endpoint for Chat Prefix Completion
        )

        # Regular client for checking
        self.regular_client = AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        )

        # Set up directories
        self.prompts_dir = Path("./prompts_for_raw_chapters/")
        self.responses_dir = Path("./responses_from_deepseek/")
        self.backup_dir = Path("./responses_from_deepseek/backups/")

        # Create backup directory
        self.backup_dir.mkdir(exist_ok=True)

    def read_file(self, filepath):
        """Read the content of a file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            print(f"Error reading file {filepath}: {e}")
            return None

    def save_file(self, content, filepath):
        """Save content to file"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"Error saving file {filepath}: {e}")
            return False

    def is_response_truncated(self, response_text):
        """Check if a response appears to be truncated"""
        # Common signs of truncation
        truncation_indicators = [
            # Ends mid-sentence
            lambda text: not text.strip().endswith(('.', '!', '?', '"', "'", ')', ']', '}')) and len(text.strip()) > 100,
            # Ends with incomplete word
            lambda text: text.strip() and text.strip()[-1].isalnum() and ' ' not in text.strip()[-20:],
            # Very abrupt ending after long content
            lambda text: len(text) > 5000 and not any(text.strip().endswith(end) for end in ['.', '!', '?', '."', ".'", '?"', "?'"]),
            # Ends with incomplete markdown
            lambda text: text.count('```') % 2 != 0 or text.count('**') % 2 != 0,
        ]

        return any(indicator(response_text) for indicator in truncation_indicators)

    async def continue_response(self, original_prompt, truncated_response, max_continuations=5):
        """Continue a truncated response using Chat Prefix Completion"""
        try:
            full_response = truncated_response
            continuation_count = 0

            print(f"  🔄 Attempting to continue truncated response...")

            while continuation_count < max_continuations:
                # Use Chat Prefix Completion to continue
                continuation_response = await self.beta_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "user", "content": original_prompt},
                        {"role": "assistant", "content": full_response, "prefix": True}
                    ],
                    max_tokens=8000,
                    stream=False
                )

                continuation_text = continuation_response.choices[0].message.content

                if not continuation_text or len(continuation_text.strip()) < 10:
                    print(f"  ✓ Response appears complete (short continuation)")
                    break

                # Append the continuation
                full_response += continuation_text
                continuation_count += 1

                print(f"  📄 Added continuation {continuation_count} ({len(continuation_text)} chars)")

                # Check if this continuation was also truncated
                if continuation_response.choices[0].finish_reason != "length":
                    print(f"  ✓ Response completed after {continuation_count} continuations")
                    break

                # Small delay between continuations
                await asyncio.sleep(0.5)

            if continuation_count >= max_continuations:
                print(f"  ⚠️ Reached max continuations ({max_continuations}), response may still be incomplete")

            return full_response

        except Exception as e:
            print(f"  ✗ Error during continuation: {e}")
            return truncated_response  # Return original if continuation fails

    def get_truncated_files(self):
        """Find all response files that appear to be truncated"""
        response_files = glob.glob(str(self.responses_dir / "response_chapter_*.md"))
        truncated_files = []

        print("🔍 Scanning for truncated responses...")

        for filepath in response_files:
            content = self.read_file(filepath)
            if content and self.is_response_truncated(content):
                truncated_files.append(filepath)
                print(f"  📄 Found truncated: {Path(filepath).name}")

        return sorted(truncated_files)

    def get_original_prompt(self, response_filepath):
        """Get the original prompt for a response file"""
        response_filename = Path(response_filepath).name
        prompt_filename = response_filename.replace("response_", "prompt_")
        prompt_filepath = self.prompts_dir / prompt_filename

        return self.read_file(prompt_filepath)

    async def fix_single_file(self, response_filepath):
        """Fix a single truncated response file"""
        filename = Path(response_filepath).name
        print(f"\n🔧 Fixing: {filename}")

        # Read the truncated response
        truncated_response = self.read_file(response_filepath)
        if not truncated_response:
            print(f"  ✗ Could not read response file")
            return False

        # Get the original prompt
        original_prompt = self.get_original_prompt(response_filepath)
        if not original_prompt:
            print(f"  ✗ Could not find original prompt")
            return False

        # Create backup
        backup_filepath = self.backup_dir / f"{filename}.backup"
        if not self.save_file(truncated_response, backup_filepath):
            print(f"  ⚠️ Could not create backup")
        else:
            print(f"  💾 Backup saved to {backup_filepath}")

        # Continue the response
        complete_response = await self.continue_response(original_prompt, truncated_response)

        if len(complete_response) <= len(truncated_response):
            print(f"  ⚠️ No additional content generated")
            return False

        # Save the completed response
        if self.save_file(complete_response, response_filepath):
            added_length = len(complete_response) - len(truncated_response)
            print(f"  ✓ Fixed! Added {added_length} characters")
            return True
        else:
            print(f"  ✗ Failed to save completed response")
            return False

    async def fix_all_truncated(self):
        """Fix all truncated response files"""
        truncated_files = self.get_truncated_files()

        if not truncated_files:
            print("✅ No truncated files found!")
            return

        print(f"\n🎯 Found {len(truncated_files)} truncated files to fix")
        print("-" * 50)

        start_time = time.time()
        successful = 0
        failed = 0

        for filepath in truncated_files:
            try:
                if await self.fix_single_file(filepath):
                    successful += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"  ✗ Error fixing {Path(filepath).name}: {e}")
                failed += 1

            # Small delay between files
            await asyncio.sleep(1)

        elapsed_time = time.time() - start_time

        print("-" * 50)
        print(f"🏁 Completion fixing complete!")
        print(f"✓ Successfully fixed: {successful}")
        print(f"✗ Failed to fix: {failed}")
        print(f"⏱ Total time: {elapsed_time:.2f} seconds")

    async def fix_specific_chapters(self, chapter_numbers):
        """Fix specific chapter numbers that are truncated"""
        all_truncated = self.get_truncated_files()

        # Filter for specific chapters
        specific_truncated = []
        for filepath in all_truncated:
            filename = Path(filepath).name
            # Extract chapter number from filename like "response_chapter_13.md"
            match = re.search(r'response_chapter_(\d+)\.md', filename)
            if match and int(match.group(1)) in chapter_numbers:
                specific_truncated.append(filepath)

        if not specific_truncated:
            print(f"✅ No truncated files found for chapters {chapter_numbers}!")
            return

        print(f"🎯 Found {len(specific_truncated)} truncated files for chapters {chapter_numbers}")
        for filepath in specific_truncated:
            print(f"  📄 {Path(filepath).name}")

        print("-" * 50)

        start_time = time.time()
        successful = 0
        failed = 0

        for filepath in specific_truncated:
            try:
                if await self.fix_single_file(filepath):
                    successful += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"  ✗ Error fixing {Path(filepath).name}: {e}")
                failed += 1

            # Small delay between files
            await asyncio.sleep(1)

        elapsed_time = time.time() - start_time

        print("-" * 50)
        print(f"🏁 Chapter fixing complete!")
        print(f"✓ Successfully fixed: {successful}")
        print(f"✗ Failed to fix: {failed}")
        print(f"⏱ Total time: {elapsed_time:.2f} seconds")

def main():
    """Main function"""
    try:
        fixer = DeepSeekContinuationFixer()

        print("DeepSeek Continuation Fixer")
        print("=" * 50)
        print("1. Fix all truncated responses")
        print("2. Fix specific chapters")

        choice = input("\nChoose option (1 or 2): ").strip()

        if choice == "1":
            asyncio.run(fixer.fix_all_truncated())
        elif choice == "2":
            chapters_input = input("Enter chapter numbers (e.g., 10,13,15 or 13-29): ").strip()

            # Parse chapter numbers
            chapter_numbers = []
            for part in chapters_input.split(','):
                part = part.strip()
                if '-' in part:
                    start, end = part.split('-')
                    chapter_numbers.extend(range(int(start), int(end) + 1))
                else:
                    chapter_numbers.append(int(part))

            asyncio.run(fixer.fix_specific_chapters(chapter_numbers))
        else:
            print("Invalid choice!")

    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
