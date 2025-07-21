#!/usr/bin/env python3
"""
Extract Markdown Content from DeepSeek Responses

This script reads response files from ./responses_from_deepseek/
extracts content between ```markdown and ```
and saves to ./properparts_staging/ with proper naming

Example:
response_chapter_03.md -> 004_chapter_03.md (with extracted content)
"""

import os
import re
import glob
from pathlib import Path

class MarkdownExtractor:
    def __init__(self):
        self.responses_dir = Path("./responses_from_deepseek/")
        self.output_dir = Path("./properparts_staging/")

        # Create output directory if it doesn't exist
        self.output_dir.mkdir(exist_ok=True)

    def extract_markdown_content(self, text):
        """Extract content between ```markdown and ``` markers only"""
        # Pattern to match content between ```markdown and ``` anywhere in the text
        # This handles any intro text before the fences
        pattern = r'```markdown\s*\n(.*?)\n```'

        # Search for the pattern (DOTALL flag to match across newlines)
        match = re.search(pattern, text, re.DOTALL)

        if match:
            return match.group(1).strip()
        else:
            # If no markdown code block found, return None
            return None

    def read_response_file(self, filepath):
        """Read the content of a response file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading file {filepath}: {e}")
            return None

    def save_extracted_content(self, content, output_filename):
        """Save extracted content to file"""
        try:
            output_path = self.output_dir / output_filename
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ Saved extracted content to {output_path}")
            return True
        except Exception as e:
            print(f"Error saving content to {output_filename}: {e}")
            return False

    def get_chapter_number(self, filename):
        """Extract chapter number from filename like 'response_chapter_03.md'"""
        # Pattern to match chapter number
        match = re.search(r'chapter_(\d+)', filename)
        if match:
            return match.group(1)
        return None

    def generate_output_filename(self, chapter_num):
        """Generate output filename like '004_chapter_03.md'"""
        # Pad chapter number to 3 digits and add 1 for the prefix
        chapter_int = int(chapter_num)
        padded_num = str(chapter_int + 1).zfill(3)
        return f"{padded_num}_chapter_{chapter_num.zfill(2)}.md"

    def get_response_files(self):
        """Get all response files"""
        pattern = str(self.responses_dir / "response_chapter_*.md")
        files = glob.glob(pattern)
        return sorted(files)

    def process_all_responses(self):
        """Process all response files"""
        response_files = self.get_response_files()

        if not response_files:
            print(f"No files found in {self.responses_dir}")
            return

        print(f"Found {len(response_files)} response files to process")
        print(f"Extracted content will be saved to: {self.output_dir}")
        print("-" * 60)

        successful = 0
        failed = 0
        no_markdown = 0

        for filepath in response_files:
            filename = Path(filepath).name
            print(f"Processing: {filename}")

            # Read the response file
            content = self.read_response_file(filepath)
            if content is None:
                print(f"✗ Failed to read {filename}")
                failed += 1
                continue

            # Extract chapter number
            chapter_num = self.get_chapter_number(filename)
            if chapter_num is None:
                print(f"✗ Could not extract chapter number from {filename}")
                failed += 1
                continue

            # Extract markdown content
            extracted_content = self.extract_markdown_content(content)
            if extracted_content is None:
                print(f"⚠ No markdown code block found in {filename}")
                no_markdown += 1
                continue

            # Generate output filename
            output_filename = self.generate_output_filename(chapter_num)
            print(f"  -> {output_filename}")

            # Save extracted content
            if self.save_extracted_content(extracted_content, output_filename):
                successful += 1
            else:
                failed += 1

        print("-" * 60)
        print(f"Processing complete!")
        print(f"✓ Successfully extracted: {successful}")
        print(f"⚠ No markdown blocks found: {no_markdown}")
        print(f"✗ Failed: {failed}")

        if no_markdown > 0:
            print(f"\nNote: {no_markdown} files didn't contain ```markdown blocks")
            print("You may want to check those files manually")

def main():
    """Main function"""
    try:
        extractor = MarkdownExtractor()
        extractor.process_all_responses()
    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
